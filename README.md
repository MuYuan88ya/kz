# Kaggle Remote zrok

Use Kaggle as a temporary remote Linux machine and connect from Windows through `zrok` and SSH.

`zrok.exe` is intentionally not committed. Install `zrok` first:

- https://docs.zrok.io/docs/guides/install/

## Prerequisites

- A Kaggle notebook with internet enabled
- Your zrok account token
- Windows with Python 3.11+
- VS Code
- VS Code Remote - SSH extension
- `zrok` available in `PATH`, or `zrok.exe` placed in the project directory, or `ZROK_BIN` set

## Init Flow

This only needs to be done once for the same Kaggle notebook storage.

Kaggle persistent state is stored in:

```text
/kaggle/working/.kaggle_remote_zrok
```

### Step 1: Prepare on Windows

Run:

```bat
prepare_client.bat
```

This does four things:

- caches your zrok token in `%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt`
- creates `~/.ssh/kaggle_rsa` if it does not already exist
- prints your SSH public key
- prints the exact Kaggle init command you should paste

This step does not connect to Kaggle.

### Step 2: Initialize in Kaggle

Paste the printed command into a Kaggle cell and run it.

Typical command:

```bash
!git clone https://github.com/MuYuan88ya/kz.git /kaggle/working/kz
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_key "PASTE_YOUR_PUBLIC_KEY_HERE"
```

This init step:

- saves the zrok token
- saves the SSH public key
- captures the current Kaggle notebook environment for later SSH sessions
- starts `sshd`
- starts the private zrok share

You do not need to run extra prep like `chmod +x ...` or `printenv > /kaggle/working/kaggle_env_vars.txt` manually. `zrok_server.py` now does that before calling `setup_ssh.sh`.

### Step 3: Keep Kaggle running

Do not stop the Kaggle cell after the share starts.

### Step 4: Connect from Windows

Run:

```bat
start_client.bat
```

If everything is correct, it will:

- find the `kaggle_server` share
- open local access on `127.0.0.1:9191`
- update `%USERPROFILE%\.ssh\config`
- open VS Code Remote SSH

### Password-based init

If you want password login instead of key login:

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

## Later Use Flow

After init has succeeded once, each later session is only two steps.

### Step 1: Start Kaggle side

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

This reuses the saved token and saved SSH auth config from `/kaggle/working/.kaggle_remote_zrok`.
It also refreshes `/kaggle/working/kaggle_env_vars.txt` automatically before starting SSH.

### Step 2: Start Windows side

```bat
start_client.bat
```

That is the normal daily usage flow.

## Windows Scripts

### `prepare_client.bat`

Use this only during initialization.

It:

- caches your token
- creates `~/.ssh/kaggle_rsa` if needed
- prints the Kaggle init command

### `start_client.bat`

Use this after the Kaggle server is already running.

Token lookup order:

1. `ZROK_TOKEN`
2. `%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt`
3. interactive prompt

`zrok` lookup order:

1. `zrok` from `PATH`
2. `zrok.exe` in the project directory
3. `ZROK_BIN`

To clear the saved token, delete:

```text
%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt
```

## Generated SSH Config

The client writes a host like this:

```sshconfig
Host kaggle_client
    HostName 127.0.0.1
    User root
    Port 9191
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

If `~/.ssh/kaggle_rsa` exists, key-based login is used.

If it does not exist, the client falls back to password authentication.

## Useful Variants

Use a hosted `authorized_keys` file:

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_keys_url "https://example.com/authorized_keys"
```

Use password auth:

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

Change the environment name:

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --name "kaggle_server"
!python3 zrok_server.py --start --name "kaggle_server"
```

## Troubleshooting

### `kaggle_server environment not found`

- The Kaggle cell is not running
- The server process did not finish creating the private share
- You ran `--start` before ever running `--init`

### `enableUnauthorized`

- Make sure the token is a real zrok account token
- Make sure another terminal is not holding conflicting local zrok state

### `zrok` not found on Windows

Install `zrok` and ensure one of these is true:

- `zrok` is in `PATH`
- `zrok.exe` is in the project directory
- `ZROK_BIN` points to the full path of `zrok.exe`

## Files

- `zrok_server.py`: Kaggle-side startup script
- `zrok_client.py`: local client script
- `prepare_client.bat`: first-time local setup helper
- `start_client.bat`: normal Windows connect launcher
- `setup_ssh.sh`: SSH server bootstrap for Kaggle
