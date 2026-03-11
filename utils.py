import urllib.request
import os
import sys
import tarfile
import json
import subprocess
import platform
import shutil

class Zrok:
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

        return "zrok"

    def get_env(self):
        """Get overview of all zrok environments using HTTP API.

        This method uses HTTP API to retrieve environments even when zrok enable command fails.
        
        Returns:
            dict: Overview data containing environments information
            None: If the API call fails or no environments exist
        """
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

        for item in overview:
            env = item["environment"]
            if env["description"].lower() == name.lower():
                return item
            
        return None

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
        env = self.find_env(env_name)
        if env is not None:
            self.delete_environment(env['environment']['zId'])

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
            raise Exception("This script only works on Linux. For other operating systems, \
                            please install zrok manually following the instructions at https://docs.zrok.io/docs/guides/install/")

        print("Downloading latest zrok release")
        # Get latest release info
        response = urllib.request.urlopen("https://api.github.com/repos/openziti/zrok/releases/latest")
        data = json.loads(response.read())
        
        # Find linux_amd64 tar.gz download URL
        download_url = None
        for asset in data["assets"]:
            if "linux_amd64.tar.gz" in asset["browser_download_url"]:
                download_url = asset["browser_download_url"]
                break
        
        if not download_url:
            raise FileNotFoundError("Could not find zrok download URL for linux_amd64")
        
        # Download zrok
        urllib.request.urlretrieve(download_url, "zrok.tar.gz")
        
        print("Extracting Zrok")
        with tarfile.open("zrok.tar.gz", "r:gz") as tar:
            tar.extractall("/usr/local/bin/")
        os.remove("zrok.tar.gz")

        # Check if zrok is installed correctly
        if not Zrok.is_installed():
            raise RuntimeError("Failed to verify zrok installation")
        
        print("Successfully installed zrok")

    @staticmethod
    def is_installed():
        """Check if zrok is installed and accessible.
        
        Returns:
            bool: True if zrok is installed and can be executed, False otherwise
        """
        try:
            subprocess.run([Zrok.resolve_executable(), "version"], check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

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

  
