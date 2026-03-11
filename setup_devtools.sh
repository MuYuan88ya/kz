#!/bin/bash

set -euo pipefail

STATE_DIR="/kaggle/working/.kaggle_remote_zrok"
NPM_PREFIX="$STATE_DIR/npm-global"
LOG_FILE="$STATE_DIR/devtools.log"
WATCH_SCRIPT="$STATE_DIR/install_vscode_extensions.sh"
WATCH_PID_FILE="$STATE_DIR/install_vscode_extensions.pid"
SHELL_RC="$HOME/.bashrc"

EXTENSIONS=(
    "ms-python.python"
    "ms-toolsai.jupyter"
    "openai.chatgpt"
)

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

ensure_state_dir() {
    mkdir -p "$STATE_DIR"
    touch "$LOG_FILE"
}

ensure_node_and_npm() {
    if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
        log "node: $(node --version)"
        log "npm: $(npm --version)"
        return
    fi

    log "Installing nodejs and npm..."
    sudo apt-get update
    sudo apt-get install -y nodejs npm
    log "node: $(node --version)"
    log "npm: $(npm --version)"
}

ensure_persistent_npm_prefix() {
    mkdir -p "$NPM_PREFIX"
    export PATH="$NPM_PREFIX/bin:$PATH"

    if ! grep -Fq '# kaggle-remote-zrok devtools path' "$SHELL_RC" 2>/dev/null; then
        cat >>"$SHELL_RC" <<EOF

# kaggle-remote-zrok devtools path
export PATH="$NPM_PREFIX/bin:\$PATH"
EOF
    fi
}

ensure_codex_cli() {
    export PATH="$NPM_PREFIX/bin:$PATH"

    if [ -x "$NPM_PREFIX/bin/codex" ]; then
        log "Codex CLI already installed: $("$NPM_PREFIX/bin/codex" --version)"
        return
    fi

    log "Installing Codex CLI..."
    npm install -g @openai/codex --prefix "$NPM_PREFIX"
    log "Codex CLI installed: $("$NPM_PREFIX/bin/codex" --version)"
}

write_watcher_script() {
    cat >"$WATCH_SCRIPT" <<'EOF'
#!/bin/bash

set -euo pipefail

STATE_DIR="/kaggle/working/.kaggle_remote_zrok"
LOG_FILE="$STATE_DIR/devtools.log"
MARKER_DIR="$STATE_DIR/vscode-extension-markers"

EXTENSIONS=(
    "ms-python.python"
    "ms-toolsai.jupyter"
    "openai.chatgpt"
)

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG_FILE"
}

mkdir -p "$MARKER_DIR"

for _ in $(seq 1 360); do
    found_server=0
    for code_server in "$HOME"/.vscode-server/bin/*/bin/code-server; do
        if [ ! -x "$code_server" ]; then
            continue
        fi

        found_server=1
        commit_dir="$(basename "$(dirname "$(dirname "$code_server")")")"
        marker_file="$MARKER_DIR/$commit_dir.done"

        if [ -f "$marker_file" ]; then
            continue
        fi

        log "Installing remote VS Code extensions for commit $commit_dir"
        for extension in "${EXTENSIONS[@]}"; do
            "$code_server" --install-extension "$extension" --force >>"$LOG_FILE" 2>&1
        done
        touch "$marker_file"
        log "Finished remote VS Code extension install for commit $commit_dir"
    done

    if [ "$found_server" -eq 1 ]; then
        exit 0
    fi

    sleep 5
done

log "Timed out waiting for ~/.vscode-server to appear"
exit 0
EOF

    chmod +x "$WATCH_SCRIPT"
}

start_watcher() {
    if [ -f "$WATCH_PID_FILE" ]; then
        old_pid="$(cat "$WATCH_PID_FILE" 2>/dev/null || true)"
        if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" 2>/dev/null; then
            log "VS Code extension watcher is already running with PID $old_pid"
            return
        fi
    fi

    log "Starting VS Code extension watcher..."
    nohup bash "$WATCH_SCRIPT" >>"$LOG_FILE" 2>&1 &
    echo $! >"$WATCH_PID_FILE"
    log "VS Code extension watcher started with PID $(cat "$WATCH_PID_FILE")"
}

show_summary() {
    log "Python: $(python3 --version 2>/dev/null || echo unavailable)"
    log "Jupyter: $(jupyter --version 2>/dev/null | head -n 1 || echo unavailable)"
    log "Codex CLI: $("$NPM_PREFIX/bin/codex" --version 2>/dev/null || echo unavailable)"
    log "Devtools log: $LOG_FILE"
}

main() {
    ensure_state_dir
    ensure_node_and_npm
    ensure_persistent_npm_prefix
    ensure_codex_cli
    write_watcher_script
    start_watcher
    show_summary
}

main "$@"
