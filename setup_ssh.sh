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
AUTH_KEYS_URL="${1:-}"
AUTHORIZED_KEYS_FILE="/kaggle/working/.ssh/authorized_keys"
SSHD_DROPIN_FILE="/etc/ssh/sshd_config.d/kaggle_remote.conf"
BASH_RC="$HOME/.bashrc"

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
    if grep -Fq '# kaggle-remote-zrok cuda env' "$BASH_RC" 2>/dev/null; then
        echo "CUDA environment variables already configured in $BASH_RC"
        return
    fi

    cat >>"$BASH_RC" <<'EOF'

# kaggle-remote-zrok cuda env
export CUDA_HOME=/usr/local/cuda
export PATH=/usr/local/cuda/bin:/opt/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/nvidia/lib64:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:$LD_LIBRARY_PATH
EOF

    echo "CUDA environment variables set successfully"
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
        echo "PrintLastLog yes"
        echo "ChallengeResponseAuthentication no"
        echo "UsePAM yes"
        echo "AcceptEnv LANG LC_*"
        echo "AllowTcpForwarding yes"
        echo "GatewayPorts yes"
        echo "PermitTunnel yes"
        echo "ClientAliveInterval 60"
        echo "ClientAliveCountMax 2"
    } >"$SSHD_DROPIN_FILE"
}

install_packages() {
    if command -v sshd >/dev/null 2>&1; then
        echo "openssh-server already available; skipping install"
        return
    fi

    echo "Installing openssh-server..."
    sudo apt-get update
    sudo apt-get install -y openssh-server
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
