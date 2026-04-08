import argparse
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from utils import Zrok

DEFAULT_LOCAL_SSH_HOST = "127.0.0.1"
DEFAULT_LOCAL_SSH_PORT = 9191
DEFAULT_ACCESS_READY_TIMEOUT = 45
DEFAULT_SSH_READY_TIMEOUT = 120
DEFAULT_SSH_POLL_INTERVAL = 2
DEFAULT_BANNER_READY_TIMEOUT = 30
DEFAULT_SHARE_LOOKUP_TIMEOUT = 90
DEFAULT_SHARE_LOOKUP_POLL_INTERVAL = 3
DEFAULT_WORKSPACE = "/kaggle/working"
DEFAULT_CLIENT_NAME = "kaggle_client"
DEFAULT_SERVER_NAME = "kaggle_server"
KNOWN_SUBCOMMANDS = {"prepare", "start"}

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


@dataclass(frozen=True)
class ClientPaths:
    home: Path
    state_dir: Path
    token_cache_file: Path
    ssh_dir: Path
    private_key: Path
    public_key: Path
    ssh_config: Path
    codex_auth: Path

    @classmethod
    def from_home(cls, home: Optional[Path] = None) -> "ClientPaths":
        resolved_home = Path(home) if home is not None else Path.home()
        ssh_dir = resolved_home / ".ssh"
        state_dir = resolved_home / ".kaggle_remote_zrok"
        return cls(
            home=resolved_home,
            state_dir=state_dir,
            token_cache_file=state_dir / "zrok_token.txt",
            ssh_dir=ssh_dir,
            private_key=ssh_dir / "kaggle_rsa",
            public_key=ssh_dir / "kaggle_rsa.pub",
            ssh_config=ssh_dir / "config",
            codex_auth=resolved_home / ".codex" / "auth.json",
        )


def current_platform(system_name: Optional[str] = None) -> str:
    if system_name:
        return system_name
    if os.name == "nt":
        return "Windows"
    if sys.platform == "darwin":
        return "Darwin"
    return "Linux"


def is_windows(system_name: Optional[str] = None) -> bool:
    return current_platform(system_name) == "Windows"


def is_macos(system_name: Optional[str] = None) -> bool:
    return current_platform(system_name) == "Darwin"


def should_attempt_auto_install_zrok(system_name: Optional[str] = None) -> bool:
    return current_platform(system_name) == "Linux"


def get_client_paths() -> ClientPaths:
    return ClientPaths.from_home()


def normalize_argv(argv: Sequence[str]) -> List[str]:
    argv_list = list(argv)
    if not argv_list:
        return ["start"]
    if argv_list[0] in KNOWN_SUBCOMMANDS:
        return argv_list
    if argv_list[0] in {"-h", "--help"}:
        return argv_list
    return ["start"] + argv_list


def resolve_ssh_executable() -> str:
    resolved = shutil.which("ssh")
    if resolved:
        return resolved

    windows_ssh = Path(os.environ.get("WINDIR", "C:\\Windows")) / "System32" / "OpenSSH" / "ssh.exe"
    if windows_ssh.exists():
        return str(windows_ssh)

    return "ssh"


def resolve_scp_executable() -> str:
    resolved = shutil.which("scp")
    if resolved:
        return resolved

    windows_scp = Path(os.environ.get("WINDIR", "C:\\Windows")) / "System32" / "OpenSSH" / "scp.exe"
    if windows_scp.exists():
        return str(windows_scp)

    return "scp"


def read_cached_token(paths: ClientPaths) -> Optional[str]:
    if not paths.token_cache_file.exists():
        return None
    try:
        token = paths.token_cache_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def prompt_for_token() -> str:
    return input("Enter your zrok token: ").strip()


def resolve_token(explicit_token: Optional[str], paths: ClientPaths) -> str:
    token = explicit_token or os.environ.get("ZROK_TOKEN") or read_cached_token(paths)
    if not token:
        token = prompt_for_token()
    if not token:
        raise RuntimeError("Token is required.")

    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.token_cache_file.write_text(token + "\n", encoding="utf-8")
    return token


