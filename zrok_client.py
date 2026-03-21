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

DEFAULT_LOCAL_SSH_HOST = "127.0.0.1"
DEFAULT_LOCAL_SSH_PORT = 9191
DEFAULT_ACCESS_READY_TIMEOUT = 45
DEFAULT_SSH_READY_TIMEOUT = 120
DEFAULT_SSH_POLL_INTERVAL = 2
DEFAULT_BANNER_READY_TIMEOUT = 30
DEFAULT_SHARE_LOOKUP_TIMEOUT = 90
DEFAULT_SHARE_LOOKUP_POLL_INTERVAL = 3


DEFAULT_REMOTE_EXTENSIONS = [
    "ms-python.python",
    "ms-toolsai.jupyter",
    "openai.chatgpt",
]

DEFAULT_SSH_LOW_LATENCY_OPTIONS = [
    "    ServerAliveInterval 15",
    "    ServerAliveCountMax 3",
    "    TCPKeepAlive yes",
    "    IPQoS lowdelay throughput",
    "    Compression no",
    "    LogLevel ERROR",
]


def wait_for_local_access(port: int, timeout: int = DEFAULT_ACCESS_READY_TIMEOUT):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((DEFAULT_LOCAL_SSH_HOST, port), timeout=1):
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


def has_local_identity_file() -> bool:
    return (Path(os.environ["USERPROFILE"]) / ".ssh" / "kaggle_rsa").exists()


def wait_for_remote_ssh_banner(port: int, timeout: int = DEFAULT_BANNER_READY_TIMEOUT):
    deadline = time.time() + timeout
    attempt = 0
    last_error = None

    print(f"Waiting for remote SSH banner through localhost:{port}...")
    while time.time() < deadline:
        attempt += 1
        try:
            with socket.create_connection((DEFAULT_LOCAL_SSH_HOST, port), timeout=5) as conn:
                conn.settimeout(5)
                banner = conn.recv(256).decode("utf-8", errors="ignore").strip()
                if banner.startswith("SSH-"):
                    print(f"Remote SSH banner detected: {banner}")
                    return True, banner
                last_error = f"unexpected banner: {banner!r}" if banner else "empty SSH banner"
        except OSError as exc:
            last_error = str(exc)

        remaining = max(0, int(deadline - time.time()))
        print(
            f"SSH banner probe {attempt} not ready yet; retrying for up to {remaining}s. "
            f"Last error: {last_error}"
        )
        time.sleep(2)

    return False, last_error or f"timed out waiting for SSH banner on localhost:{port}"


