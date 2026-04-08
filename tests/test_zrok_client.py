import tempfile
import unittest
from pathlib import Path

from zrok_client import (
    ClientPaths,
    build_kaggle_init_command,
    build_ssh_config_entry,
    build_vscode_launch_command,
    normalize_argv,
    should_attempt_auto_install_zrok,
)


class ZrokClientTests(unittest.TestCase):
    def test_client_paths_from_home(self):
        home = Path('/tmp/example-home')
        paths = ClientPaths.from_home(home)
        self.assertEqual(paths.state_dir, home / '.kaggle_remote_zrok')
        self.assertEqual(paths.token_cache_file, home / '.kaggle_remote_zrok' / 'zrok_token.txt')
        self.assertEqual(paths.private_key, home / '.ssh' / 'kaggle_rsa')
        self.assertEqual(paths.public_key, home / '.ssh' / 'kaggle_rsa.pub')
        self.assertEqual(paths.ssh_config, home / '.ssh' / 'config')

    def test_normalize_argv_defaults_to_start(self):
        self.assertEqual(normalize_argv([]), ['start'])
        self.assertEqual(normalize_argv(['--token', 'abc']), ['start', '--token', 'abc'])
        self.assertEqual(normalize_argv(['prepare', '--token', 'abc']), ['prepare', '--token', 'abc'])
        self.assertEqual(normalize_argv(['--help']), ['--help'])

    def test_build_kaggle_init_command_quotes_values(self):
        command = build_kaggle_init_command('abc 123', 'ssh-rsa AAA test key')
        self.assertIn('--token', command)
        self.assertIn('--authorized_key', command)
        self.assertIn("'abc 123'", command)

    def test_build_ssh_config_entry_with_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = ClientPaths.from_home(Path(tmpdir))
            paths.ssh_dir.mkdir(parents=True, exist_ok=True)
            paths.private_key.write_text('dummy', encoding='utf-8')
            entry = build_ssh_config_entry('kaggle_client', 9191, paths)
            self.assertIn('IdentityFile ~/.ssh/kaggle_rsa', entry)
            self.assertNotIn('PreferredAuthentications password', entry)

    def test_build_ssh_config_entry_without_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = ClientPaths.from_home(Path(tmpdir))
            entry = build_ssh_config_entry('kaggle_client', 9191, paths)
            self.assertIn('PreferredAuthentications password', entry)
            self.assertIn('PubkeyAuthentication no', entry)

    def test_write_ssh_config_smoke(self):
        from zrok_client import write_ssh_config

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = ClientPaths.from_home(Path(tmpdir))
            paths.ssh_dir.mkdir(parents=True, exist_ok=True)
            write_ssh_config('kaggle_client', 9191, paths)
            content = paths.ssh_config.read_text(encoding='utf-8')
            self.assertIn('Host kaggle_client', content)
            self.assertIn('Port 9191', content)

    def test_build_vscode_launch_command_windows(self):
        command, kwargs = build_vscode_launch_command(
            host='kaggle_client',
            workspace='/kaggle/working',
            system_name='Windows',
            code_executable='code',
        )
        self.assertEqual(command, ['code', '--remote', 'ssh-remote+kaggle_client', '/kaggle/working'])
        self.assertIn('creationflags', kwargs)

    def test_build_vscode_launch_command_macos_fallback(self):
        command, kwargs = build_vscode_launch_command(
            host='kaggle_client',
            workspace='/kaggle/working',
            system_name='Darwin',
            code_executable='',
            open_executable='/usr/bin/open',
        )
        self.assertEqual(
            command,
            ['/usr/bin/open', '-a', 'Visual Studio Code', '--args', '--remote', 'ssh-remote+kaggle_client', '/kaggle/working'],
        )
        self.assertEqual(kwargs, {})

    def test_should_attempt_auto_install_zrok(self):
        self.assertTrue(should_attempt_auto_install_zrok('Linux'))
        self.assertFalse(should_attempt_auto_install_zrok('Darwin'))
        self.assertFalse(should_attempt_auto_install_zrok('Windows'))


if __name__ == '__main__':
    unittest.main()
