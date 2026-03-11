# Kaggle Remote zrok

[English](README.md)

通过 [zrok](https://zrok.io) 私有隧道，从 Windows 以 SSH 方式连接到 Kaggle Notebook，实现远程开发。

## 前置条件

| 需求 | 说明 |
|---|---|
| Kaggle Notebook | 需开启 Internet |
| zrok 账号 | 在 [zrok.io](https://zrok.io) 注册获取 token |
| Windows + Python 3.11+ | — |
| VS Code + Remote SSH 扩展 | — |
| `zrok` 可执行文件 | 在 `PATH` 中、项目目录下、或通过 `ZROK_BIN` 环境变量指定 |

---

## 快速开始（首次使用）

### 1. Windows 端准备

```bat
prepare_client.bat
```

执行后会：
- 缓存你的 zrok token 到本地
- 生成 `~/.ssh/kaggle_rsa` 密钥对（若不存在）
- 打印出需要粘贴到 Kaggle 的初始化命令

### 2. 在 Kaggle 中初始化

将打印出的命令粘贴到 Kaggle Notebook 的代码格中执行：

```bash
!git clone https://github.com/MuYuan88ya/kz.git /kaggle/working/kz
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "你的TOKEN" --authorized_key "你的公钥"
```

> **执行流程：** 保存配置 → 安装 SSH → 启动 devtools → 打开私有隧道。

### 3. 从 Windows 连接

```bat
start_client.bat
```

> **执行流程：** 查找隧道 → 打开本地 9191 端口 → 写入 SSH 配置 → 启动 VS Code。

### 4. 保持 Kaggle 运行

**不要停止** Kaggle 的代码格 —— 停止后隧道会断开。

---

## 日常使用（初始化之后）

只需两步：

```bash
# Kaggle 代码格
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

```bat
REM Windows 端
start_client.bat
```

---

## 可选变体

**密码登录**（不使用 SSH 密钥）：

```bash
!python3 zrok_server.py --init --token "TOKEN" --password "你的密码"
```

**跳过 devtools 安装**：

```bash
!python3 zrok_server.py --start --no-devtools
```

**自定义环境名称**：

```bash
!python3 zrok_server.py --init --token "TOKEN" --name "my_server"
```

**从 URL 获取 authorized_keys**：

```bash
!python3 zrok_server.py --init --token "TOKEN" --authorized_keys_url "https://example.com/keys"
```

---

## 工作原理

```
┌─────────────────────┐        zrok 私有隧道         ┌─────────────────────┐
│     Windows PC      │◄────────────────────────────►│   Kaggle Notebook   │
│                     │    TCP 隧道  本地端口 9191     │                     │
│  start_client.bat   │                               │  zrok_server.py     │
│  └─ zrok_client.py  │                               │  └─ setup_ssh.sh    │
│     └─ VS Code SSH  │                               │  └─ setup_devtools  │
└─────────────────────┘                               └─────────────────────┘
```

---

## 生成的 SSH 配置

客户端会自动写入 `~/.ssh/config`：

```
Host kaggle_client
    HostName 127.0.0.1
    User root
    Port 9191
    IdentityFile ~/.ssh/kaggle_rsa    # 若密钥存在
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

---

## 持久化存储

| 位置 | 用途 |
|---|---|
| `/kaggle/working/.kaggle_remote_zrok/` | 服务端配置、保存的密钥 |
| `/kaggle/working/kaggle_env_vars.txt` | 为 SSH 会话捕获的环境变量 |
| `%USERPROFILE%\.kaggle_remote_zrok\` | 缓存的 zrok token（Windows） |

---

## Token 与 zrok 查找顺序

**Token**（Windows）：`ZROK_TOKEN` 环境变量 → `%USERPROFILE%\.kaggle_remote_zrok\zrok_token.txt` → 手动输入。

**zrok 可执行文件**（Windows）：`PATH` → 项目目录下的 `zrok.exe` → `ZROK_BIN` 环境变量。

---

## 常见问题

| 错误信息 | 原因与解决 |
|---|---|
| `kaggle_server environment not found` | Kaggle 代码格未运行，或服务端尚未启动完成 |
| `enableUnauthorized` | token 无效，或本地 zrok 状态冲突（运行 `zrok disable` 重置） |
| `zrok not found` | 未安装 zrok，确保满足前置条件 |

---

## 项目文件

| 文件 | 运行环境 | 说明 |
|---|---|---|
| `zrok_server.py` | Kaggle | 服务端入口：配置、SSH、隧道 |
| `zrok_client.py` | Windows | 客户端入口：查找隧道、连接 |
| `utils.py` | 通用 | 共享的 `Zrok` API 封装 |
| `setup_ssh.sh` | Kaggle | 自包含的 SSH 服务启动脚本 |
| `setup_devtools.sh` | Kaggle | Codex CLI 与 VS Code 扩展安装器 |
| `prepare_client.bat` | Windows | 首次使用的准备脚本 |
| `start_client.bat` | Windows | 日常连接启动器 |