def wait_for_ssh_ready(
    host: str,
    timeout: int = DEFAULT_SSH_READY_TIMEOUT,
    poll_interval: int = DEFAULT_SSH_POLL_INTERVAL,
    process=None,
):
    ssh_exe = resolve_ssh_executable()
    deadline = time.time() + timeout
    last_error = None
    attempt = 0

    print(f"Waiting for SSH login on host {host}...")
    while time.time() < deadline:
        attempt += 1
        result = subprocess.run(
            [
                ssh_exe,
                "-o",
                "BatchMode=yes",
                "-o",
                "PreferredAuthentications=publickey",
                "-o",
                "PubkeyAuthentication=yes",
                "-o",
                "PasswordAuthentication=no",
                "-o",
                "KbdInteractiveAuthentication=no",
                "-o",
                "GSSAPIAuthentication=no",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "ConnectionAttempts=1",
                host,
                "exit",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"SSH login confirmed on host {host}")
            return True, None

        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        last_error = stderr or stdout or f"ssh exited with code {result.returncode}"
        remaining = max(0, int(deadline - time.time()))
        print(
            f"SSH auth probe {attempt} not ready yet; retrying for up to {remaining}s. "
            f"Last error: {last_error}"
        )

        time.sleep(poll_interval)

    return False, last_error or f"timed out waiting for SSH login on host {host}"


def get_client_state_dir() -> Path:
    return Path(os.environ["USERPROFILE"]) / ".kaggle_remote_zrok"


def lookup_share_token(zrok: Zrok, server_name: str, port: int):
    env = zrok.find_env(server_name)
    if env is None:
        return None

    share = Zrok.find_share(env, f"localhost:{port}", backend_mode="tcpTunnel")
    if share is None:
        return None
    return share.get("shareToken")


def wait_for_share_token(zrok: Zrok, server_name: str, port: int, previous_token: str | None = None):
    deadline = time.time() + DEFAULT_SHARE_LOOKUP_TIMEOUT
    attempt = 0
    last_status = None

    print(f"Looking up zrok environment {server_name}...")
    while time.time() < deadline:
        attempt += 1
        try:
            share_token = lookup_share_token(zrok, server_name, port)
        except Exception as exc:
            last_status = str(exc)
            share_token = None
        else:
            last_status = f"share for localhost:{port} not published yet"

        if share_token:
            if previous_token and share_token == previous_token:
                last_status = f"server is still advertising stale share token {share_token}"
            else:
                print(f"Using share token {share_token}")
                return share_token

        remaining = max(0, int(deadline - time.time()))
        print(
            f"Share lookup {attempt} not ready yet; retrying for up to {remaining}s. "
            f"Last status: {last_status}"
        )
        time.sleep(DEFAULT_SHARE_LOOKUP_POLL_INTERVAL)

    if previous_token:
        raise Exception(
            f"{server_name} is still advertising stale share token {previous_token}. "
            f"Please rerun the notebook-side start command so it publishes a fresh share."
        )

    raise Exception(
        f"{server_name} share for localhost:{port} not found after waiting. "
        f"Is the notebook still running?"
    )


def read_log_tail(log_path: Path, line_count: int = 40):
    if not log_path.exists():
        return ""

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except OSError:
        return ""

    return "".join(lines[-line_count:])


def find_local_listener_pids(port: int):
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []

    pids = set()
    port_suffix = f":{port}"
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 5 or columns[0].upper() != "TCP":
            continue

        local_address = columns[1]
        state = columns[3].upper()
        pid = columns[4]
        if not local_address.endswith(port_suffix):
            continue
        if state != "LISTENING":
            continue
        if pid.isdigit():
            pids.add(int(pid))

    return sorted(pids)


def kill_local_listener_pids(port: int):
    pids = find_local_listener_pids(port)
    if not pids:
        return

    print(f"Cleaning up stale local listeners on localhost:{port}: {', '.join(str(pid) for pid in pids)}")
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            check=False,
        )

    deadline = time.time() + 10
    while time.time() < deadline:
        if not find_local_listener_pids(port):
            return
        time.sleep(1)

    remaining = ", ".join(str(pid) for pid in find_local_listener_pids(port))
    raise Exception(f"Failed to clear localhost:{port}; remaining listener PIDs: {remaining}")


