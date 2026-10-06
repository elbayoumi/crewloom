"""Independent privacy checks use real Git indexes and preserve local user data."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import check_repository as gate
import crewloom
import project_binding as binding
import repo_map
import task_coordinator as coordinator

ROOT = Path(__file__).resolve().parents[1]


class ProjectPrivacyBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-private-acceptance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.git('init', '-q')

    def git(self, *args, root=None):
        return subprocess.run(['git', '-C', str(root or self.root), *args],
                              env=repo_map.git_environment(), check=True,
                              capture_output=True, timeout=10).stdout

    def file(self, name, text='private fixture only\n'):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        return p

    def ignored(self, name):
        result = subprocess.run(['git', '-C', str(self.root), 'check-ignore', '--no-index', '-q', name],
                                env=repo_map.git_environment(), capture_output=True, timeout=10)
        return result.returncode == 0

    def test_installed_memory_and_runtime_are_ignored_before_use(self):
        installed, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        self.assertFalse(errors)
        self.assertEqual(installed, ['context-guardian'])
        for name in ['.crewloom/context/private.json', '.crewloom/tasks/task/backups/module.py',
                     '.agents/skills/context-guardian/brain/COMPLETED.md',
                     '.claude/skills/context-guardian/brain/CHALLENGES.md',
                     '.env.local', '.codex/hooks.json', '.claude/settings.json',
                     '.opencode/plugins/crewloom-lifecycle.js']:
            self.assertTrue(self.ignored(name), name)
        self.assertFalse(self.ignored('.agents/skills/context-guardian/SKILL.md'))
        self.assertFalse(self.ignored('src/module.py'))
        self.assertFalse(self.ignored('crewloom.project.json'))

    def test_force_install_preserves_existing_private_memory(self):
        crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        p = self.file('.agents/skills/context-guardian/brain/COMPLETED.md', 'keep exact user memory\n')
        _, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], True)
        self.assertFalse(errors)
        self.assertEqual(p.read_text(), 'keep exact user memory\n')

    def test_claude_install_ignores_memory_without_ignoring_instructions(self):
        _, errors = crewloom.install_skills(self.root, 'claude', ['context-guardian'], False)
        self.assertFalse(errors)
        self.assertTrue(self.ignored('.claude/skills/context-guardian/brain/IDEAS_VAULT.md'))
        self.assertFalse(self.ignored('.claude/skills/context-guardian/SKILL.md'))

    def test_later_negative_rules_cannot_reinclude_private_state(self):
        p = self.file('.gitignore', '.crewloom/\n!.crewloom/\n!.crewloom/private.json\n')
        binding.ignore_local_state(self.root, role_memory=True)
        self.assertTrue(self.ignored('.crewloom/private.json'))
        before = p.read_bytes()
        self.assertIsNone(binding.ignore_local_state(self.root, role_memory=True))
        self.assertEqual(before, p.read_bytes())

    def test_user_rules_and_non_ascii_names_are_preserved(self):
        p = self.file('.gitignore', 'custom-output/\n# محفوظ\n')
        binding.ignore_local_state(self.root, role_memory=True)
        self.assertTrue(p.read_text().startswith('custom-output/\n# محفوظ\n'))
        self.assertTrue(self.ignored('.crewloom/مشروع مستقل/نسخة.json'))

    def test_new_negation_after_the_block_is_repaired(self):
        binding.ignore_local_state(self.root, role_memory=True)
        p = self.root / '.gitignore'
        p.write_text(p.read_text() + '!.crewloom/\n!.crewloom/private.json\n')
        binding.ignore_local_state(self.root, role_memory=True)
        self.assertTrue(self.ignored('.crewloom/private.json'))

    def test_forced_private_index_entry_is_detected(self):
        p = self.file('.crewloom/context/private.json')
        binding.ignore_local_state(self.root)
        self.git('add', '-f', '--', str(p))
        self.assertEqual(binding.tracked_private_paths(self.root), ['.crewloom/context/private.json'])

    def test_tracked_data_blocks_install_without_deleting_or_overwriting(self):
        p = self.file('.agents/skills/context-guardian/brain/COMPLETED.md', 'preserve\n')
        self.git('add', '--', str(p))
        before = self.git('ls-files', '--stage', '-z')
        installed, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], True)
        self.assertEqual(installed, [])
        self.assertTrue(errors)
        self.assertFalse((self.root / '.gitignore').exists())
        self.assertFalse((p.parent.parent / 'SKILL.md').exists())
        self.assertEqual(p.read_text(), 'preserve\n')
        self.assertEqual(before, self.git('ls-files', '--stage', '-z'))

    def test_tracked_data_blocks_bootstrap_before_metadata_creation(self):
        p = self.file('.env.local')
        self.git('add', '--', str(p))
        with self.assertRaises(ValueError):
            binding.bootstrap(self.root, project_id='private-project')
        self.assertFalse((self.root / '.crewloom').exists())
        self.assertFalse((self.root / '.gitignore').exists())
        self.assertEqual(p.read_text(), 'private fixture only\n')

    def test_bootstrap_keeps_declarative_policy_trackable_and_binding_private(self):
        binding.bootstrap(self.root, project_id='private-project')
        self.assertFalse(self.ignored('crewloom.project.json'))
        self.git('add', '--', 'crewloom.project.json')
        self.assertEqual(binding.tracked_private_paths(self.root, role_memory=True), [])
        self.assertTrue(self.ignored('.crewloom/binding.json'))

    def test_plain_directory_is_supported_without_using_parent_git(self):
        plain = self.root / 'plain'
        plain.mkdir()
        self.assertEqual(binding.tracked_private_paths(plain), [])
        binding.ignore_local_state(plain, role_memory=True)
        self.assertTrue((plain / '.gitignore').exists())

    def test_symlink_gitignore_is_refused_before_role_writes(self):
        outside = self.file('outside-ignore', 'unchanged\n')
        (self.root / '.gitignore').symlink_to(outside)
        _, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        self.assertTrue(errors)
        self.assertFalse((self.root / '.agents').exists())
        self.assertEqual(outside.read_text(), 'unchanged\n')

    def test_hardlinked_gitignore_is_refused(self):
        outside = self.file('original-ignore', 'unchanged\n')
        os.link(outside, self.root / '.gitignore')
        with self.assertRaises(ValueError):
            binding.ignore_local_state(self.root, role_memory=True)
        self.assertEqual(outside.read_text(), 'unchanged\n')

    def test_exported_foreign_git_environment_cannot_hide_selected_index(self):
        foreign = self.root / 'foreign'
        foreign.mkdir()
        self.git('init', '-q', root=foreign)
        p = self.file('.crewloom/tasks/private.json')
        self.git('add', '-f', '--', str(p))
        with patch.dict(os.environ, {'GIT_DIR': str(foreign / '.git'), 'GIT_WORK_TREE': str(foreign)}):
            self.assertEqual(binding.tracked_private_paths(self.root), ['.crewloom/tasks/private.json'])
        self.assertEqual(self.git('ls-files', '-z', root=foreign), b'')

    def test_symlink_git_marker_is_refused(self):
        plain = self.root / 'alias'
        plain.mkdir()
        (plain / '.git').symlink_to(self.root / '.git')
        with self.assertRaises(ValueError):
            binding.tracked_private_paths(plain)

    def test_templates_and_actual_project_memory_are_distinguished(self):
        p = self.file('.agents/skills/context-guardian/brain/ARCHITECTURE.md')
        self.git('add', '--', str(p))
        self.assertEqual(binding.tracked_private_paths(self.root), [])
        self.assertEqual(binding.tracked_private_paths(self.root, role_memory=True),
                         ['.agents/skills/context-guardian/brain/ARCHITECTURE.md'])
        self.assertTrue(binding.library_source(ROOT))
        self.assertFalse(binding.library_source(self.root))

    def test_negative_then_clean_case_passes_the_actual_gate_main(self):
        self.file('LICENSE', 'Fixture license\n')
        self.file('.agents/skills/fixture/SKILL.md', 'Fixture role\n')
        self.file('REPOSITORY_SCOPE.json', (ROOT / 'REPOSITORY_SCOPE.json').read_text())
        p = self.file('.crewloom/backups/private.json')
        binding.ignore_local_state(self.root)
        self.git('add', '-f', '--', str(p))
        with patch.object(gate, 'load_validator', return_value=SimpleNamespace(check=lambda name: [])):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(gate.main(['--skip-tests'], root=self.root), 0)
                self.git('rm', '--cached', '--', str(p))
                self.assertEqual(gate.main(['--skip-tests'], root=self.root), 0)
        self.assertTrue(p.exists(), 'Untracking must preserve the user file')

    def test_generated_nested_paths_are_private_but_sources_are_not(self):
        for name in ['dashboard/node_modules/module/index.js', 'dashboard/.next/cache.json',
                     'scripts/x.egg-info/PKG-INFO', 'src/__pycache__/x.pyc', '.env.production',
                     'nested/run.log', 'dashboard/tsconfig.tsbuildinfo']:
            self.assertTrue(binding.private_project_path(name), name)
        for name in ['src/index.py', 'examples/reference.json', 'documentation/release.md', '.env.example']:
            self.assertFalse(binding.private_project_path(name), name)

    def test_privacy_cli_is_read_only_and_refuses_forced_private_add(self):
        binding.ignore_local_state(self.root, role_memory=True)
        self.git('add', '--', '.gitignore')
        before = self.git('ls-files', '--stage', '-z')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(binding.main(['privacy', '--project', str(self.root)]), 0)
        self.assertEqual(before, self.git('ls-files', '--stage', '-z'))
        self.assertFalse((self.root / '.crewloom').exists())
        p = self.file('.crewloom/backups/preserved.json')
        self.git('add', '-f', '--', str(p))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(binding.main(['privacy', '--project', str(self.root)]), 2)
        self.assertTrue(p.exists())

    def test_privacy_cli_reports_missing_effective_ignore_policy(self):
        result = binding.privacy_report(self.root)
        self.assertEqual(result['status'], 'not_ready')
        self.assertTrue(result['missing_ignore_probes'])
        self.assertFalse((self.root / '.gitignore').exists())

    # R34: local ignore coverage is not portable publication coverage.
    def stage_ignore(self, text, name='.gitignore'):
        self.file(name, text)
        self.git('add', '--', name)

    def privacy_rules(self):
        binding.ignore_local_state(self.root, role_memory=True)
        return (self.root / '.gitignore').read_text(encoding='utf-8')

    def test_info_exclude_alone_does_not_make_publication_ready(self):
        rules = self.privacy_rules()
        (self.root / '.gitignore').unlink()
        exclude = self.root / '.git/info/exclude'
        exclude.write_text(rules, encoding='utf-8')
        result = binding.privacy_report(self.root)
        self.assertEqual(result['missing_ignore_probes'], [], 'local effective policy is complete')
        self.assertTrue(result['local_only_ignore_probes'])
        self.assertTrue(result['missing_portable_ignore_probes'])
        self.assertEqual(result['status'], 'not_ready')

    def test_global_excludes_file_alone_does_not_make_publication_ready(self):
        rules = self.privacy_rules()
        (self.root / '.gitignore').unlink()
        outside = self.root.parent / (self.root.name + '-global-ignore')
        outside.write_text(rules, encoding='utf-8')
        self.addCleanup(outside.unlink)
        self.git('config', 'core.excludesFile', str(outside))
        result = binding.privacy_report(self.root)
        self.assertEqual(result['status'], 'not_ready')
        self.assertTrue(result['missing_portable_ignore_probes'])

    def test_unstaged_worktree_ignore_file_is_not_the_staged_policy(self):
        self.privacy_rules()  # written to the working tree, never staged
        result = binding.privacy_report(self.root)
        self.assertEqual(result['status'], 'not_ready')
        self.assertTrue(result['missing_portable_ignore_probes'])
        self.assertTrue((self.root / '.gitignore').is_file(), 'local file is preserved')

    def test_staged_ignore_file_is_accepted(self):
        self.stage_ignore(self.privacy_rules())
        result = binding.privacy_report(self.root)
        self.assertEqual(result['missing_portable_ignore_probes'], [])
        self.assertEqual(result['local_only_ignore_probes'], [])
        self.assertEqual(result['status'], 'ready')

    def test_staged_negation_after_the_owned_block_is_reported(self):
        self.stage_ignore(self.privacy_rules() + '!.env.local\n')
        result = binding.privacy_report(self.root)
        self.assertIn('.env.local', result['missing_portable_ignore_probes'])
        self.assertEqual(result['status'], 'not_ready')

    def commit(self, message):
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', message)

    def test_nested_staged_negation_that_exposes_private_state_is_reported(self):
        self.stage_ignore(self.privacy_rules())
        self.stage_ignore('!.crewloom/\n!.env.local\n', 'nested/.gitignore')
        result = binding.privacy_report(self.root)
        self.assertEqual(result['missing_portable_ignore_probes'], [])
        self.assertIn('nested/.crewloom/privacy-check.json', result['nested_negation_gaps'])
        self.assertIn('nested/.env.local', result['nested_negation_gaps'])
        self.assertEqual(result['status'], 'not_ready')

    def test_harmless_nested_ignore_rules_and_unrelated_negations_are_accepted(self):
        self.stage_ignore(self.privacy_rules())
        self.stage_ignore('*.tmp\n!keep.txt\n', 'nested/.gitignore')
        result = binding.privacy_report(self.root)
        self.assertEqual(result['nested_negation_gaps'], [])
        self.assertEqual(result['status'], 'ready')

    def test_unmerged_ignore_policy_is_never_ready(self):
        self.file('seed.txt')
        self.stage_ignore('base\n')
        self.git('add', '--', 'seed.txt')
        self.commit('base')
        base = self.git('rev-parse', '--abbrev-ref', 'HEAD').decode().strip()
        self.git('checkout', '-q', '-b', 'other')
        self.stage_ignore(self.privacy_rules() + 'from-other\n')
        self.commit('other')
        self.git('checkout', '-q', base)
        self.stage_ignore(self.privacy_rules() + 'from-base\n')
        self.commit('mine')
        merge = subprocess.run(['git', '-C', str(self.root), 'merge', 'other'], env=repo_map.git_environment(),
                               capture_output=True, timeout=20)
        self.assertNotEqual(merge.returncode, 0, 'fixture must produce a real conflict')
        self.assertIn(b'U', self.git('status', '--porcelain', '--', '.gitignore')[:2])
        result = binding.privacy_report(self.root)
        self.assertEqual(result['unmerged_ignore_files'], ['.gitignore'])
        self.assertEqual(result['status'], 'not_ready')

    def test_a_resolved_ignore_policy_after_the_same_merge_is_accepted(self):
        self.stage_ignore(self.privacy_rules())
        self.commit('clean')
        result = binding.privacy_report(self.root)
        self.assertEqual((result['unmerged_ignore_files'], result['status']), ([], 'ready'))

    def test_report_does_not_modify_index_or_worktree(self):
        self.stage_ignore(self.privacy_rules())
        before = (self.git('ls-files', '--stage'), (self.root / '.gitignore').read_bytes())
        binding.privacy_report(self.root)
        after = (self.git('ls-files', '--stage'), (self.root / '.gitignore').read_bytes())
        self.assertEqual(before, after)

    def test_privacy_cli_does_not_call_plain_directory_verified(self):
        plain = self.root / 'plain'
        plain.mkdir()
        binding.ignore_local_state(plain, role_memory=True)
        result = binding.privacy_report(plain)
        self.assertFalse(result['git_index_checked'])
        self.assertEqual(result['status'], 'not_ready')

    def test_worktree_gets_independent_private_memory_from_the_same_project(self):
        _, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        self.assertFalse(errors)
        root_binding = binding.bootstrap(self.root, project_id='private-project')['binding']
        memory = self.file('.agents/skills/context-guardian/brain/COMPLETED.md', 'same-project evidence\n')
        self.git('add', '--', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        target = self.root / '.crewloom/worktrees/task'
        target.parent.mkdir(parents=True)
        self.git('worktree', 'add', '-q', '-b', 'fixture-task', str(target))
        meta = {'root': self.root, 'binding': root_binding,
                'workflows': {'task': {'plan': {'steps': [{'role': 'context-guardian', 'kind': 'model'}]}}}}
        child = coordinator._bind_worktree(meta, target, lambda *a, **kw: None)
        self.assertEqual(child['project_id'], root_binding['project_id'])
        self.assertNotEqual(child['checkout_id'], root_binding['checkout_id'])
        copy = target / memory.relative_to(self.root)
        self.assertEqual(copy.read_text(), 'same-project evidence\n')
        self.assertNotEqual(copy.stat().st_ino, memory.stat().st_ino)
        copy.write_text('only this task changed\n')
        coordinator._bind_worktree(meta, target, lambda *a, **kw: None)
        self.assertEqual(copy.read_text(), 'only this task changed\n')
        self.assertEqual(memory.read_text(), 'same-project evidence\n')
        self.assertEqual(binding.tracked_private_paths(target, role_memory=True), [])
        self.assertEqual(binding.privacy_report(target)['status'], 'ready')

    def test_library_templates_remain_public_in_its_real_linked_worktree(self):
        self.file('.agents/skills/context-guardian/brain/COMPLETED.md', 'public template\n')
        self.git('add', '--', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        target = self.root / '.crewloom/worktrees/library-task'
        target.parent.mkdir(parents=True)
        self.git('worktree', 'add', '-q', '-b', 'fixture-library-task', str(target))
        with patch('crewloom_resources.distribution_root', return_value=self.root):
            self.assertTrue(binding.library_source(target))

    def test_dangling_git_marker_is_refused(self):
        plain = self.root / 'dangling'
        plain.mkdir()
        (plain / '.git').symlink_to(self.root / 'absent.git')
        with self.assertRaises(ValueError):
            binding.tracked_private_paths(plain)

    def test_custom_declarative_configuration_remains_trackable(self):
        name = 'private config[1].json'
        self.file(name, json.dumps(binding.default_config('private-project')))
        binding.bootstrap(self.root, project_id='private-project', config_path=name)
        self.assertFalse(self.ignored(name))
        self.assertFalse(self.ignored('private config1.json'))

    def test_forced_ignored_custom_configuration_is_refused_without_writes(self):
        name = 'private-config.json'
        self.file(name, json.dumps(binding.default_config('private-project')))
        self.file('.gitignore', name + '\n')
        self.git('add', '-f', '--', name)
        with self.assertRaises(ValueError):
            binding.bootstrap(self.root, project_id='private-project', config_path=name)
        self.assertFalse((self.root / '.crewloom').exists())

    def test_force_added_arbitrary_ignored_project_data_is_rejected(self):
        self.file('.gitignore', 'tenant-private/\n')
        p = self.file('tenant-private/customer export.csv')
        self.git('add', '-f', '--', str(p))
        self.assertEqual(binding.tracked_private_paths(self.root), ['tenant-private/customer export.csv'])
        self.assertTrue(p.exists())

    def test_environment_templates_remain_trackable(self):
        binding.ignore_local_state(self.root, role_memory=True)
        self.assertFalse(self.ignored('.env.example'))
        self.assertFalse(self.ignored('.env.template'))


if __name__ == '__main__':
    unittest.main()
