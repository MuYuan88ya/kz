# Kaggle Remote zrok

[中文文档](README_CN.md)

Connect to a Kaggle notebook over SSH from Windows using [zrok](https://zrok.io) as a private tunnel.

## Prerequisites

| Requirement | Notes |
|---|---|
| Kaggle notebook | Internet must be enabled |
| zrok account | Get a token at [zrok.io](https://zrok.io) |
| Windows + Python 3.11+ | — |
| VS Code + Remote SSH extension | — |
| `zrok` binary | In `PATH`, project dir, or via `ZROK_BIN` env var |

---

## Quick Start (First Time)

### 1. Prepare on Windows

```bat
prepare_client.bat
```

This will:
- Cache your zrok token locally
- Generate `~/.ssh/kaggle_rsa` keypair (if not exists)
- Print the Kaggle init command to paste

### 2. Initialize on Kaggle

Paste into a Kaggle notebook cell:

```bash
!git clone https://github.com/MuYuan88ya/kz.git /kaggle/working/kz
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_TOKEN" --authorized_key "YOUR_PUBLIC_KEY"
```

> **What happens:** saves config → installs SSH → starts devtools → opens private tunnel.

### 3. Connect from Windows

```bat
start_client.bat
```

> **What happens:** finds tunnel → opens local port 9191 → writes SSH config → launches VS Code.

### 4. Keep Kaggle running

Do **not** stop the Kaggle cell — the tunnel dies when the cell stops.

---

## Daily Use (After Init)

Only two steps:

```bash
# Kaggle cell
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

```bat
REM Windows
start_client.bat
```

---

## Variants

**Password login** (instead of SSH key):

```bash
!python3 zrok_server.py --init --token "YOUR_TOKEN" --password "your_password"
```

**Skip devtools bootstrap**:

```bash
!python3 zrok_server.py --start --no-devtools
```

**Custom environment name**:

```bash
!python3 zrok_server.py --init --token "YOUR_TOKEN" --name "my_server"
```

**Authorized keys from URL**:

```bash
!python3 zrok_server.py --init --token "YOUR_TOKEN" --authorized_keys_url "https://example.com/keys"
```

---

## How It Works

```
┌─────────────────────┐          zrok tunnel          ┌─────────────────────┐
│     Windows PC      │◄────────────────────────────►│   Kaggle Notebook   │
│                     │    private TCP on port 9191    │                     │
│  start_client.bat   │                               │  zrok_server.py     │
│  └─ zrok_client.py  │                               │  └─ setup_ssh.sh    │
│     └─ VS Code SSH  │                               │  └─ setup_devtools  │
└─────────────────────┘                               └─────────────────────┘
```

---

## Generated SSH Config

The client writes this to `~/.ssh/config`:

```
Host kaggle_client
    HostName 127.0.0.1
    User root
    Port 9191
    IdentityFile ~/.ssh/kaggle_rsa    # if key exists
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    Compression yes
    ServerAliveInterval 15
    ServerAliveCountMax 3
```

---

## High Latency Network Optimization (Reduce Typing Lag)

If you are connecting to a Kaggle server (usually in the US) from far away, the physical network latency (often 200ms+) combined with the tunnel routing can cause a noticeable lag when typing in VS Code.

To **drastically improve** your typing experience, it is highly recommended to enable **Local Echo** in the VS Code terminal:

1. Open VS Code Settings (`Ctrl + ,` or `Cmd + ,`)
2. Search for `terminal.integrated.localEchoEnabled`
3. Set it to `on` or `auto`

When enabled, your keystrokes will instantly appear locally in gray while waiting for the server to acknowledge them, eliminating the subjective feeling of typing lag. Note that the generated SSH config also includes `Compression` to accelerate text transfer and `ServerAlive` settings to prevent drops on unstable connections.

---

## Persistent State

| Location | Purpose |
|---|---|
| `/kaggle/working/.kaggle_remote_zrok/` | Server config, saved keys |
| `/kaggle/working/kaggle_env_vars.txt` | Captured env vars for SSH sessions |
| `%USERPROFILE%\.kaggle_remote_zrok\` | Cached zrok token (Windows) |

---

## Token & Binary Lookup

**Token** (Windows): `ZROK_TOKEN` env → `%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt` → prompt.

**zrok binary** (Windows): `PATH` → project dir `zrok.exe` → `ZROK_BIN` env.

---

## Troubleshooting

| Error | Cause & Fix |
|---|---|
| `kaggle_server environment not found` | Kaggle cell isn't running, or server hasn't finished starting |
| `enableUnauthorized` | Invalid token, or stale local zrok state (`zrok disable` to reset) |
| `zrok not found` | Install zrok and ensure it's accessible (see Prerequisites) |

---

## Files

| File | Runs On | Description |
|---|---|---|
| `zrok_server.py` | Kaggle | Server entry point: config, SSH, tunnel |
| `zrok_client.py` | Windows | Client entry point: find tunnel, connect |
| `utils.py` | Both | Shared `Zrok` API wrapper |
| `setup_ssh.sh` | Kaggle | Self-contained SSH server bootstrap |
| `setup_devtools.sh` | Kaggle | Codex CLI + VS Code extensions installer |
| `prepare_client.bat` | Windows | First-time setup helper |
| `start_client.bat` | Windows | Daily connect launcher |
