#!/bin/bash

set -euo pipefail

STATE_DIR="/kaggle/working/.kaggle_remote_zrok"
NPM_PREFIX="$STATE_DIR/npm-global"
NPM_CACHE_DIR="$STATE_DIR/npm-cache"
NODE_RUNTIME_DIR="$STATE_DIR/node-runtime"
NODE_CURRENT_LINK="$NODE_RUNTIME_DIR/current"
NODE_MAJOR="${NODE_MAJOR:-22}"
NODE_PLATFORM="${NODE_PLATFORM:-linux-x64}"
LOG_FILE="$STATE_DIR/devtools.log"
WATCH_SCRIPT="$STATE_DIR/install_vscode_extensions.sh"
WATCH_PID_FILE="$STATE_DIR/install_vscode_extensions.pid"
SHELL_RC="$HOME/.bashrc"
PROFILE_FILE="$HOME/.profile"
PROFILE_SNIPPET="$STATE_DIR/devtools-path.sh"
CODEX_JS="$NPM_PREFIX/lib/node_modules/@openai/codex/bin/codex.js"
WATCH_MODE="${DEVTOOLS_WATCH_MODE:-background}"

EXTENSIONS=(
    "ms-python.python"
    "ms-toolsai.jupyter"
    "openai.chatgpt"
)

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

ensure_state_dir() {
    mkdir -p "$STATE_DIR" "$NPM_PREFIX" "$NPM_CACHE_DIR" "$NODE_RUNTIME_DIR"
    touch "$LOG_FILE"
}

fetch_to_stdout() {
    local url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url"
        return
    fi

    if command -v wget >/dev/null 2>&1; then
        wget -qO- "$url"
        return
    fi

    log "Neither curl nor wget is available for downloading $url"
    exit 1
}

download_file() {
    local url="$1"
    local destination="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$url" -o "$destination"
        return
    fi

    if command -v wget >/dev/null 2>&1; then
        wget -qO "$destination" "$url"
        return
    fi

    log "Neither curl nor wget is available for downloading $url"
    exit 1
}

use_cached_node_runtime() {
    if [ -x "$NODE_CURRENT_LINK/bin/node" ] && [ -x "$NODE_CURRENT_LINK/bin/npm" ]; then
        export PATH="$NODE_CURRENT_LINK/bin:$PATH"
        log "Using cached Node runtime: $(node --version)"
        log "Using cached npm: $(npm --version)"
        return 0
    fi

    return 1
}

install_cached_node_runtime() {
    local base_url="https://nodejs.org/dist/latest-v${NODE_MAJOR}.x"
    local archive_name
    local archive_path
    local extracted_dir

    archive_name="$(fetch_to_stdout "$base_url/SHASUMS256.txt" | awk "/${NODE_PLATFORM}\\.tar\\.xz$/ { print \$2; exit }")"
    if [ -z "$archive_name" ]; then
        log "Could not resolve a Node archive for ${NODE_PLATFORM}"
        return 1
    fi

    archive_path="$NODE_RUNTIME_DIR/$archive_name"
    extracted_dir="$NODE_RUNTIME_DIR/${archive_name%.tar.xz}"

    if [ ! -f "$archive_path" ]; then
        log "Downloading persistent Node runtime $archive_name"
        download_file "$base_url/$archive_name" "$archive_path"
    else
        log "Reusing cached Node archive $archive_name"
    fi

    if [ ! -x "$extracted_dir/bin/node" ] || [ ! -x "$extracted_dir/bin/npm" ]; then
        log "Extracting Node runtime into $extracted_dir"
        rm -rf "$extracted_dir"
        tar -xJf "$archive_path" -C "$NODE_RUNTIME_DIR"
    fi

    ln -sfn "$extracted_dir" "$NODE_CURRENT_LINK"
    export PATH="$NODE_CURRENT_LINK/bin:$PATH"
    log "Node runtime ready from cache: $(node --version)"
    log "npm ready from cache: $(npm --version)"
}

ensure_node_and_npm() {
    if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
        log "Using system node: $(node --version)"
        log "Using system npm: $(npm --version)"
        return
    fi

    if use_cached_node_runtime; then
        return
    fi

    log "System node/npm not found; preparing persistent Node runtime..."
    if install_cached_node_runtime; then
        return
    fi

    log "Falling back to apt-get install for nodejs and npm..."
    sudo apt-get update
    sudo apt-get install -y nodejs npm
    log "Using fallback node: $(node --version)"
    log "Using fallback npm: $(npm --version)"
}

ensure_persistent_npm_prefix() {
    export npm_config_cache="$NPM_CACHE_DIR"
    export PATH="$NPM_PREFIX/bin:$PATH"
    node_bin_dir="$(dirname "$(command -v node)")"

    cat >"$PROFILE_SNIPPET" <<EOF
export PATH="$node_bin_dir:$NPM_PREFIX/bin:\$PATH"
export npm_config_cache="$NPM_CACHE_DIR"
EOF

    if ! grep -Fq '# kaggle-remote-zrok devtools path' "$SHELL_RC" 2>/dev/null; then
        cat >>"$SHELL_RC" <<EOF

# kaggle-remote-zrok devtools path
[ -f "$PROFILE_SNIPPET" ] && source "$PROFILE_SNIPPET"
EOF
    fi

    if ! grep -Fq "$PROFILE_SNIPPET" "$PROFILE_FILE" 2>/dev/null; then
        cat >>"$PROFILE_FILE" <<EOF

[ -f "$PROFILE_SNIPPET" ] && . "$PROFILE_SNIPPET"
EOF
    fi

    export PATH="$node_bin_dir:$NPM_PREFIX/bin:$PATH"
}

