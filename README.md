# Kaggle Remote zrok

- 中文说明：[`README.zh-CN.md`](./README.zh-CN.md)
- English: [`README.md`](./README.md)

Use Kaggle as a temporary remote Linux machine and connect from **Windows or macOS** through `zrok` and SSH.

`zrok` is intentionally not committed. Install it first:

- https://docs.zrok.io/docs/guides/install/

## Prerequisites

- A Kaggle notebook with internet enabled
- Your zrok account token
- Python 3.11+
- `zrok` available in `PATH`, or `ZROK_BIN` set to the full executable path
- VS Code if you want the default editor-launch flow
- VS Code Remote - SSH if you want the default remote-open experience

### Platform notes

- **Windows:** `start_client.bat` and `prepare_client.bat` remain the main entrypoints.
- **macOS:** use `./start_client.sh` and `./prepare_client.sh`.
- **SSH-only:** supported as an explicit opt-out on both platforms; default behavior still opens VS Code after the tunnel is ready.
- **macOS zrok support:** macOS support relies on an already installed `zrok` binary available via `PATH` or `ZROK_BIN`. This project does **not** auto-install `zrok` on macOS.

## Init Flow

This only needs to be done once for the same Kaggle notebook storage.

Kaggle persistent state is stored in:

```text
/kaggle/working/.kaggle_remote_zrok
```

### Step 1: Prepare on your local machine

#### Windows

Run:

```bat
prepare_client.bat
```

#### macOS

Run:

```bash
./prepare_client.sh
```

This step:

- caches your zrok token in `~/.kaggle_remote_zrok/zrok_token.txt`
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

> Warning: notebook cells, outputs, and shell history may retain token values. Prefer pasting secrets carefully, avoid sharing notebook history/output, and rotate the token if you expose it accidentally.

This init step:

- saves the zrok token
- saves the SSH public key
- captures the current Kaggle notebook environment for later SSH sessions
- starts `sshd`
- starts `setup_devtools.sh` in the background
- starts the private zrok share

You do not need to run extra prep like `chmod +x ...` or `printenv > /kaggle/working/kaggle_env_vars.txt` manually. `zrok_server.py` captures the environment before calling `setup_ssh.sh`, and the environment dump is kept in `/kaggle/working` for later SSH sessions.

> Warning: environment snapshots may contain sensitive values. Treat `/kaggle/working/kaggle_env_vars.txt` and related notebook storage as sensitive, and do not share them casually.

The SSH bootstrap also tolerates Kaggle service-management quirks where `service ssh` may print success but still return a non-zero status.
If `setup_ssh.sh` exits non-zero but local SSH is already listening on port `22`, `zrok_server.py` continues instead of aborting the whole startup.

### Step 3: Keep Kaggle running

Do not stop the Kaggle cell after the share starts.

### Step 4: Devtools bootstrap starts automatically

`zrok_server.py` launches `setup_devtools.sh` in the background automatically.

That script:

- installs `nodejs` and `npm` if needed
- installs `@openai/codex`
- adds the persistent npm bin directory to root's PATH
- keeps a fallback watcher for remote VS Code extension installs

Logs are written to:

```text
/kaggle/working/.kaggle_remote_zrok/devtools-launch.log
/kaggle/working/.kaggle_remote_zrok/devtools.log
```

