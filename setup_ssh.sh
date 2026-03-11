#!/bin/bash
# Self-contained SSH server bootstrap for Kaggle.
# Usage: bash setup_ssh.sh [authorized_keys_url]
#
# Accepts one optional argument: a URL to download authorized_keys from.
# If a local authorized_keys file already exists at the expected path,
# it will be used as-is when no URL is provided.
# Returns 0 on success, non-zero on failure.

set -e

AUTHORIZED_KEYS_FILE=/kaggle/working/.ssh/authorized_keys
SSHD_DROPIN_FILE=/etc/ssh/sshd_config.d/kaggle_remote.conf
AUTH_KEYS_URL="${1:-}"

# ── Install openssh-server ──────────────────────────────────────────
echo "Installing openssh-server..."
sudo apt-get update
sudo apt-get install -y openssh-server

# ── Authorized keys ────────────────────────────────────────────────
mkdir -p /kaggle/working/.ssh

if [ -n "$AUTH_KEYS_URL" ]; then
    if wget -qO "$AUTHORIZED_KEYS_FILE" "$AUTH_KEYS_URL"; then
        echo "Downloaded authorized keys from $AUTH_KEYS_URL"
    else
        echo "Failed to download authorized keys from $AUTH_KEYS_URL"
        echo "Continuing without authorized keys..."
    fi
fi

if [ -f "$AUTHORIZED_KEYS_FILE" ]; then
    chmod 700 /kaggle/working/.ssh
    chmod 600 "$AUTHORIZED_KEYS_FILE"
    echo "Authorized keys ready at $AUTHORIZED_KEYS_FILE"
else
    echo "No authorized keys configured. Password login required."
fi

# ── Configure sshd ─────────────────────────────────────────────────
mkdir -p /var/run/sshd
mkdir -p /etc/ssh/sshd_config.d

cat >"$SSHD_DROPIN_FILE" <<EOF
Port 22
Protocol 2
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication yes
$([ -f "$AUTHORIZED_KEYS_FILE" ] && echo "AuthorizedKeysFile $AUTHORIZED_KEYS_FILE")
TCPKeepAlive yes
X11Forwarding yes
X11DisplayOffset 10
IgnoreRhosts yes
HostbasedAuthentication no
PrintLastLog yes
ChallengeResponseAuthentication no
UsePAM yes
AcceptEnv LANG LC_*
AllowTcpForwarding yes
GatewayPorts yes
PermitTunnel yes
ClientAliveInterval 60
ClientAliveCountMax 2
EOF

# ── CUDA environment for SSH sessions ──────────────────────────────
if ! grep -Fq '# kaggle-remote-zrok CUDA' ~/.bashrc 2>/dev/null; then
    cat >>~/.bashrc <<'BASHRC'

# kaggle-remote-zrok CUDA
export CUDA_HOME=/usr/local/cuda
export PATH=/usr/local/cuda/bin:/opt/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/nvidia/lib64:/usr/local/cuda/lib64:/usr/local/cuda/lib64/stubs:$LD_LIBRARY_PATH
BASHRC
    echo "CUDA environment written to ~/.bashrc"
fi

# ── Kaggle env vars for SSH sessions ───────────────────────────────
ENV_VARS_FILE=/kaggle/working/kaggle_env_vars.txt
if [ -f "$ENV_VARS_FILE" ] && ! grep -Fq '# kaggle-remote-zrok env' ~/.bashrc 2>/dev/null; then
    cat >>~/.bashrc <<BASHRC

# kaggle-remote-zrok env
[ -f "$ENV_VARS_FILE" ] && set -a && source "$ENV_VARS_FILE" && set +a
BASHRC
    echo "Kaggle env vars sourced from ~/.bashrc"
fi

# ── Start sshd ─────────────────────────────────────────────────────
echo "Starting SSH service..."
service ssh restart || echo "service ssh restart returned non-zero; continuing"
service ssh status  || echo "service ssh status returned non-zero; continuing"

echo "SSH setup completed successfully"
