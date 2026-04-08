import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import Zrok


class ZrokUtilsTests(unittest.TestCase):
    def test_extract_archive_to_target_handles_nested_binary(self):
        import tarfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            archive = tmp / 'zrok.tar.gz'
            source_dir = tmp / 'nested'
            source_dir.mkdir()
            binary = source_dir / 'zrok'
            binary.write_text('binary', encoding='utf-8')
            with tarfile.open(archive, 'w:gz') as tar:
                tar.add(binary, arcname='nested/path/zrok')

            target = tmp / 'out' / 'zrok'
            target.parent.mkdir()
            Zrok._extract_archive_to_target(archive, target)
            self.assertEqual(target.read_text(encoding='utf-8'), 'binary')

    def test_install_redownloads_when_cached_archive_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            bad_archive = cache_dir / 'zrok.tar.gz'
            bad_archive.write_bytes(b'not-a-real-archive')
            target = cache_dir / 'zrok'

            with mock.patch('utils.platform.system', return_value='Linux'), \
                 mock.patch.object(Zrok, 'cached_executable_path', return_value=None), \
                 mock.patch.object(Zrok, 'cached_archive_path', return_value=bad_archive), \
                 mock.patch.object(Zrok, 'is_installed', return_value=True), \
                 mock.patch.object(Zrok, '_download_latest_linux_archive', return_value=cache_dir / 'fresh.tar.gz') as download_mock, \
                 mock.patch.object(Zrok, '_extract_archive_to_target', side_effect=[FileNotFoundError('bad cache'), None]) as extract_mock, \
                 mock.patch.dict(os.environ, {'ZROK_CACHE_DIR': str(cache_dir)}, clear=False):
                Zrok.install()

            self.assertEqual(download_mock.call_count, 1)
            self.assertEqual(extract_mock.call_count, 2)

    def test_resolve_executable_prefers_env_var(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cli = Path(tmpdir) / 'zrok-custom'
            cli.write_text('fake', encoding='utf-8')
            with mock.patch('utils.shutil.which', return_value=None), mock.patch.dict(os.environ, {'ZROK_BIN': str(cli)}, clear=False):
                self.assertEqual(Zrok.resolve_executable(), str(cli))

    def test_resolve_executable_falls_back_to_command_name(self):
        with mock.patch('utils.shutil.which', return_value=None), mock.patch('utils.Zrok.cached_executable_path', return_value=None), mock.patch.dict(os.environ, {}, clear=False):
            self.assertEqual(Zrok.resolve_executable(), 'zrok')


if __name__ == '__main__':
    unittest.main()