ensure_codex_cli() {
    export PATH="$NPM_PREFIX/bin:$PATH"

    if [ -x "$NPM_PREFIX/bin/codex" ] && [ -f "$CODEX_JS" ]; then
        if head -n 1 "$CODEX_JS" | grep -Fq '#!/bin/bash'; then
            log "Detected a broken Codex CLI entrypoint, reinstalling package..."
            npm install -g @openai/codex --prefix "$NPM_PREFIX" --force
        else
            log "Codex CLI already installed: $("$NPM_PREFIX/bin/codex" --version)"
            return
        fi
    else
        log "Installing Codex CLI into persistent npm prefix..."
        npm install -g @openai/codex --prefix "$NPM_PREFIX"
    fi

    if [ ! -f "$CODEX_JS" ]; then
        log "Codex entrypoint not found after install: $CODEX_JS"
        return
    fi

    install_codex_wrapper
    log "Codex CLI installed: $(codex --version)"
}

install_codex_wrapper() {
    node_path="$(command -v node)"
    if [ ! -x "$node_path" ]; then
        log "node executable not found after install"
        exit 1
    fi

    if [ ! -f "$CODEX_JS" ]; then
        log "Codex entrypoint not found: $CODEX_JS"
        exit 1
    fi

    rm -f "$NPM_PREFIX/bin/codex"
    cat >"$NPM_PREFIX/bin/codex" <<EOF
#!/bin/bash
export PATH="$(dirname "$node_path"):$NPM_PREFIX/bin:\$PATH"
export npm_config_cache="$NPM_CACHE_DIR"
exec "$node_path" "$CODEX_JS" "\$@"
EOF
    chmod +x "$NPM_PREFIX/bin/codex"
}

ensure_codex_vendor_binary() {
    vendor_root="$NPM_PREFIX/lib/node_modules/@openai/codex/node_modules"
    if [ ! -d "$vendor_root" ]; then
        return
    fi

    while IFS= read -r vendor_bin; do
        if [ -n "$vendor_bin" ]; then
            chmod +x "$vendor_bin"
            log "Ensured executable permission for $vendor_bin"
        fi
    done < <(find "$vendor_root" -path '*/vendor/*/codex/codex' -type f 2>/dev/null)
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

collect_code_servers() {
    find "$HOME/.vscode-server" \
        \( -path '*/bin/code-server' -o -path '*/server/bin/code-server' \) \
        -type f 2>/dev/null | sort -u
}

for _ in $(seq 1 360); do
    found_server=0
    while IFS= read -r code_server; do
        if [ ! -x "$code_server" ]; then
            continue
        fi

        found_server=1
        commit_dir="$(echo "$code_server" | sed -E 's#.*/(Stable-[^/]+|[0-9a-f]{40})(\.staging)?/.*#\1#')"
        if [ -z "$commit_dir" ] || [ "$commit_dir" = "$code_server" ]; then
            commit_dir="$(basename "$(dirname "$(dirname "$code_server")")")"
        fi
        marker_file="$MARKER_DIR/$commit_dir.done"

        if [ -f "$marker_file" ]; then
            continue
        fi

        log "Installing remote VS Code extensions for commit $commit_dir"
        install_ok=1
        for extension in "${EXTENSIONS[@]}"; do
            if ! "$code_server" --install-extension "$extension" --force </dev/null >>"$LOG_FILE" 2>&1; then
                install_ok=0
                log "Failed to install extension $extension for commit $commit_dir"
            fi
        done

        if [ "$install_ok" -eq 1 ]; then
            touch "$marker_file"
            log "Finished remote VS Code extension install for commit $commit_dir"
        else
            log "Will retry remote VS Code extension install for commit $commit_dir"
        fi
    done < <(collect_code_servers)

    if [ "$found_server" -eq 1 ]; then
        if ls "$MARKER_DIR"/*.done >/dev/null 2>&1; then
            exit 0
        fi
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
            log "Stopping previous VS Code extension watcher PID $old_pid"
            kill "$old_pid" 2>/dev/null || true
        fi
    fi

    if [ "$WATCH_MODE" = "foreground" ]; then
        log "Running VS Code extension watcher in foreground mode"
        echo $$ >"$WATCH_PID_FILE"
        bash "$WATCH_SCRIPT" </dev/null >>"$LOG_FILE" 2>&1
        return
    fi

    log "Starting VS Code extension watcher..."
    nohup bash "$WATCH_SCRIPT" </dev/null >>"$LOG_FILE" 2>&1 &
    echo $! >"$WATCH_PID_FILE"
    log "VS Code extension watcher started with PID $(cat "$WATCH_PID_FILE")"
}

show_summary() {
    log "Python: $(python3 --version 2>/dev/null || echo unavailable)"
    log "Jupyter: $(jupyter --version 2>/dev/null | head -n 1 || echo unavailable)"
    log "Codex CLI: $(codex --version 2>/dev/null || echo unavailable)"
    log "Devtools log: $LOG_FILE"
}

main() {
    ensure_state_dir
    ensure_node_and_npm
    ensure_persistent_npm_prefix
    ensure_codex_cli
    install_codex_wrapper
    ensure_codex_vendor_binary
    write_watcher_script
    start_watcher
    show_summary
}

main "$@"
