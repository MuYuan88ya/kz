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

### Init Phase

This phase only needs to be done once for the same Kaggle notebook storage.

Persistent server state is stored in:

```text
/kaggle/working/.kaggle_remote_zrok
```

Recommended mode is SSH public key login.

#### Step 1: Prepare the client locally

On Windows, run:

```bat
prepare_client.bat
```

This will:

- cache your zrok token locally
- generate `~/.ssh/kaggle_rsa` if it does not exist
- print your public key
- print the exact Kaggle init command

#### Step 2: Initialize the server in Kaggle

Paste the printed command into Kaggle and run it.

Typical first-time init command:

```bash
!git clone https://github.com/MuYuan88ya/kz.git /kaggle/working/kz
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_key "PASTE_YOUR_PUBLIC_KEY_HERE"
```

What `--init` does:

- saves the zrok token to `/kaggle/working/.kaggle_remote_zrok/server_config.json`
- saves the SSH public key to `/kaggle/working/.kaggle_remote_zrok/authorized_keys`
- starts `sshd`
- starts the private zrok share

#### Step 3: Keep the Kaggle cell running

Do not stop the cell after the share starts.

#### Step 4: Connect from Windows

Run:

```bat
start_client.bat
```

If everything is correct, it should:

- find the `kaggle_server` share
- open local access on `127.0.0.1:9191`
- update SSH config for `kaggle_client`
- open VS Code Remote SSH

#### Password-based init

If you want password auth instead of key auth, initialize once like this:

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

### Later Use Phase

After init has completed once, later Kaggle sessions only need:

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

Then on Windows, just run:

```bat
start_client.bat
```

`--start` reuses the saved token and saved SSH auth config from `/kaggle/working/.kaggle_remote_zrok`.

### Notes

- The default server environment name is `kaggle_server`
- The default SSH port is `22`
- `--start` requires that `--init` has already succeeded at least once
- You can still use `--authorized_keys_url` if you prefer hosting `authorized_keys` elsewhere

Useful variants:

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --name "kaggle_server"
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_keys_url "https://example.com/authorized_keys"
!python3 zrok_server.py --start --name "kaggle_server"
```

## Client Side Usage

### First-time local preparation

Run `prepare_client.bat` once on Windows.

It will:

- cache your zrok token in `%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt`
- create `~/.ssh/kaggle_rsa` if it does not already exist
- print your public key
- print the exact Kaggle `--init` command you should paste into the notebook

This step does not try to connect to Kaggle.

### One-click launcher

Double-click `start_client.bat`.

This is the normal connect script to use after the Kaggle server is already running.

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

If you have already run `prepare_client.bat`, normally you do not need to enter it again.

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
2. Wait for the tunnel and VS Code Remote SSH to open

It will:

- ask for your zrok token at runtime
- cache the token for later runs
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

### Init Phase

1. Install local prerequisites, especially `zrok` and VS Code Remote SSH.
2. Run `prepare_client.bat` once on Windows.
3. Copy the printed Kaggle `--init` command into the notebook and run it.
4. Keep the Kaggle cell running.
5. Run `start_client.bat` locally and connect.

### Later Use Phase

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
- `prepare_client.bat`: first-time local setup helper
- `start_client.bat`: one-click Windows launcher
- `setup_ssh.sh`: SSH server bootstrap for Kaggle
