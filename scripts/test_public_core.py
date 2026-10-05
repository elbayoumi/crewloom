"""Regression coverage for repository checks, CLI errors, and resource heuristics."""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import crewloom
from check_repository import inspect

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts' / 'crewloom.py'
RESOURCE = ROOT / '.agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py'


class DashboardSecretDeliveryTests(unittest.TestCase):
    """The generated dashboard secret must reach the operator as a file, never as output."""

    def test_generated_secret_is_written_owner_only_and_only_its_path_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            secret = crewloom.write_dashboard_secret(root, 'generated-value')
            self.assertTrue(secret.is_file())
            self.assertEqual(secret.read_text(encoding='utf-8').strip(), 'generated-value')
            self.assertEqual(stat.S_IMODE(secret.stat().st_mode), 0o600)
            self.assertEqual(secret.parent.name, '.crewloom')
            self.assertEqual([item.name for item in (root / '.crewloom').iterdir()], ['dashboard-token'],
                             'no temporary secret may survive')

    def test_a_symlinked_credential_path_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / '.crewloom').mkdir()
            (root / '.crewloom' / 'elsewhere').write_text('decoy', encoding='utf-8')
            (root / '.crewloom' / 'dashboard-token').symlink_to(root / '.crewloom' / 'elsewhere')
            with self.assertRaises(ValueError):
                crewloom.write_dashboard_secret(root, 'generated-value')

    def test_a_non_loopback_bind_requires_a_configured_credential(self):
        strong = 'k' * crewloom.MIN_DASHBOARD_TOKEN
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(crewloom.dashboard_binding_allowed('127.0.0.1'))
            self.assertFalse(crewloom.dashboard_binding_allowed('0.0.0.0'))
        with patch.dict(os.environ, {'CREWLOOM_DASHBOARD_TOKEN': strong}):
            self.assertTrue(crewloom.dashboard_binding_allowed('0.0.0.0'))
            self.assertEqual(crewloom.dashboard_token(), strong)
        with patch.dict(os.environ, {'CREWLOOM_DASHBOARD_TOKEN': '   '}):
            self.assertIsNone(crewloom.dashboard_token())
            self.assertFalse(crewloom.dashboard_binding_allowed('0.0.0.0'),
                             'whitespace is not a configured credential')
        with patch.dict(os.environ, {'CREWLOOM_DASHBOARD_TOKEN': 'weak'}):
            self.assertIsNone(crewloom.dashboard_token())
            self.assertFalse(crewloom.dashboard_binding_allowed('0.0.0.0'),
                             'a short value is not meaningfully different from no authentication')

    def test_a_preexisting_temporary_name_cannot_redirect_a_secret_write(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as foreign_directory:
            root = Path(directory).resolve()
            foreign = Path(foreign_directory).resolve() / 'protected.txt'
            foreign.write_text('unchanged\n', encoding='utf-8')
            (root / '.crewloom').mkdir()
            (root / '.crewloom' / 'dashboard-token.tmp').symlink_to(foreign)
            secret = crewloom.write_dashboard_secret(root, 'generated-value')
            self.assertEqual(secret.read_text(encoding='utf-8').strip(), 'generated-value')
            self.assertEqual(foreign.read_text(encoding='utf-8'), 'unchanged\n')
            self.assertEqual(sorted(item.name for item in (root / '.crewloom').iterdir()),
                             ['dashboard-token', 'dashboard-token.tmp'],
                             'the planted name stays as it was and no new temporary file survives')


class PublicCoreTests(unittest.TestCase):
    def test_escaping_markdown_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'LICENSE').write_text('test')
            (root / 'README.md').write_text('[escape](../outside.md)')
            self.assertTrue(any('escaping link' in error for error in inspect(root)))

    def test_empty_checkout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn('No skills found', inspect(Path(directory)))

    def test_invalid_skill_id_is_rejected(self):
        result = subprocess.run([sys.executable, str(CLI), 'show', '../outside'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Invalid skill ID', result.stderr)

    def test_resource_checker_distinguishes_bad_good_and_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.ts'
            for content, expected in [('const q = "SELECT * FROM accounts";', 1),
                                      ('export const answer = 42;', 0)]:
                path.write_text(content)
                result = subprocess.run([sys.executable, str(RESOURCE), '--project-dir', directory],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            path.unlink()
            result = subprocess.run([sys.executable, str(RESOURCE), '--project-dir', directory],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
