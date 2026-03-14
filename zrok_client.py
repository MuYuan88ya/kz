import os
import re
import subprocess
import time
import argparse
import sys
import socket
import shutil
import json
from pathlib import Path
from utils import Zrok


DEFAULT_REMOTE_EXTENSIONS = [
    "ms-python.python",
    "ms-toolsai.jupyter",
    "openai.chatgpt",
]


def wait_for_port(port, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def resolve_tool(name):
    """Find ssh or scp executable."""
    resolved = shutil.which(name)
    if resolved:
        return resolved

    windir = os.environ.get("WINDIR", "C:\\Windows")
    candidate = Path(windir) / "System32" / "OpenSSH" / f"{name}.exe"
    if candidate.exists():
        return str(candidate)

    return name


def wait_for_ssh_ready(host, timeout=20):
    ssh = resolve_tool("ssh")
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            [ssh, "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "exit"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return True
        # If we get "Permission denied", the SSH server is up but requires a password or valid key.
        # This is fine, we can let VS Code handle the auth prompt.
        if "Permission denied" in result.stderr:
            print("SSH server is ready (authentication required).")
            return True
        time.sleep(1)
    return False


def update_ssh_config(name):
    """Write or update the SSH config entry for the given host name."""
    config_path = Path(os.environ["USERPROFILE"]) / ".ssh" / "config"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
    else:
        content = ""

    # Build entry
    lines = [
        f"Host {name}",
        "    HostName 127.0.0.1",
        "    User root",
        "    Port 9191",
    ]

    identity = Path(os.environ["USERPROFILE"]) / ".ssh" / "kaggle_rsa"
    if identity.exists():
        lines.append("    IdentityFile ~/.ssh/kaggle_rsa")
    else:
        lines.extend([
            "    PreferredAuthentications password",
            "    PubkeyAuthentication no",
        ])

    lines.extend([
        "    StrictHostKeyChecking no",
        "    UserKnownHostsFile /dev/null",
        "    Compression yes",
        "    ServerAliveInterval 15",
        "    ServerAliveCountMax 3",
    ])
    entry = "\n".join(lines)

    # Replace existing or append
    pattern = re.compile(rf"(?ms)^Host\s+{re.escape(name)}\s*$.*?(?=^Host\s+\S|\Z)")
    if pattern.search(content):
        new_content = pattern.sub(entry + "\n", content).rstrip("\n") + "\n"
        print(f"SSH config updated for {name}")
    else:
        new_content = content.rstrip("\n")
        if new_content:
            new_content += "\n"
        new_content += entry + "\n"
        print(f"SSH config created for {name}")

    # Fix Windows file permissions before/after write
    user_name = None
    if os.name == "nt":
        user_name = f"{os.environ.get('COMPUTERNAME')}\\{os.environ.get('USERNAME')}"
        subprocess.run(
            ["icacls", str(config_path), "/inheritance:r", "/grant:r",
             f"{user_name}:(F)", "SYSTEM:(F)", "Administrators:(F)"],
            check=False, capture_output=True, text=True,
        )

    with open(config_path, "w", encoding="utf-8", newline="") as f:
        f.write(new_content)

    if os.name == "nt" and user_name:
        subprocess.run(
            ["icacls", str(config_path), "/inheritance:r", "/grant:r",
             f"{user_name}:(R)", "SYSTEM:(F)", "Administrators:(F)"],
            check=False, capture_output=True, text=True,
        )


def update_vscode_remote_extensions():
    if os.name != "nt":
        return

    appdata = os.environ.get("APPDATA")
    if not appdata:
        return

    settings_path = Path(appdata) / "Code" / "User" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            content = settings_path.read_text(encoding="utf-8").strip()
            settings = json.loads(content) if content else {}
        except Exception:
            print("Could not parse VS Code settings; skipping")
            return
    else:
        settings = {}

    current = settings.get("remote.SSH.defaultExtensions", [])
    if not isinstance(current, list):
        current = []

    merged = list(current)
    for ext in DEFAULT_REMOTE_EXTENSIONS:
        if ext not in merged:
            merged.append(ext)

    settings["remote.SSH.defaultExtensions"] = merged

    with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print("VS Code remote extension defaults updated")


def sync_codex_auth(host):
    local_auth = Path(os.environ["USERPROFILE"]) / ".codex" / "auth.json"
    if not local_auth.exists():
        print(f"Local Codex auth not found at {local_auth}; skipping")
        return

    ssh = resolve_tool("ssh")
    scp = resolve_tool("scp")

    result = subprocess.run([ssh, host, "mkdir", "-p", "/root/.codex"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to create /root/.codex on {host}")

    result = subprocess.run([scp, str(local_auth), f"{host}:/root/.codex/auth.json"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Failed to copy Codex auth to {host}")

    print("Codex auth synced to remote")


# ── Main ────────────────────────────────────────────────────────────

def main(args):
    zrok = Zrok(args.token, args.name)

    if not Zrok.is_installed():
        Zrok.install()

    zrok.disable()
    zrok.enable()

    # 1. Find server share token
    env = zrok.find_env(args.server_name)
    if env is None:
        raise Exception(f"{args.server_name} environment not found. Is the notebook running?")

    share_token = None
    for share in reversed(env.get("shares", [])):
        if (share.get("backendMode") == "tcpTunnel"
                and share.get("backendProxyEndpoint") == f"localhost:{args.port}"):
            share_token = share.get("shareToken")
            break

    if not share_token:
        raise Exception(f"SSH tunnel not found in {args.server_name}. Is the notebook running?")

    # 2. Start zrok access
    print(f"{zrok.cli} access private {share_token}")
    subprocess.Popen(
        [zrok.cli, "access", "private", share_token],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

    # 3. Wait for local listener
    if not wait_for_port(9191, timeout=15):
        raise Exception("Timed out waiting for local zrok access on 127.0.0.1:9191")

    # 4. Update SSH config
    update_ssh_config(args.name)

    if not wait_for_ssh_ready(args.name, timeout=20):
        raise Exception(f"Timed out waiting for SSH on {args.name}")

    # 5. Post-connect setup
    sync_codex_auth(args.name)
    update_vscode_remote_extensions()

    # 6. Launch VS Code
    if not args.no_vscode:
        print("Launching VS Code with remote SSH...")
        subprocess.Popen(
            ["code", "--remote", f"ssh-remote+{args.name}", args.workspace],
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        print("VS Code launched.")
        time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kaggle SSH client via zrok")
    parser.add_argument("--token", type=str, help="zrok API token")
    parser.add_argument("--name", type=str, default="kaggle_client", help="SSH host name (default: kaggle_client)")
    parser.add_argument("--server_name", type=str, default="kaggle_server", help="Server environment (default: kaggle_server)")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("--no-vscode", action="store_true", help="Do not launch VS Code")
    parser.add_argument("--workspace", type=str, default="/kaggle/working", help="Remote workspace path")
    args = parser.parse_args()

    if not args.token:
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
