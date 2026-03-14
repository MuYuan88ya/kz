#!/bin/bash

set -euo pipefail

export_env_vars_from_file() {
    local env_file="$1"
    while IFS= read -r line; do
        if [[ "$line" =~ ^[A-Z0-9_]+=.* ]]; then
            export "$line"
        fi
    done <"$env_file"
}

ENV_VARS_FILE="/kaggle/working/kaggle_env_vars.txt"
STATE_DIR="/kaggle/working/.kaggle_remote_zrok"
AUTH_KEYS_URL="${1:-}"
AUTHORIZED_KEYS_FILE="/kaggle/working/.ssh/authorized_keys"
SSHD_DROPIN_FILE="/etc/ssh/sshd_config.d/kaggle_remote.conf"
BASH_RC="$HOME/.bashrc"
SHELL_ENV_SNIPPET="$STATE_DIR/shell-env.sh"
HUSHLOGIN_FILE="$HOME/.hushlogin"
APT_CACHE_DIR="$STATE_DIR/apt-archives"
APT_DOWNLOAD_DIR="$APT_CACHE_DIR/downloads"

if [ -f "$ENV_VARS_FILE" ]; then
    echo "Exporting environment variables from $ENV_VARS_FILE"
    export_env_vars_from_file "$ENV_VARS_FILE"
else
    echo "Environment variables file $ENV_VARS_FILE not found"
    echo "Capturing current environment variables to $ENV_VARS_FILE"
    printenv >"$ENV_VARS_FILE"
    export_env_vars_from_file "$ENV_VARS_FILE"
fi

setup_cuda_environment() {
    cat >"$SHELL_ENV_SNIPPET" <<'EOF'
# kaggle-remote-zrok shell env
export CUDA_HOME=/usr/local/cuda
export PATH=/usr/local/cuda/bin:/opt/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/nvidia/lib64:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:$LD_LIBRARY_PATH
EOF

    if ! grep -Fq "$SHELL_ENV_SNIPPET" "$BASH_RC" 2>/dev/null; then
        cat >>"$BASH_RC" <<EOF

# kaggle-remote-zrok shell env
[ -f "$SHELL_ENV_SNIPPET" ] && . "$SHELL_ENV_SNIPPET"
EOF
    fi

    touch "$HUSHLOGIN_FILE"
    echo "Lightweight shell environment configured via $SHELL_ENV_SNIPPET"
}

setup_ssh_directory() {
    mkdir -p /kaggle/working/.ssh
    if [ -n "$AUTH_KEYS_URL" ]; then
        if wget -qO "$AUTHORIZED_KEYS_FILE" "$AUTH_KEYS_URL"; then
            chmod 700 /kaggle/working/.ssh
            chmod 600 "$AUTHORIZED_KEYS_FILE"
            echo "Successfully set up authorized keys from $AUTH_KEYS_URL"
        else
            echo "Failed to download authorized keys from $AUTH_KEYS_URL"
            echo "Continuing without authorized keys setup..."
        fi
    elif [ -f "$AUTHORIZED_KEYS_FILE" ]; then
        chmod 700 /kaggle/working/.ssh
        chmod 600 "$AUTHORIZED_KEYS_FILE"
        echo "Using existing authorized keys file at $AUTHORIZED_KEYS_FILE"
    else
        echo "No authorized keys URL provided. Continuing without authorized keys setup..."
    fi
}

cache_ssh_packages() {
    mkdir -p "$APT_CACHE_DIR"
    shopt -s nullglob
    for package_file in \
        "$APT_DOWNLOAD_DIR"/*.deb; do
        cp -f "$package_file" "$APT_CACHE_DIR"/
    done
    shopt -u nullglob
}

has_cached_ssh_packages() {
    compgen -G "$STATE_DIR/**/openssh-server_*.deb" >/dev/null 2>&1 ||
    compgen -G "$APT_CACHE_DIR/openssh-server_*.deb" >/dev/null 2>&1
}

