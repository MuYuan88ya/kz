import subprocess
import argparse
import sys
import time
from utils import Zrok
import string
import random

def generate_random_password(length=16):
    characters = (string.ascii_letters + string.digits + "!@#$%^*()-_=+{}[]<>.,?")
    return ''.join(random.choices(characters, k=length))


def wait_for_share_token(zrok: Zrok, port: int, timeout: int = 20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        env = zrok.find_env(zrok.name)
        if env:
            for share in env.get("shares", []):
                if (share.get("backendMode") == "tcpTunnel" and
                    share.get("backendProxyEndpoint") == f"localhost:{port}"):
                    return share.get("shareToken")
        time.sleep(1)
    return None


def main(args):
    zrok = Zrok(args.token, args.name)
    
    if not Zrok.is_installed():
        Zrok.install()

    zrok.disable()
    zrok.enable()
    
    # Setup SSH server
    print("Setting up SSH server...")
    if args.authorized_keys_url:
        subprocess.run(["bash", "setup_ssh.sh", args.authorized_keys_url], check=True)
    else:
        subprocess.run(["bash", "setup_ssh.sh"], check=True)

    if args.password is not None:
        print(f"Setting password for root user: {args.password}")
        subprocess.run(f"echo 'root:{args.password}' | sudo chpasswd", shell=True, check=True)
    else:
        password = generate_random_password()
        print(f"Setting password for root user: {password}")
        subprocess.run(f"echo 'root:{password}' | sudo chpasswd", shell=True, check=True)

    print("Starting private zrok tcp tunnel for localhost:22...")
    share_process = subprocess.Popen(
        [zrok.cli, "share", "private", f"localhost:{args.port}", "--backend-mode", "tcpTunnel", "--headless"]
    )

    share_token = wait_for_share_token(zrok, args.port)
    if share_token:
        print(f"Share token: {share_token}")
    else:
        print("Share token not found yet. Check zrok service status and environment overview.")

    print("Private share is running. Keep this process alive while the client is connected.")
    share_process.wait()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Kaggle SSH connection setup')
    parser.add_argument('--token', type=str, help='zrok API token')
    parser.add_argument('--name', type=str, default='kaggle_server', help='Environment name to create (default: kaggle_server)')
    parser.add_argument('--authorized_keys_url', type=str, help='URL to authorized_keys file')
    parser.add_argument('--password', type=str, help='Password for root user, if not provided, a random password will be generated')
    parser.add_argument('--port', type=int, default=22, help='SSH port to share (default: 22)')
    args = parser.parse_args()

    if not args.token:
        args.token = input("Enter your zrok API token: ")
    
    try:
        main(args)
    except Exception as e:
        print(e)
        if sys.stdin.isatty():
            try:
                input("An error occurred. Press Enter to exit...")
            except EOFError:
                pass
        else:
            raise
