import subprocess
import argparse
import sys
import time
import json
import os
from pathlib import Path
from utils import Zrok
import string
import random

DEFAULT_STATE_DIR = "/kaggle/working/.kaggle_remote_zrok"
DEFAULT_AUTHORIZED_KEYS_PATH = "/kaggle/working/.ssh/authorized_keys"


def generate_random_password(length=16):
    characters = (string.ascii_letters + string.digits + "!@#$%^*()-_=+{}[]<>.,?")
    return ''.join(random.choices(characters, k=length))


def wait_for_share_token(zrok: Zrok, port: int, timeout: int = 20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        env = zrok.find_env(zrok.name)
        if env:
            for share in env.get("shares", []):
                if (share.get("backendMode") == "tcpTunnel" and
                    share.get("backendProxyEndpoint") == f"localhost:{port}"):
                    return share.get("shareToken")
        time.sleep(1)
    return None


def get_state_paths(state_dir: str):
    state_root = Path(state_dir)
    return {
        "root": state_root,
        "config": state_root / "server_config.json",
        "authorized_keys": state_root / "authorized_keys",
    }


def load_saved_config(state_dir: str):
    paths = get_state_paths(state_dir)
    if not paths["config"].exists():
        raise FileNotFoundError(f"Saved config not found: {paths['config']}")
    with open(paths["config"], "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict, state_dir: str):
    paths = get_state_paths(state_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    with open(paths["config"], "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return paths


def write_authorized_key(public_key: str, state_dir: str):
    paths = get_state_paths(state_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    with open(paths["authorized_keys"], "w", encoding="utf-8", newline="\n") as f:
        f.write(public_key.strip() + "\n")
    return str(paths["authorized_keys"])


def copy_persisted_authorized_keys(state_dir: str, live_path: str):
    paths = get_state_paths(state_dir)
    if not paths["authorized_keys"].exists():
        return False

    live_authorized_keys = Path(live_path)
    live_authorized_keys.parent.mkdir(parents=True, exist_ok=True)
    with open(paths["authorized_keys"], "r", encoding="utf-8") as src:
        content = src.read()
    with open(live_authorized_keys, "w", encoding="utf-8", newline="\n") as dst:
        dst.write(content)
    return True


def build_runtime_config(args):
    if args.start:
        config = load_saved_config(args.state_dir)
    else:
        config = {}

    runtime = {
        "token": args.token or config.get("token"),
        "name": args.name or config.get("name", "kaggle_server"),
        "authorized_keys_url": args.authorized_keys_url or config.get("authorized_keys_url"),
        "password": args.password if args.password is not None else config.get("password"),
        "port": args.port if args.port is not None else config.get("port", 22),
        "state_dir": args.state_dir,
    }

    if args.authorized_key:
        runtime["authorized_key_saved"] = write_authorized_key(args.authorized_key, args.state_dir)
    elif get_state_paths(args.state_dir)["authorized_keys"].exists():
        runtime["authorized_key_saved"] = str(get_state_paths(args.state_dir)["authorized_keys"])
    else:
        runtime["authorized_key_saved"] = None

    if not runtime["token"]:
        raise ValueError("A zrok token is required. Use --init with --token once, then later use --start.")

    if not runtime["authorized_key_saved"] and not runtime["authorized_keys_url"] and runtime["password"] is None:
        runtime["password"] = generate_random_password()

    return runtime


def persist_runtime_config(runtime: dict):
    config = {
        "token": runtime["token"],
        "name": runtime["name"],
        "authorized_keys_url": runtime["authorized_keys_url"],
        "password": runtime["password"],
        "port": runtime["port"],
    }
    save_config(config, runtime["state_dir"])


def main(args):
    runtime = build_runtime_config(args)
    if args.init:
        persist_runtime_config(runtime)
        print(f"Saved server config to {get_state_paths(args.state_dir)['config']}")
        if runtime["authorized_key_saved"]:
            print(f"Saved authorized_keys to {runtime['authorized_key_saved']}")
        if runtime["password"] is not None:
            print(f"Saved password for future starts: {runtime['password']}")

    zrok = Zrok(runtime["token"], runtime["name"])
    
    if not Zrok.is_installed():
        Zrok.install()

    zrok.disable()
    zrok.enable()

    copy_persisted_authorized_keys(runtime["state_dir"], DEFAULT_AUTHORIZED_KEYS_PATH)
    
    # Setup SSH server
    print("Setting up SSH server...")
    if runtime["authorized_keys_url"]:
        subprocess.run(["bash", "setup_ssh.sh", runtime["authorized_keys_url"]], check=True)
    else:
        subprocess.run(["bash", "setup_ssh.sh"], check=True)

    if runtime["password"] is not None:
        print(f"Setting password for root user: {runtime['password']}")
        subprocess.run(f"echo 'root:{runtime['password']}' | sudo chpasswd", shell=True, check=True)
    else:
        print("Password login not configured. Using SSH public key authentication only.")

    print("Starting private zrok tcp tunnel for localhost:22...")
    share_process = subprocess.Popen(
        [zrok.cli, "share", "private", f"localhost:{runtime['port']}", "--backend-mode", "tcpTunnel", "--headless"]
    )

    share_token = wait_for_share_token(zrok, runtime["port"])
    if share_token:
        print(f"Share token: {share_token}")
    else:
        print("Share token not found yet. Check zrok service status and environment overview.")

    print("Private share is running. Keep this process alive while the client is connected.")
    share_process.wait()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Kaggle SSH connection setup')
    parser.add_argument('--token', type=str, help='zrok API token')
    parser.add_argument('--name', type=str, help='Environment name to create (default: kaggle_server)')
    parser.add_argument('--authorized_keys_url', type=str, help='URL to authorized_keys file')
    parser.add_argument('--authorized_key', type=str, help='Public key content to persist for future starts')
    parser.add_argument('--password', type=str, help='Password for root user, if not provided, a random password will be generated')
    parser.add_argument('--port', type=int, help='SSH port to share (default: 22)')
    parser.add_argument('--state-dir', type=str, default=DEFAULT_STATE_DIR, help=f'Persistent config directory (default: {DEFAULT_STATE_DIR})')
    parser.add_argument('--init', action='store_true', help='Save token and auth config to persistent storage, then start')
    parser.add_argument('--start', action='store_true', help='Start using previously saved config only')
    args = parser.parse_args()

    if not args.token and not args.start:
        args.token = input("Enter your zrok API token: ")
    
    try:
        main(args)
    except Exception as e:
        print(e)
        if sys.stdin.isatty():
            try:
                input("An error occurred. Press Enter to exit...")
            except EOFError:
                pass
        else:
            raise
