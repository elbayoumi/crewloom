"""Acceptance for the documentation/MANIFEST.json completeness gate.

The manifest must list exactly the Git-tracked files with current SHA-256 values. A tree that omits,
invents or mis-hashes a file is rejected; a matching tree and a non-Git archive are accepted.
"""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import check_repository as gate
from repo_map import git_environment


def git(root, *args):
    subprocess.run(['git', '-C', str(root), '-c', 'user.email=t@example.test', '-c', 'user.name=t', *args],
                   check=True, capture_output=True, env=git_environment())


class ManifestGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        git(self.root, 'init', '-q')
        (self.root / 'documentation').mkdir()
        (self.root / 'a.txt').write_text('alpha\n', encoding='utf-8')
        (self.root / 'documentation' / 'MANIFEST.json').write_text(
            json.dumps({'package_version': '1.0.0', 'scope': 'test scope', 'files': {}}), encoding='utf-8')
        git(self.root, 'add', '-A')

    def test_a_manifest_that_omits_a_tracked_file_is_rejected(self):
        errors = gate.manifest_errors(self.root)
        self.assertIn('Manifest omits tracked file: a.txt', errors)

    def test_a_regenerated_manifest_is_accepted_and_keeps_version_and_scope(self):
        self.assertEqual(gate.write_manifest(self.root), 1)
        git(self.root, 'add', '-A')
        self.assertEqual(gate.manifest_errors(self.root), [])
        written = json.loads((self.root / 'documentation' / 'MANIFEST.json').read_text(encoding='utf-8'))
        self.assertEqual((written['package_version'], written['scope']), ('1.0.0', 'test scope'))

    def test_a_changed_file_invented_entry_and_new_tracked_file_are_each_rejected(self):
        gate.write_manifest(self.root)
        (self.root / 'a.txt').write_text('changed\n', encoding='utf-8')
        (self.root / 'b.txt').write_text('beta\n', encoding='utf-8')
        git(self.root, 'add', '-A')
        manifest = json.loads((self.root / 'documentation' / 'MANIFEST.json').read_text(encoding='utf-8'))
        manifest['files']['ghost.txt'] = '0' * 64
        (self.root / 'documentation' / 'MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8')
        errors = gate.manifest_errors(self.root)
        self.assertIn('Manifest hash is stale: a.txt', errors)
        self.assertIn('Manifest omits tracked file: b.txt', errors)
        self.assertIn('Manifest lists untracked file: ghost.txt', errors)

    def test_an_untracked_local_file_does_not_fail_the_gate(self):
        gate.write_manifest(self.root)
        git(self.root, 'add', '-A')
        (self.root / 'scratch.txt').write_text('local only\n', encoding='utf-8')
        self.assertEqual(gate.manifest_errors(self.root), [])

    def test_an_archive_without_git_or_without_a_manifest_is_not_checked(self):
        with tempfile.TemporaryDirectory() as plain:
            archive = Path(plain)
            (archive / 'documentation').mkdir()
            (archive / 'documentation' / 'MANIFEST.json').write_text('{"files": {}}', encoding='utf-8')
            self.assertEqual(gate.manifest_errors(archive), [])
        (self.root / 'documentation' / 'MANIFEST.json').unlink()
        git(self.root, 'add', '-A')
        self.assertEqual(gate.manifest_errors(self.root), [])

    def test_a_corrupt_manifest_is_reported_not_raised(self):
        (self.root / 'documentation' / 'MANIFEST.json').write_text('{not json', encoding='utf-8')
        self.assertTrue(gate.manifest_errors(self.root)[0].startswith('Invalid documentation/MANIFEST.json'))

    def test_an_inherited_git_directory_does_not_redirect_the_gate(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            git(Path(elsewhere), 'init', '-q')
            with patch.dict(os.environ, {'GIT_DIR': str(Path(elsewhere) / '.git')}):
                errors = gate.manifest_errors(self.root)
        self.assertIn('Manifest omits tracked file: a.txt', errors)

    def test_write_manifest_flag_runs_through_main_without_the_suites(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(gate.main(['--write-manifest'], root=self.root), 0)
        self.assertIn('Wrote documentation/MANIFEST.json with 1 files', out.getvalue())


if __name__ == '__main__':
    unittest.main()
