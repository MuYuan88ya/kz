# Kaggle Remote zrok

Use Kaggle as a temporary remote Linux machine and connect to it from your local machine through `zrok` and SSH.

This repository keeps the flow split into two sides:

- Server side: run in Kaggle to start SSH and publish a private `tcpTunnel` share
- Client side: run on your local Windows machine to connect that share and open VS Code Remote SSH

`zrok.exe` is intentionally not committed. Install `zrok` from the official docs first:

- https://docs.zrok.io/docs/guides/install/

## Prerequisites

### Kaggle side

- A Kaggle notebook with internet enabled
- Your zrok account token

### Local Windows side

- Python 3.11+
- VS Code
- VS Code Remote - SSH extension
- `zrok` installed and available in `PATH`

Optional:

- An SSH key at `~/.ssh/kaggle_rsa` if you want key-based login

## Server Side Usage

### Recommended persistent workflow

Because Kaggle notebook files under `/kaggle/working` persist, the server side now supports:

- one-time initialization with `--init`
- later starts with `--start`

The persistent state is stored in:

```text
/kaggle/working/.kaggle_remote_zrok
```

### First-time init in Kaggle

Recommended mode: SSH public key login, no password prompts.

If your local machine does not already have `~/.ssh/kaggle_rsa`, run `start_client.bat` once locally. It will generate the key pair automatically.

Then print your public key on Windows:

```powershell
Get-Content $env:USERPROFILE\.ssh\kaggle_rsa.pub -Raw
```

Copy that single-line public key and paste it into this Kaggle command:

```bash
!git clone https://github.com/MuYuan88ya/kz.git /kaggle/working/kz
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_key "PASTE_YOUR_PUBLIC_KEY_HERE"
```

What `--init` does:

- saves your zrok token
- saves your SSH auth configuration
- starts SSH and the private zrok share immediately

### Later starts in Kaggle

After the first init, later sessions only need:

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

This reuses the saved token and saved SSH auth config from `/kaggle/working/.kaggle_remote_zrok`.

### Password-based init

If you still prefer password login, initialize once like this:

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

What it does:

- enables a zrok environment named `kaggle_server`
- installs and configures OpenSSH server
- sets the root password
- starts a private zrok TCP tunnel for `localhost:22`
- keeps running so the private share stays alive

Important:

- Do not stop the cell after it starts the share
- The default server environment name is `kaggle_server`
- The default SSH port is `22`
- `--start` expects that `--init` has already been run at least once in the same notebook storage

Optional arguments:

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --name "kaggle_server"
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_keys_url "https://example.com/authorized_keys"
!python3 zrok_server.py --start --name "kaggle_server"
```

If you want key-based authentication, upload your public key somewhere reachable and pass it with `--authorized_keys_url`.

Example with `authorized_keys`:

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_keys_url "https://example.com/authorized_keys"
```

## Client Side Usage

### One-click launcher

Double-click `start_client.bat`.

You do not need to edit the file to store the token.

When the batch window opens, it will show:

```text
Enter your zrok token:
```

Recommended token handling:

- Best: set an environment variable named `ZROK_TOKEN`
- Otherwise the launcher will reuse a locally cached token from your user profile
- Fallback: paste the token into the batch window when prompted once
- Do not hardcode the token into `start_client.bat`

The launcher looks for `zrok` in this order:

1. `zrok` from `PATH`
2. `zrok.exe` in the project directory
3. `ZROK_BIN`

PowerShell example:

```powershell
$env:ZROK_TOKEN="YOUR_ZROK_TOKEN"
.\start_client.bat
```

If `zrok` is not in `PATH`, point the launcher at it explicitly:

```powershell
$env:ZROK_BIN="C:\path\to\zrok.exe"
$env:ZROK_TOKEN="YOUR_ZROK_TOKEN"
.\start_client.bat
```

If you do not set `ZROK_TOKEN`, paste your token there and press Enter.

After the first successful input, `start_client.bat` stores the token in:

```text
%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt
```

On later runs it will reuse that token automatically, so you do not need to paste it again.

To clear the saved token, delete:

```text
%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt
```

Recommended flow:

1. Double-click `start_client.bat`
2. On the first run, let it cache your token and generate `~/.ssh/kaggle_rsa`
3. Wait for the tunnel and VS Code Remote SSH to open

It will:

- ask for your zrok token at runtime
- cache the token for later runs
- auto-generate `~/.ssh/kaggle_rsa` if it does not exist yet
- enable a local zrok client environment
- find the `kaggle_server` share
- start `zrok access private ...` on local port `9191`
- write an SSH host named `kaggle_client` into `%USERPROFILE%\\.ssh\\config`
- open VS Code Remote SSH

### Command line

You can also run the client directly:

```powershell
python zrok_client.py --token "YOUR_ZROK_TOKEN"
```

Optional arguments:

```powershell
python zrok_client.py --token "YOUR_ZROK_TOKEN" --no-vscode
python zrok_client.py --token "YOUR_ZROK_TOKEN" --name "kaggle_client" --server_name "kaggle_server"
python zrok_client.py --token "YOUR_ZROK_TOKEN" --workspace "/kaggle/working"
```

## End-to-end Flow

### First time

1. Install local prerequisites, especially `zrok` and VS Code Remote SSH.
2. Run `start_client.bat` once on Windows so it can cache your token and generate `~/.ssh/kaggle_rsa`.
3. Copy the contents of `~/.ssh/kaggle_rsa.pub`.
4. In Kaggle, run `zrok_server.py --init --token ... --authorized_key "..."`.
5. Keep the Kaggle cell running.
6. Run `start_client.bat` locally and connect.

### Later sessions

1. In Kaggle, run `zrok_server.py --start`.
2. Keep the Kaggle cell running.
3. On your local machine, double-click `start_client.bat`.
4. VS Code opens the remote host `kaggle_client`.

If you prefer not to use the batch file, this command is equivalent:

```powershell
python zrok_client.py --token "YOUR_ZROK_TOKEN" --name "kaggle_client" --server_name "kaggle_server" --workspace "/kaggle/working"
```

## Generated SSH Config

The client writes this host entry if it does not already exist:

```sshconfig
Host kaggle_client
    HostName 127.0.0.1
    User root
    Port 9191
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

If `~/.ssh/kaggle_rsa` exists, the client uses key-based login.

If it does not exist, the client switches to password authentication automatically.

## Troubleshooting

### `enableUnauthorized`

- Make sure you are using a real zrok account token
- Make sure another terminal is not holding a conflicting local zrok state
- Try:

```powershell
zrok disable
zrok enable YOUR_ZROK_TOKEN
```

### `kaggle_server environment not found`

- The Kaggle cell is not running
- The server environment name does not match `--server_name`
- The server process did not finish creating the private share
- You ran `--start` before ever running `--init`

### `zrok` not found on Windows

Install `zrok` from the official docs and ensure the command is available in `PATH`.

If you do not want to modify `PATH`, set:

```powershell
$env:ZROK_BIN="C:\path\to\zrok.exe"
```

## Files

- `zrok_server.py`: Kaggle-side startup script
- `zrok_client.py`: local client script
- `start_client.bat`: one-click Windows launcher
- `setup_ssh.sh`: SSH server bootstrap for Kaggle
