import urllib.request
import os
import json
import subprocess
import platform
import tarfile
import shutil


class Zrok:
    def __init__(self, token, name=None):
        if token.startswith("<") and token.endswith(">"):
            raise ValueError("Please provide an actual zrok token")

        self.token = token
        self.name = name
        self.base_url = "https://api-v1.zrok.io/api/v1"
        self.cli = self.resolve_executable()

    @staticmethod
    def resolve_executable():
        for cmd in ("zrok", "zrok.exe"):
            resolved = shutil.which(cmd)
            if resolved:
                return resolved

        base_dir = os.path.dirname(os.path.abspath(__file__))
        for filename in ("zrok.exe", "zrok"):
            candidate = os.path.join(base_dir, filename)
            if os.path.exists(candidate):
                return candidate

        env_cli = os.environ.get("ZROK_BIN")
        if env_cli and os.path.exists(env_cli):
            return env_cli

        return "zrok"

    def get_env(self):
        """Get all zrok environments. Tries CLI first, falls back to HTTP API."""
        try:
            result = subprocess.run(
                [self.cli, "overview"], capture_output=True, text=True, check=True,
            )
            return json.loads(result.stdout)["environments"]
        except Exception:
            req = urllib.request.Request(
                url=f"{self.base_url}/overview",
                headers={"x-token": self.token},
            )
            with urllib.request.urlopen(req) as resp:
                if resp.getcode() != 200:
                    raise Exception("zrok API overview error")
                return json.loads(resp.read().decode("utf-8"))["environments"]

    def find_env(self, name):
        """Find environment by name. Prefers environments with active shares."""
        overview = self.get_env()
        if not overview:
            return None

        matches = [item for item in overview
                   if item["environment"]["description"].lower() == name.lower()]
        if not matches:
            return None

        # Prefer matches that have active shares
        with_shares = [m for m in matches if m.get("shares")]
        return (with_shares or matches)[-1]

    def delete_environment(self, zId):
        """Delete a zrok environment by its zId via HTTP API."""
        payload = json.dumps({"identity": zId}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/disable",
            headers={
                "x-token": self.token,
                "Accept": "*/*",
                "Content-Type": "application/zrok.v1+json",
            },
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            if resp.getcode() != 200:
                raise Exception("Failed to delete environment")

    def enable(self, name=None):
        """Enable zrok with environment name."""
        env_name = name or self.name
        if not env_name:
            raise ValueError("Environment name required")
        subprocess.run([self.cli, "enable", self.token, "-d", env_name], check=True)

    def disable(self, name=None):
        """Disable zrok locally and clean up remote environment."""
        env_name = name or self.name

        try:
            subprocess.run([self.cli, "disable"], check=True)
        except Exception as e:
            print(f"zrok disable: {e}")

        try:
            env = self.find_env(env_name)
            if env:
                self.delete_environment(env["environment"]["zId"])
        except Exception as e:
            print(f"Failed to delete remote env: {e}")

    @staticmethod
    def install():
        """Install latest zrok on Linux. On other platforms, check if it exists."""
        if platform.system() != "Linux":
            if Zrok.is_installed():
                return
            raise Exception(
                "zrok not found. Install from https://docs.zrok.io/docs/guides/install/ "
                "and ensure it's in PATH, or set ZROK_BIN."
            )

        print("Downloading latest zrok release...")
        resp = urllib.request.urlopen("https://api.github.com/repos/openziti/zrok/releases/latest")
        data = json.loads(resp.read())

        download_url = None
        for asset in data["assets"]:
            if "linux_amd64.tar.gz" in asset["browser_download_url"]:
                download_url = asset["browser_download_url"]
                break

        if not download_url:
            raise FileNotFoundError("Could not find zrok linux_amd64 download URL")

        urllib.request.urlretrieve(download_url, "zrok.tar.gz")
        with tarfile.open("zrok.tar.gz", "r:gz") as tar:
            tar.extractall("/usr/local/bin/")
        os.remove("zrok.tar.gz")

        if not Zrok.is_installed():
            raise RuntimeError("Failed to verify zrok installation")
        print("zrok installed successfully")

    @staticmethod
    def is_installed():
        try:
            subprocess.run([Zrok.resolve_executable(), "version"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def is_enabled():
        try:
            result = subprocess.run(
                [Zrok.resolve_executable(), "status"],
                capture_output=True, text=True, check=True,
            )
            return ("Account Token  <<SET>>" in result.stdout
                    and "Ziti Identity  <<SET>>" in result.stdout)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
