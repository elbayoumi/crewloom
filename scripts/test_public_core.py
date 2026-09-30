"""Regression coverage for repository checks, CLI errors, and resource heuristics."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_repository import inspect

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts' / 'crewloom.py'
RESOURCE = ROOT / '.agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py'


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
