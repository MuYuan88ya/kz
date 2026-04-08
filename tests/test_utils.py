import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from utils import Zrok


class ZrokUtilsTests(unittest.TestCase):
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
