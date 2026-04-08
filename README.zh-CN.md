# Kaggle Remote zrok

- 中文说明：[`README.zh-CN.md`](./README.zh-CN.md)
- English: [`README.md`](./README.md)

把 Kaggle 当作临时远程 Linux 机器，通过 `zrok` 和 SSH 从 **Windows 或 macOS** 连接进去。

仓库里**不会**提交 `zrok` 可执行文件，请先自行安装：

- https://docs.zrok.io/docs/guides/install/

## 前置要求

- 一个开启了网络的 Kaggle Notebook
- 你的 zrok 账号 token
- Python 3.11+
- `zrok` 已在 `PATH` 中，或者通过 `ZROK_BIN` 指向完整可执行文件路径
- 如果你想使用默认“连接后自动打开编辑器”的流程，需要安装 VS Code
- 如果你想使用默认 Remote SSH 打开体验，需要安装 VS Code Remote - SSH

### 平台说明

- **Windows：**主入口仍然是 `start_client.bat` 和 `prepare_client.bat`
- **macOS：**使用 `./start_client.sh` 和 `./prepare_client.sh`
- **SSH-only：**Windows 和 macOS 都支持显式开启；默认行为仍然是在隧道准备好之后自动打开 VS Code
- **macOS 上的 zrok：**macOS 支持依赖于你本地已经安装好的 `zrok`，并且它需要能通过 `PATH` 或 `ZROK_BIN` 被找到；本项目**不会**在 macOS 上自动安装 `zrok`

## 初始化流程

对于同一个 Kaggle Notebook 存储，这个流程通常只需要做一次。

Kaggle 的持久化状态保存在：

```text
/kaggle/working/.kaggle_remote_zrok
```

### 第 1 步：在本地机器上执行准备

#### Windows

运行：

```bat
prepare_client.bat
```

#### macOS

运行：

```bash
./prepare_client.sh
```

这个步骤会：

- 把你的 zrok token 缓存到 `~/.kaggle_remote_zrok/zrok_token.txt`
- 如果 `~/.ssh/kaggle_rsa` 不存在，就自动创建
- 打印你的 SSH 公钥
- 打印你应该粘贴到 Kaggle 里的初始化命令

这个步骤**不会**连接到 Kaggle。

### 第 2 步：在 Kaggle 里初始化

把上一步打印出来的命令粘贴到 Kaggle 单元格中执行。

典型命令如下：

```bash
!git clone https://github.com/MuYuan88ya/kz.git /kaggle/working/kz
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_key "PASTE_YOUR_PUBLIC_KEY_HERE"
```

> 警告：Notebook 单元格、输出内容以及 shell 历史都可能保留 token。请谨慎粘贴密钥信息，不要随意分享 Notebook 历史/输出；如果误泄露，建议立即轮换 token。

这一步会：

- 保存 zrok token
- 保存 SSH 公钥
- 捕获当前 Kaggle Notebook 的环境变量，供之后 SSH 会话复用
- 启动 `sshd`
- 在后台启动 `setup_devtools.sh`
- 启动 private zrok share

你不需要手动再做额外预处理，例如 `chmod +x ...` 或 `printenv > /kaggle/working/kaggle_env_vars.txt`。`zrok_server.py` 会在调用 `setup_ssh.sh` 前自动抓取环境，并把环境信息保存在 `/kaggle/working`，以便后续 SSH 会话使用。

> 警告：环境快照里可能包含敏感信息。请把 `/kaggle/working/kaggle_env_vars.txt` 以及相关 Notebook 存储视为敏感内容，不要随意共享。

SSH 启动逻辑还兼容 Kaggle 上某些服务管理异常：即使 `service ssh` 输出看起来成功，但返回码非 0，也不会直接失败。
如果 `setup_ssh.sh` 返回非 0，但本地 SSH 已经在 `22` 端口监听，`zrok_server.py` 也会继续执行，而不会整体中断启动。

### 第 3 步：保持 Kaggle 运行中

share 启动之后，不要停止 Kaggle 单元格。

### 第 4 步：devtools 会自动启动

`zrok_server.py` 会自动在后台启动 `setup_devtools.sh`。

这个脚本会：

- 按需安装 `nodejs` 和 `npm`
- 安装 `@openai/codex`
- 把持久化 npm bin 目录加入 root 的 PATH
- 保留一个用于远程 VS Code 扩展安装的兜底 watcher

日志写入到：

```text
/kaggle/working/.kaggle_remote_zrok/devtools-launch.log
/kaggle/working/.kaggle_remote_zrok/devtools.log
```