collect_cached_ssh_packages() {
    mkdir -p "$APT_CACHE_DIR"
    shopt -s globstar nullglob
    local copied=0
    for package_file in "$STATE_DIR"/**/*.deb; do
        cp -f "$package_file" "$APT_CACHE_DIR"/
        copied=1
    done
    shopt -u globstar nullglob
    [ "$copied" -eq 1 ]
}

install_cached_ssh_packages() {
    collect_cached_ssh_packages >/dev/null 2>&1 || true
    if ! compgen -G "$APT_CACHE_DIR/openssh-server_*.deb" >/dev/null 2>&1; then
        return 1
    fi

    echo "Installing openssh-server from cached packages in $APT_CACHE_DIR..."
    shopt -s nullglob
    local packages=("$APT_CACHE_DIR"/*.deb)
    if [ "${#packages[@]}" -eq 0 ]; then
        shopt -u nullglob
        return 1
    fi

    if DEBIAN_FRONTEND=noninteractive sudo dpkg -i "${packages[@]}"; then
        shopt -u nullglob
        return 0
    fi

    shopt -u nullglob
    echo "Cached package install failed; falling back to network install"
    return 1
}

configure_sshd() {
    mkdir -p /var/run/sshd
    mkdir -p /etc/ssh/sshd_config.d
    {
        echo "Port 22"
        echo "Protocol 2"
        echo "PermitRootLogin yes"
        echo "PasswordAuthentication yes"
        echo "PubkeyAuthentication yes"
        if [ -f "$AUTHORIZED_KEYS_FILE" ]; then
            echo "AuthorizedKeysFile $AUTHORIZED_KEYS_FILE"
        fi
        echo "TCPKeepAlive yes"
        echo "X11Forwarding yes"
        echo "X11DisplayOffset 10"
        echo "IgnoreRhosts yes"
        echo "HostbasedAuthentication no"
        echo "PrintLastLog no"
        echo "ChallengeResponseAuthentication no"
        echo "UseDNS no"
        echo "GSSAPIAuthentication no"
        echo "UsePAM yes"
        echo "AcceptEnv LANG LC_*"
        echo "AllowTcpForwarding yes"
        echo "GatewayPorts yes"
        echo "PermitTunnel yes"
        echo "LoginGraceTime 30"
        echo "MaxStartups 10:30:100"
        echo "ClientAliveInterval 30"
        echo "ClientAliveCountMax 3"
    } >"$SSHD_DROPIN_FILE"
    echo "Applied SSH low-latency settings in $SSHD_DROPIN_FILE"
}

install_packages() {
    if command -v sshd >/dev/null 2>&1; then
        echo "openssh-server already available; skipping install"
        cache_ssh_packages
        return
    fi

    if install_cached_ssh_packages; then
        cache_ssh_packages
        return
    fi

    echo "Installing openssh-server..."
    mkdir -p "$APT_DOWNLOAD_DIR"
    DEBIAN_FRONTEND=noninteractive sudo apt-get update
    DEBIAN_FRONTEND=noninteractive sudo apt-get install -y --download-only \
        -o Dir::Cache::archives="$APT_DOWNLOAD_DIR" \
        openssh-server
    cache_ssh_packages
    if ! install_cached_ssh_packages; then
        DEBIAN_FRONTEND=noninteractive sudo apt-get install -y openssh-server
    fi
    cache_ssh_packages
}

start_ssh_service() {
    echo "Starting ssh service..."
    if ! service ssh start; then
        echo "service ssh start returned a non-zero exit code; continuing"
    fi

    echo "Restarting ssh service..."
    if ! service ssh restart; then
        echo "service ssh restart returned a non-zero exit code; continuing"
    fi

    echo "Checking ssh service status..."
    if ! service ssh status; then
        echo "service ssh status returned a non-zero exit code; continuing"
    fi
}

cleanup() {
    echo "Keeping $ENV_VARS_FILE for later SSH sessions"
    return 0
}

install_packages
setup_cuda_environment
setup_ssh_directory
configure_sshd
start_ssh_service
cleanup

echo "Setup script completed successfully"
echo "All tasks completed successfully"