def start_local_access_tunnel(zrok_cli: str, share_token: str, log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)

    with open(log_path, "a", encoding="utf-8", newline="\n") as log_file:
        process = subprocess.Popen(
            [zrok_cli, "access", "private", share_token, "--headless"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    print(f"Started local zrok access tunnel (PID {process.pid})")
    print(f"Local zrok access log: {log_path}")
    return process


def stop_process(process, label: str):
    if process is None or process.poll() is not None:
        return

    print(f"Stopping {label} (PID {process.pid})...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def ensure_local_access_ready(host_alias: str, port: int, access_process):
    deadline = time.time() + DEFAULT_ACCESS_READY_TIMEOUT
    print(f"Waiting for local zrok access on {DEFAULT_LOCAL_SSH_HOST}:{port}...")
    while time.time() < deadline:
        if wait_for_local_access(port, timeout=1):
            print(f"Local tunnel is listening on localhost:{port}")
            banner_ready, banner_error = wait_for_remote_ssh_banner(port)
            if not banner_ready:
                raise Exception(
                    f"Timed out waiting for remote SSH banner on localhost:{port}. "
                    f"Last error: {banner_error}"
                )
            if has_local_identity_file():
                ssh_ready, ssh_error = wait_for_ssh_ready(
                    host_alias,
                    timeout=DEFAULT_SSH_READY_TIMEOUT,
                    poll_interval=DEFAULT_SSH_POLL_INTERVAL,
                    process=access_process,
                )
                if not ssh_ready:
                    raise Exception(
                        f"Timed out waiting for SSH login on host {host_alias}. "
                        f"Last error: {ssh_error}"
                    )
            else:
                print("No local SSH key detected; skipping non-interactive SSH login probe.")
            return

        if access_process is not None and access_process.poll() is not None:
            raise RuntimeError(
                f"local zrok access exited with code {access_process.returncode}"
            )

        time.sleep(1)

    raise TimeoutError(f"Timed out waiting for local zrok access on {DEFAULT_LOCAL_SSH_HOST}:{port}")


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
    settings["terminal.integrated.gpuAcceleration"] = "on"

    with open(settings_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print("VS Code remote extension defaults updated")
    print('VS Code setting "terminal.integrated.gpuAcceleration" set to "on"')


def sync_codex_auth(host: str):
    local_auth = Path(os.environ["USERPROFILE"]) / ".codex" / "auth.json"
    if not local_auth.exists():
        print(f"Local Codex auth not found at {local_auth}; skipping remote sync")
        return
    if not has_local_identity_file():
        print("Local SSH key not found; skipping remote Codex auth sync")
        return

    ssh_exe = resolve_ssh_executable()
    scp_exe = resolve_scp_executable()

    print("Syncing Codex auth to remote host...")
    mkdir_result = subprocess.run(
        [ssh_exe, "-o", "ConnectTimeout=10", host, "mkdir", "-p", "/root/.codex"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if mkdir_result.returncode != 0:
        raise Exception(f"Failed to create /root/.codex on remote host {host}")

    copy_result = subprocess.run(
        [scp_exe, "-o", "ConnectTimeout=10", str(local_auth), f"{host}:/root/.codex/auth.json"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if copy_result.returncode != 0:
        raise Exception(f"Failed to copy Codex auth.json to remote host {host}")

    print("Codex auth synced to /root/.codex/auth.json")


def main(args):
    zrok = Zrok(args.token, args.name)
    kill_local_listener_pids(DEFAULT_LOCAL_SSH_PORT)
    
    if not Zrok.is_installed():
        Zrok.install()
        zrok.cli = Zrok.resolve_executable()

    zrok.ensure_enabled()

    # 1. Get zrok share token
    share_token = wait_for_share_token(zrok, args.server_name, args.port)

    access_log_path = get_client_state_dir() / f"{args.name}-access.log"
    access_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(access_log_path, "w", encoding="utf-8", newline="\n"):
        pass
    access_process = None

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
    entry_lines.extend(DEFAULT_SSH_LOW_LATENCY_OPTIONS)
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

    try:
        for attempt in range(1, 4):
            print(f"{zrok.cli} access private {share_token} --headless")
            access_process = start_local_access_tunnel(zrok.cli, share_token, access_log_path)
            try:
                ensure_local_access_ready(args.name, DEFAULT_LOCAL_SSH_PORT, access_process)
                break
            except (RuntimeError, TimeoutError) as error:
                log_tail = read_log_tail(access_log_path).lower()
                stop_process(access_process, "local zrok access tunnel")
                access_process = None

                should_rebuild_identity = (
                    attempt == 1 and
                    ("accessunauthorized" in log_tail or "invalid_auth" in log_tail)
                )
                should_refresh_share = (
                    "accessnotfound" in log_tail or
                    "service not found" in log_tail
                )
                should_retry_access = any(
                    marker in log_tail
                    for marker in [
                        "client version error",
                        "tls handshake timeout",
                        "unexpected_eof",
                        "ssl",
                        "timeout",
                        "eof",
                    ]
                )
                if not should_rebuild_identity:
                    if should_retry_access and attempt < 3:
                        print("Local zrok access hit a transient network error; retrying...")
                        time.sleep(2)
                        continue
                    if not should_refresh_share or attempt >= 3:
                        raise Exception(
                            f"{error}. See local access log: {access_log_path}"
                        ) from error

                    print("Share token is no longer valid; waiting for the notebook to publish a fresh share token...")
                    share_token = wait_for_share_token(
                        zrok,
                        args.server_name,
                        args.port,
                        previous_token=share_token,
                    )
                    continue

                print("Local zrok identity cannot access the current share; rebuilding identity and retrying once...")
                zrok.rebuild_local_identity()
                share_token = wait_for_share_token(zrok, args.server_name, args.port)

        print("SSH low-latency options applied:")
        for option_line in DEFAULT_SSH_LOW_LATENCY_OPTIONS:
            print(option_line.strip())

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
            print("VS Code launched. Closing client terminal.")
    except Exception:
        stop_process(access_process, "local zrok access tunnel")
        raise


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
