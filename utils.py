import urllib.request
import os
import sys
import tarfile
import json
import subprocess
import platform
import shutil
import tempfile
from pathlib import Path

class Zrok:
    DEFAULT_LINUX_CACHE_DIR = Path("/kaggle/working/.kaggle_remote_zrok/bin")

    def __init__(self, token: str, name: str = None):
        """Initialize Zrok instance with API token and optional environment name.
        
        Args:
            token (str): Zrok API token for authentication
            name (str, optional): Name/description for the zrok environment. Defaults to None.
        """
        if token.startswith('<') and token.endswith('>'):
            raise ValueError("Please provide an actual your zrok token")
        
        self.token = token
        self.name = name
        self.base_url = "https://api-v1.zrok.io/api/v1"
        self.cli = self.resolve_executable()

    @staticmethod
    def resolve_executable():
        for command in ("zrok", "zrok.exe"):
            resolved = shutil.which(command)
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

        cached_cli = Zrok.cached_executable_path()
        if cached_cli and cached_cli.exists():
            return str(cached_cli)

        return "zrok"

    @staticmethod
    def cached_executable_path():
        if platform.system() != "Linux":
            return None

        cache_dir = Path(os.environ.get("ZROK_CACHE_DIR", str(Zrok.DEFAULT_LINUX_CACHE_DIR)))
        for candidate in [cache_dir / "zrok", *cache_dir.rglob("zrok")]:
            if candidate.exists():
                try:
                    candidate.chmod(candidate.stat().st_mode | 0o111)
                except OSError:
                    pass
                return candidate
        return None

    @staticmethod
    def cached_archive_path():
        if platform.system() != "Linux":
            return None

        cache_dir = Path(os.environ.get("ZROK_CACHE_DIR", str(Zrok.DEFAULT_LINUX_CACHE_DIR)))
        preferred = cache_dir / "zrok.tar.gz"
        if preferred.exists():
            return preferred

        for candidate in cache_dir.rglob("*.tar.gz"):
            return candidate

        return None

    @staticmethod
    def executable_works(cli_path: str):
        try:
            subprocess.run([cli_path, "version"], capture_output=True, text=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError, PermissionError):
            return False

    def get_env(self):
        """Get overview of all zrok environments using HTTP API.

        This method uses HTTP API to retrieve environments even when zrok enable command fails.
        
        Returns:
            dict: Overview data containing environments information
            None: If the API call fails or no environments exist
        """
        try:
            result = subprocess.run(
                [self.cli, "overview"],
                capture_output=True,
                text=True,
                check=True,
            )
            data = json.loads(result.stdout)
            return data["environments"]
        except Exception:
            req = urllib.request.Request(
                url=f"{self.base_url}/overview",
                headers={"x-token": self.token},
            )

            with urllib.request.urlopen(req) as response:
                status = response.getcode()
                data = response.read().decode('utf-8')
                data = json.loads(data)

            if status != 200:
                print(f"Error: {status}")
                raise Exception("zrok API overview error")
            
            return data['environments']

    def find_env(self, name: str):
        """Find a specific environment by its name.
        
        Args:
            name (str): Name/description of the environment to find (case-insensitive)
        
        Returns:
            dict: Environment information if found
            None: If no environment matches the given name
        """
        overview = self.get_env()
        if overview is None:
            return None

        matches = []
        for item in overview:
            env = item["environment"]
            if env["description"].lower() == name.lower():
                matches.append(item)

        if not matches:
            return None

        shareful_matches = [item for item in matches if item.get("shares")]
        if shareful_matches:
            return shareful_matches[-1]
            
        return matches[-1]

    def delete_environment(self, zId: str):
        """Delete a zrok environment by its ID.
        
        Args:
            zid (str): The environment ID to delete
        
        Returns:
            bool: True if the environment was successfully deleted, False otherwise
        """
        headers = {
            "x-token": self.token,
            "Accept": "*/*",
            "Content-Type": "application/zrok.v1+json"
        }
        payload = {
            "identity": zId
        }
        
        data_bytes = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(f"{self.base_url}/disable", headers=headers, data=data_bytes, method="POST")
        with urllib.request.urlopen(req) as response:
            status = response.getcode()

        if status != 200:
            raise Exception("Failed to delete environment")

        return True

    def enable(self, name: str = None):
        """Enable zrok with the specified environment name.
        
        This method runs the 'zrok enable' command with the provided token and
        environment name. It will create a new environment if one doesn't exist.
        
        Args:
            name (str, optional): Name/description for the zrok environment.
                                 If not provided, uses the name from initialization.
            
        Raises:
            RuntimeError: If enable command fails
        """
        env_name = name if name is not None else self.name
        if env_name is None:
            raise ValueError("Environment name must be provided either during initialization or when calling enable()")
        
        subprocess.run([self.cli, "enable", self.token, "-d", env_name], check=True)

    def disable(self, name: str = None):
        """Disable zrok.
        
        This function executes the zrok disable command to delete the environment stored in the local file ~/.zrok/environment.json,
        and additionally removes any environments that could not be deleted through HTTP communication.
        
        Args:
            name (str, optional): Name/description for the zrok environment.
                                If not provided, uses the name from initialization.
        """
        env_name = name if name is not None else self.name

        # Delete the ~/.zrok/environment.json file
        try:
            subprocess.run([self.cli, "disable"], check=True)
        except Exception as e:
            print(e)
            print("zrok already disable")

        # Delete environment via HTTP communication even if zrok is not enabled
        try:
            env = self.find_env(env_name)
            if env is not None:
                self.delete_environment(env['environment']['zId'])
        except Exception as e:
            print(e)
            print("failed to delete remote zrok environment; continuing")

    @staticmethod
    def install():
        """Install the latest version of zrok.
        
        This method:
        1. Downloads the latest zrok release from GitHub
        2. Extracts the binary to /usr/local/bin/
        3. Verifies the installation
        """
        # Check if running on Windows
        if platform.system() != 'Linux':
            if Zrok.is_installed():
                return
            raise Exception("zrok was not found on this machine. Install it from https://docs.zrok.io/docs/guides/install/ and ensure `zrok` is in PATH, or set ZROK_BIN to the full zrok executable path.")

        cached_cli = Zrok.cached_executable_path()
        if cached_cli and Zrok.executable_works(str(cached_cli)):
            print(f"Using cached zrok from {cached_cli}")
            return

        cache_dir = Path(os.environ.get("ZROK_CACHE_DIR", str(Zrok.DEFAULT_LINUX_CACHE_DIR)))
        cache_dir.mkdir(parents=True, exist_ok=True)
        target_path = cache_dir / "zrok"
        archive_path = Zrok.cached_archive_path()
        if archive_path is not None:
            print(f"Extracting cached zrok archive from {archive_path}")
        else:
            print("Downloading latest zrok release")
            response = urllib.request.urlopen("https://api.github.com/repos/openziti/zrok/releases/latest")
            data = json.loads(response.read())

            download_url = None
            for asset in data["assets"]:
                if "linux_amd64.tar.gz" in asset["browser_download_url"]:
                    download_url = asset["browser_download_url"]
                    break

            if not download_url:
                raise FileNotFoundError("Could not find zrok download URL for linux_amd64")

            archive_path = cache_dir / "zrok.tar.gz"
            with tempfile.TemporaryDirectory(dir=str(cache_dir)) as temp_dir:
                download_path = Path(temp_dir) / "zrok.tar.gz"
                urllib.request.urlretrieve(download_url, download_path)
                shutil.copy2(download_path, archive_path)

        print(f"Extracting zrok to {target_path}")
        with tarfile.open(archive_path, "r:gz") as tar:
            member = next((item for item in tar.getmembers() if Path(item.name).name == "zrok"), None)
            if member is None:
                raise FileNotFoundError("Could not find zrok binary in downloaded archive")

            extracted = tar.extractfile(member)
            if extracted is None:
                raise FileNotFoundError("Could not extract zrok binary from downloaded archive")

            with open(target_path, "wb") as output_file:
                shutil.copyfileobj(extracted, output_file)

        target_path.chmod(0o755)

        # Check if zrok is installed correctly
        if not Zrok.is_installed():
            raise RuntimeError("Failed to verify zrok installation")

        print(f"Successfully installed zrok to {target_path}")

    @staticmethod
    def is_installed():
        """Check if zrok is installed and accessible.
        
        Returns:
            bool: True if zrok is installed and can be executed, False otherwise
        """
        return Zrok.executable_works(Zrok.resolve_executable())

    @staticmethod
    def is_enabled() -> bool:
        """Check if zrok is enabled.
        
        Returns:
            bool: True if zrok is enabled (Account Token and Ziti Identity are set), False otherwise
        """
        try:
            result = subprocess.run(
                [Zrok.resolve_executable(), "status"],
                capture_output=True,
                text=True,
                check=True
            )
            # Check if both Account Token and Ziti Identity are set
            return "Account Token  <<SET>>" in result.stdout and "Ziti Identity  <<SET>>" in result.stdout
        except subprocess.CalledProcessError:
            return False
        except FileNotFoundError:
            return False

  
