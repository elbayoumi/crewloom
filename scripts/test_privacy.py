"""Real Git commits, forced additions, existing hook preservation and publication boundaries."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import crewloom
import privacy as p
import project_binding as pb
import repo_map
import user_context as uc


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, repo_map.git_environment(), clear=True)
        environment.start(); self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        pb.enter(self.root, 'privacy-fixture', 'fixture-task', 'context-guardian')
        pb.cancel(self.root, 'privacy-fixture', 'fixture-task', 'setup fixture')
        (self.root / 'code.py').write_text('print("public")\n')

    def git(self, *args, check=True, env=None):
        return subprocess.run(['git', *args], cwd=self.root, capture_output=True, text=True,
                              check=check, env=repo_map.git_environment(env))

    def test_install_ignores_role_memory_and_late_unignore_is_repaired(self):
        memory = '.agents/skills/context-guardian/brain/COMPLETED.md'
        self.assertEqual(self.git('check-ignore', memory, check=False).returncode, 0)
        (self.root / '.gitignore').write_text('.crewloom/\n!.crewloom/\n')
        pb.ignore_local_state(self.root)
        self.assertEqual(self.git('check-ignore', '.crewloom/private/note.txt', check=False).returncode, 0)

    def test_repair_candidates_are_ignored_and_forced_commit_is_rejected(self):
        p.init(self.root)
        candidate = self.root/'.crewloom-repairs/repair-one/candidate-0.txt'
        candidate.parent.mkdir(parents=True)
        candidate.write_text('private failed candidate')
        relative = candidate.relative_to(self.root).as_posix()
        self.assertEqual(self.git('check-ignore', relative, check=False).returncode, 0)
        self.git('add', '-f', relative)
        bad = self.git('commit', '-m', 'reject private repair', check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('private path', bad.stdout + bad.stderr)
        self.git('rm', '--cached', relative)
        self.git('add', 'code.py', 'crewloom.project.json', '.gitignore')
        clean = self.git('commit', '-m', 'public files only', check=False)
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

    def test_real_bad_commit_rejected_then_clean_commit_accepted(self):
        p.init(self.root)
        p.private_write(self.root, '.crewloom/private/note.txt', b'private conversation')
        self.git('add', '-f', '.crewloom/private/note.txt')
        bad = self.git('commit', '-m', 'reject private', check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('private path', bad.stdout + bad.stderr)
        self.git('rm', '--cached', '.crewloom/private/note.txt')
        self.assertTrue((self.root / '.crewloom/private/note.txt').exists())
        self.git('add', 'code.py')
        self.assertEqual(self.git('commit', '-m', 'public code', check=False).returncode, 0)

    def test_inherited_guard_checks_the_bound_worktree_index(self):
        p.init(self.root)
        self.git('add', 'code.py', 'crewloom.project.json', '.gitignore')
        self.git('commit', '-m', 'public base')
        worktree_folder = tempfile.TemporaryDirectory(); self.addCleanup(worktree_folder.cleanup)
        other = Path(worktree_folder.name).resolve() / 'parallel'
        self.git('worktree', 'add', '-b', 'parallel', str(other))
        pb.bootstrap(other, project_id='privacy-fixture')
        (other / 'second.py').write_text('value = 2\n')
        def run(*args):
            return subprocess.run(['git', *args], cwd=other, capture_output=True, text=True,
                                  env=repo_map.git_environment())
        self.assertEqual(run('add', 'second.py').returncode, 0)
        result = run('commit', '-m', 'task public code')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        p.private_write(other, '.crewloom/private/note.txt', b'private task')
        self.assertEqual(run('add', '-f', '.crewloom/private/note.txt').returncode, 0)
        result = run('commit', '-m', 'reject task private')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('private path', result.stdout + result.stderr)
        self.assertFalse((self.root / 'second.py').exists())

    def test_rebind_rehomes_guard_and_previous_hooks(self):
        previous = self.root / '.githooks'; previous.mkdir()
        (previous / 'pre-commit').write_text('#!/bin/sh\nexit 0\n')
        (previous / 'pre-commit').chmod(0o700)
        (previous / 'pre-push').write_text('#!/bin/sh\nexit 0\n')
        (previous / 'pre-push').chmod(0o700)
        self.git('config', 'core.hooksPath', '.githooks')
        p.init(self.root)
        moved = self.root.parent / (self.root.name + '-moved')
        shutil.move(str(self.root), str(moved)); self.root = moved.resolve()
        self.addCleanup(shutil.rmtree, self.root)
        pb.rebind(self.root, 'privacy-fixture', 'move fixture')
        self.assertEqual(self.git('config', '--get', 'core.hooksPath').stdout.strip(),
                         str(self.root / '.crewloom/private/hooks'))
        self.assertEqual((self.root / '.crewloom/private/hooks/pre-push').resolve(), self.root / '.githooks/pre-push')
        self.git('add', 'code.py')
        clean = self.git('commit', '-m', 'clean after move', check=False)
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        p.private_write(self.root, '.crewloom/private/note.txt', b'private after move')
        self.git('add', '-f', '.crewloom/private/note.txt')
        bad = self.git('commit', '-m', 'reject after move', check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('private path', bad.stdout + bad.stderr)

    def test_ordinary_ignore_additions_do_not_duplicate_runtime_rule(self):
        path = self.root / '.gitignore'
        path.write_text('/.crewloom/\n*.log\n')
        before = path.read_bytes()
        self.assertIsNone(pb.ignore_local_state(self.root))
        self.assertEqual(path.read_bytes(), before)

    def test_parallel_setup_reuses_the_owned_guard_without_chaining_cycles(self):
        p.init(self.root)
        configured = self.git('config', '--get', 'core.hooksPath').stdout.strip()
        self.git('add', 'code.py', 'crewloom.project.json', '.gitignore')
        self.git('commit', '-m', 'parallel base')
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        other = Path(folder.name).resolve() / 'parallel'
        self.git('worktree', 'add', '-b', 'parallel-setup', str(other))
        pb.bootstrap(other, project_id='privacy-fixture')
        self.assertEqual(p.init(other)['status'], 'inherited-enabled')
        self.assertEqual(self.git('config', '--get', 'core.hooksPath').stdout.strip(), configured)
        self.assertEqual(p.init(self.root)['status'], 'already-enabled')
        (other / 'clean.py').write_text('value = 1\n')
        def run(*args):
            return subprocess.run(['git', *args], cwd=other, capture_output=True, text=True,
                                  env=repo_map.git_environment(), timeout=30)
        self.assertEqual(run('add', 'clean.py').returncode, 0)
        clean = run('commit', '-m', 'accept parallel clean')
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        (other / 'snippet.txt').write_text('Private parallel excerpt')
        p.source_snapshot(other, 'snippet.txt', b'Private parallel excerpt')
        self.assertEqual(self.git('config', '--get', 'core.hooksPath').stdout.strip(), configured)
        self.assertEqual(run('add', 'snippet.txt').returncode, 0)
        bad = run('commit', '-m', 'reject parallel source')
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('private path', bad.stdout + bad.stderr)

    def test_existing_pre_commit_and_other_hooks_are_preserved(self):
        hooks = self.root / '.githooks'; hooks.mkdir()
        previous = hooks / 'pre-commit'
        previous.write_text('#!/bin/sh\nexit 7\n'); previous.chmod(0o700)
        other = hooks / 'pre-push'; other.write_text('#!/bin/sh\nexit 0\n'); other.chmod(0o700)
        self.git('config', 'core.hooksPath', '.githooks')
        p.init(self.root)
        self.git('add', 'code.py')
        rejected = self.git('commit', '-m', 'existing rejection', check=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('previous-hook-rejected', rejected.stdout + rejected.stderr)
        self.assertEqual(previous.read_text(), '#!/bin/sh\nexit 7\n')
        self.assertEqual((self.root / '.crewloom/private/hooks/pre-push').resolve(), other)

    def test_private_source_snapshot_and_original_path_are_not_publishable(self):
        (self.root / 'request.txt').write_text('الرد بالعربي.')
        value = uc.record(self.root, 'owner', 'language', 'الرد بالعربي.', 'request.txt', 'الرد بالعربي.')
        copy = self.root / value['source']['private_copy']
        self.assertEqual(copy.read_text(), 'الرد بالعربي.')
        self.assertEqual(copy.stat().st_mode & 0o777, 0o600)
        self.git('add', 'request.txt')
        self.assertTrue(p.check(self.root))
        with self.assertRaisesRegex(ValueError, 'Private file'):
            p.export(self.root, ['request.txt'], '.crewloom/private/exports/bad.zip')

    def test_private_source_can_be_recorded_without_public_file(self):
        p.private_write(self.root, '.crewloom/private/inputs/message.txt', 'الرد بالعربي.')
        value = uc.record(self.root, 'owner', 'language', 'الرد بالعربي.',
                          '.crewloom/private/inputs/message.txt', 'الرد بالعربي.')
        self.assertTrue(value['source']['path'].startswith('.crewloom/private/inputs/'))

    def test_scan_reads_staged_credential_even_if_worktree_was_cleaned(self):
        (self.root / 'code.py').write_text('credential = "ghp_' + 'A' * 36 + '"\n')
        self.git('add', 'code.py')
        (self.root / 'code.py').write_text('print("clean")\n')
        findings = p.check(self.root)
        self.assertEqual(findings[0]['reason'], 'recognized credential in index blob')
        self.assertNotIn('A' * 36, json.dumps(findings))

    def test_export_is_explicit_owner_only_and_does_not_publish(self):
        (self.root / 'personal.txt').write_text('private notes not selected')
        result = p.export(self.root, ['code.py'], '.crewloom/private/exports/public.zip')
        packet = self.root / result['packet']
        self.assertFalse(result['published'])
        self.assertEqual(packet.stat().st_mode & 0o777, 0o600)
        with zipfile.ZipFile(packet) as archive:
            self.assertEqual(archive.namelist(), ['code.py'])
        with self.assertRaisesRegex(ValueError, 'already exists'):
            p.export(self.root, ['code.py'], result['packet'])

    def test_export_alias_symlink_and_credentials_refused(self):
        (self.root / '.env').write_text('private')
        (self.root / 'folder').mkdir()
        (self.root / 'alias.py').symlink_to(self.root / 'code.py')
        for name in ('folder/../.env', 'alias.py', '.crewloom/private/note.txt'):
            with self.assertRaises(ValueError):
                p.export(self.root, [name], '.crewloom/private/exports/reject.zip')
        (self.root / 'code.py').write_text('sk-' + 'A' * 32)
        with self.assertRaisesRegex(ValueError, 'credential'):
            p.export(self.root, ['code.py'], '.crewloom/private/exports/reject.zip')

    def test_hook_removal_is_detected_and_tracked_private_files_are_reported(self):
        p.init(self.root)
        (self.root / '.crewloom/private/hooks/pre-commit').unlink()
        with self.assertRaisesRegex(ValueError, 'missing or changed'):
            p.init(self.root)
        (self.root / '.env').write_text('private')
        self.git('add', '-f', '.env')
        self.assertTrue(p.check(self.root))

    def test_alternate_commit_index_is_scanned_and_foreign_index_is_refused(self):
        index = self.root / '.git' / 'privacy-index'
        environment = repo_map.git_environment()
        environment['GIT_INDEX_FILE'] = str(index)
        subprocess.run(['git', 'read-tree', '--empty'], cwd=self.root, env=environment, check=True)
        (self.root / 'code.py').write_text('ghp_' + 'A' * 36)
        subprocess.run(['git', 'add', 'code.py'], cwd=self.root, env=environment, check=True)
        with patch.dict(os.environ, {'GIT_INDEX_FILE': str(index)}):
            self.assertTrue(p.check(self.root))
        with patch.dict(os.environ, {'GIT_INDEX_FILE': str(self.root / 'foreign-index')}):
            with self.assertRaisesRegex(ValueError, 'does not belong'):
                p.check(self.root)

    def test_old_source_paths_are_registered_during_setup(self):
        (self.root / 'old-request.txt').write_text('private preference')
        store = uc.load(self.root)
        store['records'] = [{'id': 1, 'user_id': 'owner', 'key': 'preference', 'task_id': None,
                             'kind': 'statement', 'value': 'private preference',
                             'source': {'path': 'old-request.txt', 'quote': 'private preference'}}]
        p.private_write(self.root, uc.RELATIVE, json.dumps(store).encode())
        p.init(self.root)
        self.git('add', 'old-request.txt')
        self.assertTrue(p.check(self.root))

    def test_user_record_enables_guard_automatically(self):
        (self.root / 'request.txt').write_text('private preference')
        uc.record(self.root, 'owner', 'preference', 'private preference', 'request.txt', 'private preference')
        self.git('add', 'request.txt')
        result = self.git('commit', '-m', 'reject conversation', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('private path', result.stdout + result.stderr)

    def test_private_input_and_output_names_cannot_escape_their_namespace(self):
        with self.assertRaisesRegex(ValueError, 'inside private inputs'):
            uc.evidence(self.root, '.crewloom/private/inputs/../git-policy.json', 'anything')
        with self.assertRaisesRegex(ValueError, 'packet belongs'):
            p.export(self.root, ['code.py'], '.crewloom/private/exports/../../leak.zip')

    def test_setup_protects_existing_installed_memory_without_duplicate_rules(self):
        (self.root / '.gitignore').write_text('node_modules/\n')
        p.init(self.root)
        memory = '.agents/skills/context-guardian/brain/COMPLETED.md'
        self.assertEqual(self.git('check-ignore', memory, check=False).returncode, 0)
        before = (self.root / '.gitignore').read_text()
        p.init(self.root)
        self.assertEqual((self.root / '.gitignore').read_text(), before)


if __name__ == '__main__':
    unittest.main()
