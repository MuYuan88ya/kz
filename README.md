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

- saves the zrok token and SSH public key
- captures current Kaggle env vars for later SSH sessions
- starts `sshd` via `setup_ssh.sh`
- starts `setup_devtools.sh` in the background
- starts the private zrok share

### Step 3: Keep Kaggle running

Do not stop the Kaggle cell after the share starts.

### Step 4: Devtools bootstrap starts automatically

`zrok_server.py` launches `setup_devtools.sh` in the background automatically.

That script:

- installs `nodejs` and `npm` if needed
- installs `@openai/codex`
- adds the persistent npm bin directory to root's PATH
- keeps a fallback watcher for remote VS Code extension installs

Logs:

```text
/kaggle/working/.kaggle_remote_zrok/devtools-launch.log
/kaggle/working/.kaggle_remote_zrok/devtools.log
```

Skip for one run:

```bash
!python3 zrok_server.py --start --no-devtools
```

### Step 5: Connect from Windows

Run:

```bat
start_client.bat
```

It will:

- find the `kaggle_server` share
- open local access on `127.0.0.1:9191`
- update `%USERPROFILE%\.ssh\config`
- update local VS Code remote extension defaults
- open VS Code Remote SSH

### Password-based init

If you want password login instead of key login:

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

## Later Use Flow

After init has succeeded once, each later session is only two steps.

### Step 1: Start Kaggle side

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

### Step 2: Start Windows side

```bat
start_client.bat
```

## Windows Scripts

### `prepare_client.bat`

First-time setup: caches token, creates SSH key, prints Kaggle init command.

### `start_client.bat`

Daily use: connects to running Kaggle server.

Token lookup: `ZROK_TOKEN` → `%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt` → prompt.

`zrok` lookup: `PATH` → project directory → `ZROK_BIN`.

## Generated SSH Config

```sshconfig
Host kaggle_client
    HostName 127.0.0.1
    User root
    Port 9191
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

If `~/.ssh/kaggle_rsa` exists, key-based login is used. Otherwise password authentication.

## Troubleshooting

### `kaggle_server environment not found`

- The Kaggle cell is not running
- The server process did not finish creating the private share
- You ran `--start` before ever running `--init`

### `enableUnauthorized`

- Make sure the token is a real zrok account token
- Make sure another terminal is not holding conflicting local zrok state

### `zrok` not found on Windows

Install `zrok` and ensure one of: `zrok` in `PATH`, `zrok.exe` in project dir, or `ZROK_BIN` set.

## Files

| File | Description |
|------|-------------|
| `zrok_server.py` | Kaggle-side startup script |
| `zrok_client.py` | Windows client script |
| `utils.py` | Shared Zrok API wrapper |
| `setup_ssh.sh` | Self-contained SSH server bootstrap (called by server) |
| `setup_devtools.sh` | Optional Kaggle-side devtools bootstrap |
| `prepare_client.bat` | First-time Windows setup helper |
| `start_client.bat` | Daily Windows connect launcher |
