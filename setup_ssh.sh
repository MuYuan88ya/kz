#!/bin/bash

set -e # Exit immediately if a command exits with a non-zero status

# Function to export environment variables from a file
export_env_vars_from_file() {
    local env_file=$1
    while IFS= read -r line; do
        if [[ "$line" =~ ^[A-Z0-9_]+=.* ]]; then
            export "$line"
        fi
    done <"$env_file"
}

# Path to the captured environment variables file
ENV_VARS_FILE=/kaggle/working/kaggle_env_vars.txt

if [ -f "$ENV_VARS_FILE" ]; then
    echo "Exporting environment variables from $ENV_VARS_FILE"
    export_env_vars_from_file "$ENV_VARS_FILE"
else
    echo "Environment variables file $ENV_VARS_FILE not found"
fi

# Make authorized keys URL optional
AUTH_KEYS_URL=$1
AUTHORIZED_KEYS_FILE=/kaggle/working/.ssh/authorized_keys
SSHD_DROPIN_FILE=/etc/ssh/sshd_config.d/kaggle_remote.conf

setup_cuda_environment() {
    echo "Setting up CUDA environment variables..."

    echo "export CUDA_HOME=/usr/local/cuda" >> ~/.bashrc
    echo "export PATH=/usr/local/cuda/bin:/opt/bin:\$PATH" >> ~/.bashrc
    echo "export LD_LIBRARY_PATH=/usr/local/nvidia/lib64:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:\$LD_LIBRARY_PATH" >> ~/.bashrc
    
    echo "CUDA environment variables set successfully"
}

setup_ssh_directory() {
    mkdir -p /kaggle/working/.ssh
    if [ ! -z "$AUTH_KEYS_URL" ]; then
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
    echo "Installing openssh-server..."
    sudo apt-get update
    sudo apt-get install -y openssh-server
}

start_ssh_service() {
    service ssh start
    service ssh restart
}

cleanup() {
    [ -f /kaggle/working/kaggle_env_vars.txt ] && rm /kaggle/working/kaggle_env_vars.txt
}

install_packages
setup_cuda_environment
setup_ssh_directory
configure_sshd
start_ssh_service
cleanup

echo "Setup script completed successfully"
echo "All tasks completed successfully"