If you want to skip it for one run:

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start --no-devtools
```

If you want to rerun it manually:

```bash
%cd /kaggle/working/kz
!bash setup_devtools.sh
```

### Step 5: Connect from your local machine

#### Windows default flow

```bat
start_client.bat
```

#### macOS default flow

```bash
./start_client.sh
```

If everything is correct, the client will:

- find the `kaggle_server` share
- open local access on `127.0.0.1:9191`
- update your local SSH config for host `kaggle_client`
- on Windows, keep the current best-effort VS Code Remote SSH settings update
- open VS Code Remote SSH by default

## SSH-only mode

If you want the client to stop after the SSH tunnel and local SSH config are ready, use the explicit SSH-only option.

#### Windows

```bat
start_client.bat --ssh-only
```

#### macOS

```bash
./start_client.sh --ssh-only
```

#### Direct Python CLI

```bash
python zrok_client.py start --ssh-only
```

`--no-vscode` is also supported as an alias.

In SSH-only mode, the client still:

- resolves the zrok share
- opens the local tunnel
- writes the `kaggle_client` SSH host entry

It simply skips launching VS Code.

### SSH-only connection examples

After the tunnel is ready, you can connect directly with normal SSH tools.

#### Open an interactive shell

```bash
ssh kaggle_client
```

#### Run one command remotely

```bash
ssh kaggle_client "cd /kaggle/working && pwd && ls"
```

#### Copy a file from the Kaggle side to local

```bash
scp kaggle_client:/kaggle/working/your-file.txt ./your-file.txt
```

#### Upload a local file to Kaggle

```bash
scp ./local-file.txt kaggle_client:/kaggle/working/local-file.txt
```

If you prefer a different host name, replace `kaggle_client` with the value you passed through `--name`.

## Later Use Flow

After init has succeeded once, each later session is only two steps.

### Step 1: Start Kaggle side

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

This reuses the saved token and saved SSH auth config from `/kaggle/working/.kaggle_remote_zrok`.
It also refreshes `/kaggle/working/kaggle_env_vars.txt` automatically before starting SSH.
It also launches `setup_devtools.sh` in the background unless you pass `--no-devtools`.

### Step 2: Start the local client

#### Windows

```bat
start_client.bat
```

#### macOS

```bash
./start_client.sh
```

That is the normal daily usage flow.

## Wrapper scripts

### `prepare_client.bat` / `prepare_client.sh`

Use this only during initialization.

It:

- caches your token
- creates `~/.ssh/kaggle_rsa` if needed
- prints the Kaggle init command

### `start_client.bat` / `start_client.sh`

Use this after the Kaggle server is already running.

Token lookup order:

1. `ZROK_TOKEN`
2. `~/.kaggle_remote_zrok/zrok_token.txt`
3. interactive prompt

`zrok` lookup order:

1. `zrok` from `PATH`
2. local `zrok` / `zrok.exe` in the project directory
3. `ZROK_BIN`

To clear the saved token, delete:

```text
~/.kaggle_remote_zrok/zrok_token.txt
```

> Warning: this token cache file is plaintext local state. Treat it as sensitive, avoid sharing it, and keep normal user-only filesystem permissions on it.

## Direct Python entrypoints

If you prefer not to use the wrapper scripts:

```bash
python zrok_client.py prepare
python zrok_client.py start
python zrok_client.py start --ssh-only
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

> Warning: the generated SSH config disables strict host verification (`StrictHostKeyChecking no` and `UserKnownHostsFile /dev/null`) for convenience. This is fine for short-lived trusted workflows, but it is not appropriate for hostile or untrusted networks.

## Password-based init

If you want password login instead of key login:

> Warning: `--password "0"` below is only a minimal example. Use a strong password if you enable password-based access.

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

## Useful Variants

Use a hosted `authorized_keys` file:

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_keys_url "https://example.com/authorized_keys"
```

Use password auth:

> Warning: do not reuse weak demo passwords in real sessions.

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

### `zrok` not found

Install `zrok` and ensure one of these is true:

- `zrok` is in `PATH`
- `zrok` or `zrok.exe` is in the project directory
- `ZROK_BIN` points to the full executable path

### VS Code did not open automatically

This no longer blocks the core connection flow.
If the tunnel and SSH config were created successfully, connect manually with host `kaggle_client`.

On macOS, automatic launch prefers `code --remote ...` and otherwise falls back to `open -a "Visual Studio Code" --args ...`.

## Files

- `zrok_server.py`: Kaggle-side startup script
- `zrok_client.py`: shared local client script
- `prepare_client.bat`: Windows first-time local setup helper
- `start_client.bat`: Windows connect launcher
- `prepare_client.sh`: macOS first-time local setup helper
- `start_client.sh`: macOS connect launcher
- `setup_ssh.sh`: SSH server bootstrap for Kaggle
- `setup_devtools.sh`: optional Kaggle-side devtools bootstrap