def ensure_public_key_from_private(paths: ClientPaths) -> bool:
    if not paths.private_key.exists() or paths.public_key.exists():
        return False

    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        raise RuntimeError(f"Public key file not found: {paths.public_key}")

    result = subprocess.run(
        [ssh_keygen, "-y", "-f", str(paths.private_key)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Public key file not found: {paths.public_key}")

    paths.ssh_dir.mkdir(parents=True, exist_ok=True)
    paths.public_key.write_text(result.stdout.strip() + "\n", encoding="utf-8")
    return True


def ensure_local_ssh_key(paths: ClientPaths, require_keygen: bool) -> bool:
    if paths.private_key.exists() and paths.public_key.exists():
        return False

    if paths.private_key.exists() and not paths.public_key.exists():
        return ensure_public_key_from_private(paths)

    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        if require_keygen:
            raise RuntimeError("ssh-keygen not found. Install OpenSSH Client first.")
        return False

    paths.ssh_dir.mkdir(parents=True, exist_ok=True)
    print(f'Generating SSH key for Kaggle at "{paths.private_key}"...')
    result = subprocess.run(
        [ssh_keygen, "-t", "rsa", "-b", "4096", "-f", str(paths.private_key), "-N", ""],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if require_keygen:
            raise RuntimeError("Failed to generate SSH key.")
        return False
    return True


def has_local_identity_file(paths: ClientPaths) -> bool:
    return paths.private_key.exists()


def quote_for_shell(value: str) -> str:
    return shlex.quote(value)


def build_kaggle_init_command(token: str, public_key: str) -> str:
    return f'!python3 zrok_server.py --init --token {quote_for_shell(token)} --authorized_key {quote_for_shell(public_key)}'


def build_kaggle_start_command() -> str:
    return "!python3 zrok_server.py --start"


def run_prepare(args: argparse.Namespace) -> int:
    paths = get_client_paths()
    token = resolve_token(args.token, paths)
    created_new_key = ensure_local_ssh_key(paths, require_keygen=True)

    if not paths.public_key.exists():
        raise RuntimeError(f'Public key file not found: "{paths.public_key}"')

    public_key = paths.public_key.read_text(encoding="utf-8").strip()

    print()
    if created_new_key:
        print("Generated new SSH key pair for Kaggle.")
    else:
        print("Reusing existing SSH key pair for Kaggle.")
    print()
    print("Public key:")
    print(paths.public_key.read_text(encoding="utf-8").rstrip())
    print()
    print("Kaggle first-time init command:")
    print(build_kaggle_init_command(token, public_key))
    print()
    print("Kaggle later-start command:")
    print(build_kaggle_start_command())
    print()
    return 0


def wait_for_local_access(port: int, timeout: int = DEFAULT_ACCESS_READY_TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((DEFAULT_LOCAL_SSH_HOST, port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def wait_for_remote_ssh_banner(port: int, timeout: int = DEFAULT_BANNER_READY_TIMEOUT) -> Tuple[bool, str]:
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


def wait_for_ssh_ready(host: str, timeout: int = DEFAULT_SSH_READY_TIMEOUT, poll_interval: int = DEFAULT_SSH_POLL_INTERVAL) -> Tuple[bool, str]:
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
            check=False,
        )
        if result.returncode == 0:
            print(f"SSH login confirmed on host {host}")
            return True, ""

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


def lookup_share_token(zrok: Zrok, server_name: str, port: int) -> Optional[str]:
    env = zrok.find_env(server_name)
    if env is None:
        return None

    share = Zrok.find_share(env, f"localhost:{port}", backend_mode="tcpTunnel")
    if share is None:
        return None
    return share.get("shareToken")


def wait_for_share_token(zrok: Zrok, server_name: str, port: int, previous_token: Optional[str] = None) -> str:
    deadline = time.time() + DEFAULT_SHARE_LOOKUP_TIMEOUT
    attempt = 0
    last_status = None

    print(f"Looking up zrok environment {server_name}...")
    while time.time() < deadline:
        attempt += 1
        try:
            share_token = lookup_share_token(zrok, server_name, port)
        except Exception as exc:  # pragma: no cover - passthrough logging path
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
        raise RuntimeError(
            f"{server_name} is still advertising stale share token {previous_token}. "
            "Please rerun the notebook-side start command so it publishes a fresh share."
        )

    raise RuntimeError(
        f"{server_name} share for localhost:{port} not found after waiting. "
        "Is the notebook still running?"
    )


def read_log_tail(log_path: Path, line_count: int = 40) -> str:
    if not log_path.exists():
        return ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-line_count:])


def find_local_listener_pids(port: int) -> List[int]:
    if is_windows():
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
            if not local_address.endswith(port_suffix) or state != "LISTENING":
                continue
            if pid.isdigit():
                pids.add(int(pid))
        return sorted(pids)

    lsof_executable = shutil.which("lsof")
    if not lsof_executable:
        return []
    result = subprocess.run(
        [lsof_executable, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        return []
    pids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return sorted(set(pids))


def kill_local_listener_pids(port: int) -> None:
    pids = find_local_listener_pids(port)
    if not pids:
        return

    print(f"Cleaning up stale local listeners on localhost:{port}: {', '.join(str(pid) for pid in pids)}")
    for pid in pids:
        if is_windows():
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, check=False)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                continue

    deadline = time.time() + 10
    while time.time() < deadline:
        remaining = find_local_listener_pids(port)
        if not remaining:
            return
        time.sleep(1)

    remaining = find_local_listener_pids(port)
    if not is_windows():
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                continue
        time.sleep(1)
        remaining = find_local_listener_pids(port)

    if remaining:
        raise RuntimeError(f"Failed to clear localhost:{port}; remaining listener PIDs: {', '.join(str(pid) for pid in remaining)}")


def start_local_access_tunnel(zrok_cli: str, share_token: str, log_path: Path) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    creationflags = 0
    if is_windows():
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


def stop_process(process: Optional[subprocess.Popen], label: str) -> None:
    if process is None or process.poll() is not None:
        return

    print(f"Stopping {label} (PID {process.pid})...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def ensure_local_access_ready(host_alias: str, port: int, access_process: subprocess.Popen, paths: ClientPaths) -> None:
    deadline = time.time() + DEFAULT_ACCESS_READY_TIMEOUT
    print(f"Waiting for local zrok access on {DEFAULT_LOCAL_SSH_HOST}:{port}...")
    while time.time() < deadline:
        if wait_for_local_access(port, timeout=1):
            print(f"Local tunnel is listening on localhost:{port}")
            banner_ready, banner_error = wait_for_remote_ssh_banner(port)
            if not banner_ready:
                raise RuntimeError(
                    f"Timed out waiting for remote SSH banner on localhost:{port}. Last error: {banner_error}"
                )
            if has_local_identity_file(paths):
                ssh_ready, ssh_error = wait_for_ssh_ready(host_alias)
                if not ssh_ready:
                    raise RuntimeError(
                        f"Timed out waiting for SSH login on host {host_alias}. Last error: {ssh_error}"
                    )
            else:
                print("No local SSH key detected; skipping non-interactive SSH login probe.")
            return

        if access_process is not None and access_process.poll() is not None:
            raise RuntimeError(f"local zrok access exited with code {access_process.returncode}")
        time.sleep(1)

    raise TimeoutError(f"Timed out waiting for local zrok access on {DEFAULT_LOCAL_SSH_HOST}:{port}")


def build_ssh_config_entry(host_alias: str, local_port: int, paths: ClientPaths) -> str:
    entry_lines = [
        f"Host {host_alias}",
        f"    HostName {DEFAULT_LOCAL_SSH_HOST}",
        "    User root",
        f"    Port {local_port}",
    ]

    if paths.private_key.exists():
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
    return "\n".join(entry_lines)


def apply_windows_file_permissions(path: Path) -> None:
    if not is_windows():
        return
    user_name = "{}\\{}".format(os.environ.get("COMPUTERNAME"), os.environ.get("USERNAME"))
    subprocess.run(
        [
            "icacls",
            str(path),
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


def write_ssh_config(host_alias: str, local_port: int, paths: ClientPaths) -> None:
    paths.ssh_dir.mkdir(parents=True, exist_ok=True)
    if not paths.ssh_config.exists():
        paths.ssh_config.write_text("", encoding="utf-8")

    content = paths.ssh_config.read_text(encoding="utf-8")
    entry = build_ssh_config_entry(host_alias, local_port, paths)
    host_pattern = re.compile(rf"(?ms)^Host\s+{re.escape(host_alias)}\s*$.*?(?=^Host\s+\S|\Z)")

    if host_pattern.search(content):
        new_content = host_pattern.sub(entry + "\n", content).rstrip("\n") + "\n"
        print(f"SSH config updated for {host_alias}")
    else:
        new_content = content.rstrip("\n")
        if new_content:
            new_content += "\n"
        new_content += entry + "\n"
        print(f"SSH config created for {host_alias}")

    paths.ssh_config.write_text(new_content, encoding="utf-8")
    apply_windows_file_permissions(paths.ssh_config)


def update_vscode_remote_extensions() -> None:
    if not is_windows():
        return

    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("APPDATA not set; skipping VS Code settings update")
        return

    settings_path = Path(appdata) / "Code" / "User" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            content = settings_path.read_text(encoding="utf-8").strip()
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
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print("VS Code remote extension defaults updated")
    print('VS Code setting "terminal.integrated.gpuAcceleration" set to "on"')


def sync_codex_auth(host: str, paths: ClientPaths) -> bool:
    if not paths.codex_auth.exists():
        print(f"Local Codex auth not found at {paths.codex_auth}; skipping remote sync")
        return False
    if not has_local_identity_file(paths):
        print("Local SSH key not found; skipping remote Codex auth sync")
        return False

    ssh_exe = resolve_ssh_executable()
    scp_exe = resolve_scp_executable()
    command_kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    common_ssh_options = [
        "-o",
        "BatchMode=yes",
        "-o",
        "RequestTTY=no",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ConnectionAttempts=1",
    ]

    print("Syncing Codex auth to remote host...")
    try:
        mkdir_result = subprocess.run(
            [ssh_exe] + common_ssh_options + [host, "mkdir", "-p", "/root/.codex"],
            timeout=10,
            **command_kwargs,
        )
    except subprocess.TimeoutExpired:
        print("Remote Codex auth sync timed out while creating /root/.codex; skipping sync")
        return False
    if mkdir_result.returncode != 0:
        stderr = (mkdir_result.stderr or mkdir_result.stdout or "").strip()
        print(f"Failed to create /root/.codex on remote host {host}; skipping sync. {stderr}")
        return False

    try:
        copy_result = subprocess.run(
            [scp_exe] + common_ssh_options + [str(paths.codex_auth), f"{host}:/root/.codex/auth.json"],
            timeout=10,
            **command_kwargs,
        )
    except subprocess.TimeoutExpired:
        print("Remote Codex auth sync timed out while copying auth.json; skipping sync")
        return False
    if copy_result.returncode != 0:
        stderr = (copy_result.stderr or copy_result.stdout or "").strip()
        print(f"Failed to copy Codex auth.json to remote host {host}; skipping sync. {stderr}")
        return False

    print("Codex auth synced to /root/.codex/auth.json")
    return True


def build_vscode_launch_command(host: str, workspace: str, system_name: Optional[str] = None, code_executable: Optional[str] = None, open_executable: Optional[str] = None) -> Tuple[List[str], dict]:
    resolved_system = current_platform(system_name)
    code_binary = code_executable if code_executable is not None else shutil.which("code")

    if code_binary:
        creationflags = 0
        if resolved_system == "Windows":
            creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs = {"creationflags": creationflags} if resolved_system == "Windows" else {}
        return [code_binary, "--remote", f"ssh-remote+{host}", workspace], kwargs

    if resolved_system == "Darwin":
        open_binary = open_executable if open_executable is not None else shutil.which("open")
        if open_binary:
            return [open_binary, "-a", "Visual Studio Code", "--args", "--remote", f"ssh-remote+{host}", workspace], {}

    raise FileNotFoundError("VS Code launcher not found. Install VS Code and ensure `code` is available, or launch it manually.")


def launch_vscode_remote(host: str, workspace: str) -> bool:
    print("Launching VS Code with remote SSH connection...")
    try:
        command, kwargs = build_vscode_launch_command(host, workspace)
        subprocess.Popen(command, shell=False, **kwargs)
    except Exception as exc:
        print(f"Could not launch VS Code automatically: {exc}")
        print(f"Tunnel and SSH config remain ready; connect manually with host {host} if needed.")
        return False

    print("VS Code launch requested.")
    return True


def ensure_zrok_available(zrok: Zrok) -> None:
    if Zrok.is_installed():
        return
    if should_attempt_auto_install_zrok():
        Zrok.install()
        zrok.cli = Zrok.resolve_executable()
        return
    raise RuntimeError(
        "zrok was not found on this machine. Install it from https://docs.zrok.io/docs/guides/install/ "
        "and ensure `zrok` is in PATH, or set ZROK_BIN to the full zrok executable path."
    )


def run_start(args: argparse.Namespace) -> int:
    paths = get_client_paths()
    token = resolve_token(args.token, paths)
    created_new_key = ensure_local_ssh_key(paths, require_keygen=False)

    if created_new_key and paths.public_key.exists():
        print()
        print("New local Kaggle public key:")
        print(paths.public_key.read_text(encoding="utf-8").rstrip())
        print()

    zrok = Zrok(token, args.name)
    kill_local_listener_pids(DEFAULT_LOCAL_SSH_PORT)
    ensure_zrok_available(zrok)
    zrok.ensure_enabled()

    share_token = wait_for_share_token(zrok, args.server_name, args.port)
    access_log_path = paths.state_dir / f"{args.name}-access.log"
    access_log_path.parent.mkdir(parents=True, exist_ok=True)
    access_log_path.write_text("", encoding="utf-8")

    write_ssh_config(args.name, DEFAULT_LOCAL_SSH_PORT, paths)
    access_process = None

    try:
        for attempt in range(1, 4):
            print(f"{zrok.cli} access private {share_token} --headless")
            access_process = start_local_access_tunnel(zrok.cli, share_token, access_log_path)
            try:
                ensure_local_access_ready(args.name, DEFAULT_LOCAL_SSH_PORT, access_process, paths)
                break
            except (RuntimeError, TimeoutError) as error:
                log_tail = read_log_tail(access_log_path).lower()
                stop_process(access_process, "local zrok access tunnel")
                access_process = None

                should_rebuild_identity = attempt == 1 and ("accessunauthorized" in log_tail or "invalid_auth" in log_tail)
                should_refresh_share = "accessnotfound" in log_tail or "service not found" in log_tail
                should_retry_access = any(
                    marker in log_tail
                    for marker in ["client version error", "tls handshake timeout", "unexpected_eof", "ssl", "timeout", "eof"]
                )

                if not should_rebuild_identity:
                    if should_retry_access and attempt < 3:
                        print("Local zrok access hit a transient network error; retrying...")
                        time.sleep(2)
                        continue
                    if not should_refresh_share or attempt >= 3:
                        raise RuntimeError(f"{error}. See local access log: {access_log_path}")

                    print("Share token is no longer valid; waiting for the notebook to publish a fresh share token...")
                    share_token = wait_for_share_token(zrok, args.server_name, args.port, previous_token=share_token)
                    continue

                print("Local zrok identity cannot access the current share; rebuilding identity and retrying once...")
                zrok.rebuild_local_identity()
                share_token = wait_for_share_token(zrok, args.server_name, args.port)

        print("SSH low-latency options applied:")
        for option_line in DEFAULT_SSH_LOW_LATENCY_OPTIONS:
            print(option_line.strip())

        sync_codex_auth(args.name, paths)
        update_vscode_remote_extensions()

        if not args.no_vscode:
            launch_vscode_remote(args.name, args.workspace)
    except Exception:
        stop_process(access_process, "local zrok access tunnel")
        raise

    return 0


def add_start_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--token", type=str, help="zrok API token")
    parser.add_argument("--name", type=str, default=DEFAULT_CLIENT_NAME, help=f"zrok environment name and SSH config Host name (default: {DEFAULT_CLIENT_NAME})")
    parser.add_argument("--server_name", type=str, default=DEFAULT_SERVER_NAME, help=f"Server environment name (default: {DEFAULT_SERVER_NAME})")
    parser.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("--no-vscode", dest="no_vscode", action="store_true", help="Do not launch VS Code after setup")
    parser.add_argument("--ssh-only", dest="no_vscode", action="store_true", help="Only prepare SSH access and skip launching VS Code")
    parser.add_argument("--workspace", type=str, default=DEFAULT_WORKSPACE, help="Default workspace directory to open in VS Code remote session")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kaggle SSH connection setup")
    subparsers = parser.add_subparsers(dest="command")

    prepare_parser = subparsers.add_parser("prepare", help="Cache token, ensure SSH key, and print Kaggle init commands")
    prepare_parser.add_argument("--token", type=str, help="zrok API token")
    prepare_parser.set_defaults(func=run_prepare)

    start_parser = subparsers.add_parser("start", help="Open the local zrok tunnel, update SSH config, and optionally launch VS Code")
    add_start_arguments(start_parser)
    start_parser.set_defaults(func=run_start)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    normalized_argv = normalize_argv(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(normalized_argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except Exception as exc:
        print(exc)
        if sys.stdin.isatty():
            try:
                input("An error occurred. Press Enter to exit...")
            except EOFError:
                pass
        else:
            raise
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
