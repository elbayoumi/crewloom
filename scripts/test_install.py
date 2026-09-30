"""Regression coverage for `crewloom install` and its refusals."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts' / 'crewloom.py'


def cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=30)


class InstallTests(unittest.TestCase):
    def test_installs_selected_role_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            ok = cli('install', '--host', 'claude', '--target', directory, '--skill', 'seo-growth-engineer')
            self.assertEqual(ok.returncode, 0, ok.stderr)
            installed = Path(directory) / '.claude' / 'skills' / 'seo-growth-engineer'
            self.assertTrue((installed / 'SKILL.md').is_file())
            self.assertFalse(list(installed.rglob('__pycache__')))
            again = cli('install', '--host', 'claude', '--target', directory, '--skill', 'seo-growth-engineer')
            self.assertEqual(again.returncode, 2)
            self.assertIn('--force', again.stderr)
            forced = cli('install', '--host', 'claude', '--target', directory, '--skill', 'seo-growth-engineer', '--force')
            self.assertEqual(forced.returncode, 0)

    def test_unknown_and_invalid_roles_and_missing_target_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory, '--skill', 'nope').returncode, 2)
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory, '--skill', '../x').returncode, 2)
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory + '/missing').returncode, 2)
            self.assertFalse((Path(directory) / '.agents').exists())

    def test_installs_all_roles_for_agents_host(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory).returncode, 0)
            self.assertEqual(len(list((Path(directory) / '.agents' / 'skills').glob('*/SKILL.md'))), 42)


if __name__ == '__main__':
    unittest.main()
