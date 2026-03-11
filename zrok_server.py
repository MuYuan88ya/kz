import subprocess
import argparse
import sys
import time
import json
import os
import socket
import string
import random
from pathlib import Path
from utils import Zrok

# ── Paths ───────────────────────────────────────────────────────────
STATE_DIR = Path("/kaggle/working/.kaggle_remote_zrok")
CONFIG_FILE = STATE_DIR / "server_config.json"
SAVED_KEYS_FILE = STATE_DIR / "authorized_keys"
LIVE_KEYS_FILE = Path("/kaggle/working/.ssh/authorized_keys")
ENV_VARS_FILE = Path("/kaggle/working/kaggle_env_vars.txt")
DEVTOOLS_LOG = STATE_DIR / "devtools-launch.log"


def generate_password(length=16):
    chars = string.ascii_letters + string.digits + "!@#$%^*()-_=+{}[]<>.,?"
    return "".join(random.choices(chars, k=length))


def wait_for_port(host, port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def wait_for_share_token(zrok, port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        env = zrok.find_env(zrok.name)
        if env:
            for share in env.get("shares", []):
                if (share.get("backendMode") == "tcpTunnel"
                        and share.get("backendProxyEndpoint") == f"localhost:{port}"):
                    return share.get("shareToken")
        time.sleep(1)
    return None


def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Saved config not found: {CONFIG_FILE}")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def save_authorized_key(public_key):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(SAVED_KEYS_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(public_key.strip() + "\n")


def copy_saved_keys_to_live():
    if not SAVED_KEYS_FILE.exists():
        return
    LIVE_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = SAVED_KEYS_FILE.read_text(encoding="utf-8")
    with open(LIVE_KEYS_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def dump_env_vars():
    """Capture current Kaggle env vars for later SSH sessions."""
    ENV_VARS_FILE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(f"printenv > {ENV_VARS_FILE}", shell=True, executable="/bin/bash", check=True)


def run_ssh_setup(authorized_keys_url):
    """Run setup_ssh.sh. Tolerates non-zero exit if SSH is actually listening."""
    script = Path(__file__).resolve().parent / "setup_ssh.sh"
    cmd = ["bash", str(script)]
    if authorized_keys_url:
        cmd.append(authorized_keys_url)

    result = subprocess.run(cmd, check=False)
    if result.returncode == 0:
        return

    if wait_for_port("127.0.0.1", 22, timeout=10):
        print(f"setup_ssh.sh exited {result.returncode}, but SSH is listening; continuing")
        return

    raise subprocess.CalledProcessError(result.returncode, result.args)


def launch_devtools():
    script = Path(__file__).resolve().parent / "setup_devtools.sh"
    if not script.exists():
        print("setup_devtools.sh not found; skipping")
        return

    DEVTOOLS_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DEVTOOLS_WATCH_MODE"] = "foreground"

    with open(DEVTOOLS_LOG, "a", encoding="utf-8", newline="\n") as log:
        proc = subprocess.Popen(
            ["bash", str(script)],
            stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=env,
        )
    print(f"Devtools bootstrap started (PID {proc.pid}), log: {DEVTOOLS_LOG}")


# ── Main ────────────────────────────────────────────────────────────

def main(args):
    # 1. Build config from saved state + CLI overrides
    saved = load_config() if args.start else {}

    token = args.token or saved.get("token")
    name = args.name or saved.get("name", "kaggle_server")
    auth_url = args.authorized_keys_url or saved.get("authorized_keys_url")
    password = args.password if args.password is not None else saved.get("password")
    port = args.port if args.port is not None else saved.get("port", 22)

    if not token:
        raise ValueError("A zrok token is required. Use --init with --token once, then --start.")

    # Save authorized key if provided
    if args.authorized_key:
        save_authorized_key(args.authorized_key)

    # Generate password if no auth method configured
    if not SAVED_KEYS_FILE.exists() and not auth_url and password is None:
        password = generate_password()

    # 2. Persist config on --init
    if args.init:
        save_config({"token": token, "name": name, "authorized_keys_url": auth_url,
                      "password": password, "port": port})
        print(f"Config saved to {CONFIG_FILE}")
        if args.authorized_key:
            print(f"Authorized key saved to {SAVED_KEYS_FILE}")
        if password is not None:
            print(f"Password: {password}")

    # 3. Install + enable zrok
    zrok = Zrok(token, name)
    if not Zrok.is_installed():
        Zrok.install()
    zrok.disable()
    zrok.enable()

    # 4. Prepare runtime files
    copy_saved_keys_to_live()
    dump_env_vars()

    # 5. Setup SSH (calls setup_ssh.sh — fully self-contained)
    print("Setting up SSH server...")
    run_ssh_setup(auth_url)

    if password is not None:
        print(f"Setting root password: {password}")
        subprocess.run(f"echo 'root:{password}' | sudo chpasswd", shell=True, check=True)
    else:
        print("Using SSH public key authentication only.")

    # 6. Devtools
    if not args.no_devtools:
        launch_devtools()
    else:
        print("Skipping devtools bootstrap")

    # 7. Start private zrok share
    print(f"Starting private zrok tcp tunnel for localhost:{port}...")
    share_proc = subprocess.Popen(
        [zrok.cli, "share", "private", f"localhost:{port}",
         "--backend-mode", "tcpTunnel", "--headless"]
    )

    share_token = wait_for_share_token(zrok, port)
    if share_token:
        print(f"Share token: {share_token}")
    else:
        print("Share token not found yet. Check zrok status.")

    print("Private share running. Keep this process alive.")
    share_proc.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kaggle SSH server via zrok")
    parser.add_argument("--token", type=str, help="zrok API token")
    parser.add_argument("--name", type=str, help="Environment name (default: kaggle_server)")
    parser.add_argument("--authorized_keys_url", type=str, help="URL to authorized_keys file")
    parser.add_argument("--authorized_key", type=str, help="Public key to persist")
    parser.add_argument("--password", type=str, help="Root password (random if omitted and no key auth)")
    parser.add_argument("--port", type=int, help="SSH port (default: 22)")
    parser.add_argument("--init", action="store_true", help="Save config then start")
    parser.add_argument("--start", action="store_true", help="Start from saved config")
    parser.add_argument("--no-devtools", action="store_true", help="Skip setup_devtools.sh")
    args = parser.parse_args()

    if not args.token and not args.start:
        args.token = input("Enter your zrok API token: ")

    try:
        main(args)
    except Exception as e:
        print(e)
        if sys.stdin.isatty() and "KAGGLE_KERNEL_RUN_TYPE" not in os.environ:
            try:
                input("An error occurred. Press Enter to exit...")
            except EOFError:
                pass
        else:
            raise
