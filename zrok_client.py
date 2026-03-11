import os
import re
import subprocess
import time
import argparse
import sys
from pathlib import Path
import socket
import shutil
import json
from utils import Zrok


DEFAULT_REMOTE_EXTENSIONS = [
    "ms-python.python",
    "ms-toolsai.jupyter",
    "openai.chatgpt",
]


def wait_for_local_access(port: int, timeout: int = 15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def resolve_ssh_executable():
    resolved = shutil.which("ssh")
    if resolved:
        return resolved

    windows_ssh = Path(os.environ.get("WINDIR", "C:\\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
    if windows_ssh.exists():
        return str(windows_ssh)

    return "ssh"


def resolve_scp_executable():
    resolved = shutil.which("scp")
    if resolved:
        return resolved

    windows_scp = Path(os.environ.get("WINDIR", "C:\\Windows")) / "System32" / "OpenSSH" / "scp.exe"
    if windows_scp.exists():
        return str(windows_scp)

    return "scp"


def wait_for_ssh_ready(host: str, timeout: int = 20):
    ssh_exe = resolve_ssh_executable()
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            [ssh_exe, "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", host, "exit"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
        time.sleep(1)
    return False


def update_vscode_remote_extensions():
    if os.name != "nt":
        return

    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("APPDATA not set; skipping VS Code settings update")
        return

    settings_path = Path(appdata) / "Code" / "User" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                settings = json.loads(content) if content else {}
        except Exception:
            print(f"Could not parse VS Code settings at {settings_path}; skipping extension defaults update")
            return
    else:
        settings = {}

    current = settings.get("remote.SSH.defaultExtensions", [])
    if not isinstance(current, list):
        current = []

    merged = list(current)
    for extension in DEFAULT_REMOTE_EXTENSIONS:
        if extension not in merged:
            merged.append(extension)

    settings["remote.SSH.defaultExtensions"] = merged

    with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print("VS Code remote extension defaults updated")


def sync_codex_auth(host: str):
    local_auth = Path(os.environ["USERPROFILE"]) / ".codex" / "auth.json"
    if not local_auth.exists():
        print(f"Local Codex auth not found at {local_auth}; skipping remote sync")
        return

    ssh_exe = resolve_ssh_executable()
    scp_exe = resolve_scp_executable()

    mkdir_result = subprocess.run(
        [ssh_exe, host, "mkdir", "-p", "/root/.codex"],
        capture_output=True,
        text=True,
    )
    if mkdir_result.returncode != 0:
        raise Exception(f"Failed to create /root/.codex on remote host {host}")

    copy_result = subprocess.run(
        [scp_exe, str(local_auth), f"{host}:/root/.codex/auth.json"],
        capture_output=True,
        text=True,
    )
    if copy_result.returncode != 0:
        raise Exception(f"Failed to copy Codex auth.json to remote host {host}")

    print("Codex auth synced to /root/.codex/auth.json")


def main(args):
    zrok = Zrok(args.token, args.name)
    
    if not Zrok.is_installed():
        Zrok.install()

    zrok.disable()
    zrok.enable()

    # 1. Get zrok share token
    env = zrok.find_env(args.server_name)
    if env is None:
        raise Exception(f"{args.server_name} environment not found. Are you running the notebook?")

    share_token = None
    for share in reversed(env.get("shares", [])):
        if (share.get("backendMode") == "tcpTunnel" and
            share.get("backendProxyEndpoint") == f"localhost:{args.port}"):
            share_token = share.get("shareToken")
            break

    if not share_token:
        raise Exception(f"SSH tunnel not found in {args.server_name} environment. Are you running the notebook?")

    # 2. Start zrok process
    print(f"{zrok.cli} access private {share_token}")
    subprocess.Popen(
        [zrok.cli, "access", "private", share_token],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )

    # 3. Wait for local zrok access listener
    if not wait_for_local_access(9191, timeout=15):
        raise Exception("Timed out waiting for local zrok access on 127.0.0.1:9191")

    # 4. Update SSH config
    config_path = os.path.join(os.environ['USERPROFILE'], '.ssh', 'config')
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entry_lines = [
        f"Host {args.name}",
        "    HostName 127.0.0.1",
        "    User root",
        "    Port 9191",
    ]

    identity_file = Path(os.environ['USERPROFILE']) / '.ssh' / 'kaggle_rsa'
    if identity_file.exists():
        entry_lines.append("    IdentityFile ~/.ssh/kaggle_rsa")
    else:
        entry_lines.extend([
            "    PreferredAuthentications password",
            "    PubkeyAuthentication no",
        ])

    entry_lines.extend([
        "    StrictHostKeyChecking no",
        "    UserKnownHostsFile /dev/null",
    ])
    entry = "\n".join(entry_lines)

    host_pattern = re.compile(
        rf"(?ms)^Host\s+{re.escape(args.name)}\s*$.*?(?=^Host\s+\S|\Z)"
    )
    if host_pattern.search(content):
        new_content = host_pattern.sub(entry + "\n", content).rstrip("\n") + "\n"
        print(f"SSH config updated for {args.name}")
    else:
        new_content = content.rstrip("\n")
        if new_content:
            new_content += "\n"
        new_content += entry + "\n"
        print(f"SSH config created for {args.name}")

    user_name = None
    if os.name == 'nt':
        user_name = f"{os.environ.get('COMPUTERNAME')}\\{os.environ.get('USERNAME')}"
        subprocess.run(
            [
                "icacls",
                config_path,
                "/inheritance:r",
                "/grant:r",
                f"{user_name}:(F)",
                "SYSTEM:(F)",
                "Administrators:(F)",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    with open(config_path, 'w', encoding='utf-8', newline='') as f:
        f.write(new_content)

    if os.name == 'nt' and user_name:
        subprocess.run(
            [
                "icacls",
                config_path,
                "/inheritance:r",
                "/grant:r",
                f"{user_name}:(R)",
                "SYSTEM:(F)",
                "Administrators:(F)",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    if not wait_for_ssh_ready(args.name, timeout=20):
        raise Exception(f"Timed out waiting for SSH login on host {args.name}")

    sync_codex_auth(args.name)
    update_vscode_remote_extensions()

    # 5. Launch VS Code remote-SSH
    if not args.no_vscode:
        print("Launching VS Code with remote SSH connection...")
        subprocess.Popen(
            ["code", "--remote", f"ssh-remote+{args.name}", args.workspace],
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        print("VS Code launched. Please wait for the connection to establish...")
        time.sleep(5)  # Give some time for VS Code to start


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Kaggle SSH connection setup')
    parser.add_argument('--token', type=str, help='zrok API token')
    parser.add_argument('--name', type=str, default='kaggle_client', help='zrok environment name and SSH config Host name (default: kaggle_client)')
    parser.add_argument('--server_name', type=str, default='kaggle_server', help='Server environment name (default: kaggle_server)')
    parser.add_argument('--port', type=int, default=22, help='SSH port (default: 22)')
    parser.add_argument('--no-vscode', action='store_true', help='Do not launch VS Code after setup')
    parser.add_argument('--workspace', type=str, default='/kaggle/working', help='Default workspace directory to open in VS Code remote session')
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
