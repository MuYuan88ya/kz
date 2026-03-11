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

Run this in Kaggle:

```bash
!python3 zrok_server.py --token "YOUR_ZROK_TOKEN" --password "0"
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

Optional arguments:

```bash
!python3 zrok_server.py --token "YOUR_ZROK_TOKEN" --password "0" --name "kaggle_server"
!python3 zrok_server.py --token "YOUR_ZROK_TOKEN" --authorized_keys_url "https://example.com/authorized_keys"
```

If you want key-based authentication, upload your public key somewhere reachable and pass it with `--authorized_keys_url`.

## Client Side Usage

### One-click launcher

Double-click `start_client.bat`.

It will:

- ask for your zrok token at runtime
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

1. Install local prerequisites, especially `zrok` and VS Code Remote SSH.
2. Start the Kaggle server cell and keep it running.
3. On your local machine, run `start_client.bat` or `python zrok_client.py --token "YOUR_ZROK_TOKEN"`.
4. Wait for the local private access tunnel to bind to `127.0.0.1:9191`.
5. VS Code opens the remote host `kaggle_client`.

## Generated SSH Config

The client writes this host entry if it does not already exist:

```sshconfig
Host kaggle_client
    HostName 127.0.0.1
    User root
    Port 9191
    IdentityFile ~/.ssh/kaggle_rsa
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

If you use password login, the password is whatever you passed to `zrok_server.py`, for example `0`.

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

### `zrok` not found on Windows

Install `zrok` from the official docs and ensure the command is available in `PATH`.

## Files

- `zrok_server.py`: Kaggle-side startup script
- `zrok_client.py`: local client script
- `start_client.bat`: one-click Windows launcher
- `setup_ssh.sh`: SSH server bootstrap for Kaggle