如果你某次启动想跳过它：

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start --no-devtools
```

如果你想手动重跑：

```bash
%cd /kaggle/working/kz
!bash setup_devtools.sh
```

### 第 5 步：从本地机器连接

#### Windows 默认流程

```bat
start_client.bat
```

#### macOS 默认流程

```bash
./start_client.sh
```

如果一切正常，客户端会：

- 找到 `kaggle_server` share
- 在本地打开 `127.0.0.1:9191`
- 更新你本机上的 SSH config，写入 `kaggle_client` host
- 在 Windows 上保留当前 best-effort 的 VS Code Remote SSH 设置更新行为
- 默认自动打开 VS Code Remote SSH

## SSH-only 模式

如果你希望客户端在 SSH 隧道和本地 SSH 配置准备好之后**不要自动打开 VS Code**，可以显式使用 SSH-only 模式。

#### Windows

```bat
start_client.bat --ssh-only
```

#### macOS

```bash
./start_client.sh --ssh-only
```

#### 直接使用 Python CLI

```bash
python zrok_client.py start --ssh-only
```

`--no-vscode` 也可以作为别名使用。

在 SSH-only 模式下，客户端仍然会：

- 解析 zrok share
- 打开本地隧道
- 写入 `kaggle_client` SSH host 配置

只是不会自动启动 VS Code。

## 日常使用流程

如果初始化已经成功做过一次，之后的日常使用通常只需要两步。

### 第 1 步：启动 Kaggle 侧

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --start
```

它会复用保存在 `/kaggle/working/.kaggle_remote_zrok` 里的 token 和 SSH 鉴权配置。
同时也会在启动 SSH 前自动刷新 `/kaggle/working/kaggle_env_vars.txt`。
除非你传入 `--no-devtools`，否则它还会在后台启动 `setup_devtools.sh`。

### 第 2 步：启动本地客户端

#### Windows

```bat
start_client.bat
```

#### macOS

```bash
./start_client.sh
```

这就是日常使用的标准流程。

## 包装脚本

### `prepare_client.bat` / `prepare_client.sh`

只在初始化时使用。

它会：

- 缓存 token
- 如有需要创建 `~/.ssh/kaggle_rsa`
- 打印 Kaggle 初始化命令

### `start_client.bat` / `start_client.sh`

在 Kaggle 服务端已经启动后使用。

Token 查找顺序：

1. `ZROK_TOKEN`
2. `~/.kaggle_remote_zrok/zrok_token.txt`
3. 交互式输入

`zrok` 查找顺序：

1. `PATH` 中的 `zrok`
2. 项目目录下的本地 `zrok` / `zrok.exe`
3. `ZROK_BIN`

如果你想清除保存的 token，请删除：

```text
~/.kaggle_remote_zrok/zrok_token.txt
```

> 警告：这个 token 缓存文件是明文保存在本地的敏感状态，请不要随意共享，并尽量保持只有当前用户可读写。

## 直接使用 Python 入口

如果你不想使用包装脚本，也可以直接运行：

```bash
python zrok_client.py prepare
python zrok_client.py start
python zrok_client.py start --ssh-only
```

## 自动生成的 SSH 配置

客户端会写入一个类似这样的 host：

```sshconfig
Host kaggle_client
    HostName 127.0.0.1
    User root
    Port 9191
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

如果 `~/.ssh/kaggle_rsa` 存在，就会使用基于密钥的登录。

如果不存在，就会回退到密码认证。

> 警告：为了使用方便，自动生成的 SSH 配置关闭了严格主机校验（`StrictHostKeyChecking no` 和 `UserKnownHostsFile /dev/null`）。这适合短期、可信环境，但不适合不可信网络。

## 密码方式初始化

如果你想使用密码登录，而不是密钥登录：

> 警告：下面的 `--password "0"` 只是最小示例。启用密码访问时请换成强密码。

```bash
%cd /kaggle/working/kz
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

## 常用变体

使用托管的 `authorized_keys` 文件：

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --authorized_keys_url "https://example.com/authorized_keys"
```

使用密码认证：

> 警告：真实使用时不要复用弱口令示例。

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --password "0"
```

修改环境名：

```bash
!python3 zrok_server.py --init --token "YOUR_ZROK_TOKEN" --name "kaggle_server"
!python3 zrok_server.py --start --name "kaggle_server"
```

## 故障排查

### `kaggle_server environment not found`

- Kaggle 单元格没有在运行
- 服务端进程还没有完成 private share 创建
- 你在从未执行过 `--init` 的情况下直接运行了 `--start`

### `enableUnauthorized`

- 确认 token 是真实的 zrok account token
- 确认没有其他终端持有冲突的本地 zrok 状态

### 找不到 `zrok`

安装 `zrok`，并确保至少满足以下一项：

- `zrok` 在 `PATH` 中
- 项目目录里存在 `zrok` 或 `zrok.exe`
- `ZROK_BIN` 指向完整可执行文件路径

### VS Code 没有自动打开

这已经不再阻塞核心连接流程。
如果隧道和 SSH 配置已经成功创建，你仍然可以手动使用 `kaggle_client` 这个 host 连接。

在 macOS 上，自动启动会优先尝试 `code --remote ...`；如果不可用，则回退到 `open -a "Visual Studio Code" --args ...`。

## 文件说明

- `zrok_server.py`：Kaggle 侧启动脚本
- `zrok_client.py`：共享的本地客户端脚本
- `prepare_client.bat`：Windows 首次本地准备脚本
- `start_client.bat`：Windows 连接启动脚本
- `prepare_client.sh`：macOS 首次本地准备脚本
- `start_client.sh`：macOS 连接启动脚本
- `setup_ssh.sh`：Kaggle 的 SSH 服务启动脚本
- `setup_devtools.sh`：可选的 Kaggle devtools 启动脚本
