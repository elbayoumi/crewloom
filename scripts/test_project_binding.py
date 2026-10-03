"""Project identity, safe bootstrap, relocation, agency ledger validation and lifecycle ownership."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import crewloom
import project_binding as pb
import project_lessons
import repo_map
import workflow as w

ROLE = 'context-guardian'
CLI = Path(__file__).parent / 'crewloom.py'


def write_config(root, **changes):
    config = pb.default_config('sample-project')
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key].update(value)
        else:
            config[key] = value
    (root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
    return config


def git(root, *argv):
    # A fixture must never inherit the repository, index or configuration of a committing
    # checkout, so every fixture Git child starts from the cleared environment.
    subprocess.run(['git', *argv], cwd=root, check=True, capture_output=True,
                   env=repo_map.git_environment())


class ProjectBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        git(self.root, 'init', '-q')
        self.installed, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'auth.py').write_text('def login(user):\n    return user\n', encoding='utf-8')
        (self.root / 'AGENTS.md').write_text('# Customer rules\nNever rewrite this line.\n', encoding='utf-8')
        self.constitution = (self.root / 'AGENTS.md').read_text()
        self.brain = self.root / '.agents' / 'skills' / ROLE / 'brain' / 'COMPLETED.md'
        self.brain.write_text('# Completed\n\nLocal history stays here.\n', encoding='utf-8')

    def enter(self, **kwargs):
        arguments = {'root': self.root, 'project_id': 'sample-project', 'task_id': 'login-fix',
                     'role': ROLE, 'seeds': ['auth.py']}
        arguments.update(kwargs)
        return pb.enter(**arguments)

    def agency_case(self, project_id='agency-project', status='in_progress', owner=ROLE, evidence=True,
                    verified='2026-10-01T00:00:00+00:00'):
        """Agency workspace fixture using the exact ledger contract: active_dir is agency-relative."""
        agency = self.root.parent / (self.root.name + '-agency')
        project = agency / '04_Clients' / 'Active' / ('Client_' + project_id)
        if not project.is_dir():
            project.mkdir(parents=True)
            shutil.copytree(self.root / '.agents', project / '.agents')
            git(project, 'init', '-q')
            (project / 'auth.py').write_text('def login(user):\n    return user\n', encoding='utf-8')
        for base in (agency, project):
            target = base / '.agents' / 'skills' / owner
            if not (target / 'SKILL.md').is_file():
                target.mkdir(parents=True)
                (target / 'SKILL.md').write_text('# ' + owner + '\n', encoding='utf-8')
        (project / 'context-snapshot.md').write_text('# snapshot\n', encoding='utf-8')
        observed = project / 'state-evidence.md'
        observed.write_text('# evidence\n', encoding='utf-8')
        entry = {'id': project_id,
                 'active_dir': str(project.relative_to(agency)),
                 'context_snapshot': str((project / 'context-snapshot.md').relative_to(agency)),
                 'delivery_owner': owner, 'control_status': status,
                 'last_verified_at': None if status == 'needs_reconciliation' else verified,
                 'next_action': {'owner': owner, 'output': 'status.md', 'acceptance': 'evidence recorded'}}
        if evidence and status != 'needs_reconciliation':
            entry['state_evidence'] = {'path': str(observed.relative_to(agency)),
                                       'sha256': pb.file_digest(observed),
                                       'source_type': 'staging_observation',
                                       'observed_at': verified}
        registry = agency / '.agents' / 'project-control' / 'registry.json'
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({'schema_version': 1, 'projects': [entry]}), encoding='utf-8')
        return project, agency, registry

    def test_first_entry_creates_a_complete_and_idempotent_footprint(self):
        first = self.enter()
        self.assertEqual(sorted(first['created']), sorted([pb.CONFIG_NAME, pb.BINDING_RELATIVE, '.gitignore']))
        binding = json.loads((self.root / pb.BINDING_RELATIVE).read_text())
        self.assertEqual(binding['project_root'], str(self.root))
        self.assertEqual(len(binding['checkout_id']), 32)
        self.assertEqual(binding['project_id'], 'sample-project')
        self.assertEqual(binding['config_path'], pb.CONFIG_NAME)
        self.assertEqual((self.root / '.gitignore').read_text(), '.crewloom/\n')
        for name in ('index', 'context', 'tasks', 'lessons'):
            self.assertTrue((self.root / '.crewloom' / name).is_dir())
        second = self.enter()
        self.assertEqual(second['created'], [])
        self.assertEqual(json.loads((self.root / pb.BINDING_RELATIVE).read_text())['checkout_id'], binding['checkout_id'])
        self.assertEqual((self.root / 'AGENTS.md').read_text(), self.constitution)
        self.assertIn('Local history stays here.', self.brain.read_text())

    def test_portable_configuration_declares_tooling_not_client_ownership(self):
        self.enter()
        config = json.loads((self.root / pb.CONFIG_NAME).read_text())
        self.assertEqual(config['tooling'], {'vendor': 'Rumuze', 'tool': 'Crewloom', 'role': 'tooling',
                                             'owns_client_code': False})
        text = (self.root / pb.CONFIG_NAME).read_text()
        self.assertNotIn(str(self.root), text)
        for word in ('token', 'secret', 'password', 'api_key'):
            self.assertNotIn(word, text.casefold())

    def test_missing_and_ambiguous_identity_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            fresh = Path(folder).resolve() / 'fresh'
            fresh.mkdir()
            shutil.copytree(self.root / '.agents', fresh / '.agents')
            (fresh / 'auth.py').write_text('def login(): pass\n')
            git(fresh, 'init', '-q')
            with self.assertRaisesRegex(ValueError, 'Explicit project identity'):
                pb.enter(fresh, None, 'login-fix', ROLE)
            self.assertFalse((fresh / pb.CONFIG_NAME).exists())
        write_config(self.root, project_id='other-project')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.enter()
        write_config(self.root, project_id='sample-project')
        self.enter()
        self.enter()

    def test_foreign_binding_blocks_entry_before_any_write(self):
        self.enter()
        with tempfile.TemporaryDirectory() as other:
            copy = Path(other).resolve() / 'copied'
            shutil.copytree(self.root, copy)
            (copy / pb.CONFIG_NAME).unlink()
            with self.assertRaisesRegex(ValueError, 'another checkout'):
                pb.enter(copy, 'sample-project', 'login-fix', ROLE)
            self.assertFalse((copy / pb.CONFIG_NAME).exists())

    def test_corrupt_binding_blocks_bootstrap_before_config_is_written(self):
        (self.root / '.crewloom').mkdir()
        (self.root / pb.BINDING_RELATIVE).write_text('{"schema_version": 1', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Malformed local project binding'):
            pb.enter(self.root, 'sample-project', 'login-fix', ROLE)
        self.assertFalse((self.root / pb.CONFIG_NAME).exists())

    def test_malformed_configuration_blocks_the_project(self):
        (self.root / pb.CONFIG_NAME).write_text('{not json', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            self.enter()
        config = pb.default_config('sample-project')
        config['policy']['mode'] = 'sometimes'
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Policy mode'):
            self.enter()

    def test_schema_violations_are_rejected_explicitly(self):
        cases = [
            ({'schema_version': 2}, 'schema_version'),
            ({'project_id': 'Bad Name'}, 'explicit lowercase project_id'),
            ({'source_roots': ['/absolute']}, 'project-relative'),
            ({'source_roots': ['../escape']}, 'parent traversal'),
            ({'language': 'fr'}, 'en or ar'),
            ({'budgets': {'map_bytes': 10, 'context_bytes': 4096, 'lesson_budget_bytes': 0}}, 'map_bytes'),
            ({'host_adapter': {'enabled': True, 'files': ['README.md']}}, 'host_adapter.files'),
            ({'extra_field': 1}, 'Unknown project configuration'),
        ]
        for patch, message in cases:
            with self.subTest(patch=patch):
                config = pb.default_config('sample-project')
                config.update(patch)
                (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, message):
                    pb.load_config(self.root)

    def test_ownership_claim_in_attribution_is_rejected(self):
        config = pb.default_config('sample-project')
        config['tooling']['owns_client_code'] = True
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'owns_client_code'):
            pb.load_config(self.root)

    def test_enforced_mode_bootstraps_a_consistent_managed_lifecycle(self):
        write_config(self.root, policy={'mode': 'enforced', 'managed_lifecycle': True})
        result = self.enter()
        self.assertEqual(result['policy_mode'], 'enforced')
        self.assertEqual(result['lifecycle'], 'managed-runner')
        self.assertEqual(pb.default_config('sample-project', 'enforced')['policy']['managed_lifecycle'], True)
        write_config(self.root, policy={'mode': 'enforced', 'managed_lifecycle': False})
        with self.assertRaisesRegex(ValueError, 'managed lifecycle'):
            self.enter(task_id='second-task')
        write_config(self.root, policy={'mode': 'observe', 'managed_lifecycle': True})
        self.assertEqual(self.enter()['lifecycle'], 'managed-runner')
        write_config(self.root, policy={'mode': 'observe', 'managed_lifecycle': False})
        self.assertEqual(self.enter()['lifecycle'], 'instruction-assisted')

    def test_symlinked_and_escaping_metadata_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            (self.root / '.crewloom').symlink_to(Path(other), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                self.enter()
            (self.root / '.crewloom').unlink()
        with self.assertRaisesRegex(ValueError, 'escapes selected project'):
            self.enter(config_path='../outside.json')
        self.assertFalse((self.root.parent / 'outside.json').exists())

    def test_hardlinked_configuration_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            pb.write_json(self.root, pb.CONFIG_NAME, pb.default_config('sample-project'))
            external = Path(other) / 'copy.json'
            external.write_text((self.root / pb.CONFIG_NAME).read_text())
            (self.root / pb.CONFIG_NAME).unlink()
            os.link(str(external), str(self.root / pb.CONFIG_NAME))
            with self.assertRaisesRegex(ValueError, 'hardlink'):
                self.enter()

    def test_non_git_root_is_reported_unsupported_and_never_initialized(self):
        with tempfile.TemporaryDirectory() as folder:
            plain = Path(folder).resolve() / 'plain'
            plain.mkdir()
            shutil.copytree(self.root / '.agents', plain / '.agents')
            (plain / 'auth.py').write_text('def login(): pass\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Git project'):
                pb.enter(plain, 'plain-project', 'login-fix', ROLE)
            self.assertFalse((plain / '.git').exists())

    def test_unborn_head_repository_is_supported(self):
        self.assertFalse((self.root / '.crewloom' / 'index' / 'map.json').exists())
        result = self.enter()
        self.assertEqual(result['status'], 'active')
        import repo_map
        _, stats = repo_map.build(self.root)
        self.assertEqual(stats['head'], '')
        self.assertEqual(stats['files'], 1)

    def test_relocation_rebuilds_caches_and_keeps_durable_memory(self):
        self.enter()
        binding = pb.load_binding(self.root)
        lesson = project_lessons.record(self.root, binding, 'Map cache identity must match the checkout',
                                        'Store project and checkout IDs in every generation')['lesson']
        original = self.root
        moved = self.root.parent / (self.root.name + '-moved')
        shutil.move(str(self.root), str(moved))
        self.root = moved.resolve()
        with self.assertRaisesRegex(ValueError, 'another checkout'):
            self.enter()
        result = pb.rebind(self.root, 'sample-project', 'worktree relocated')
        self.assertEqual(result['project_id'], 'sample-project')
        self.assertEqual(result['relocated_from'], str(original))
        self.assertFalse((self.root / '.crewloom' / 'index' / 'map.json').exists())
        self.assertFalse((self.root / '.crewloom' / 'context' / 'login-fix.json').exists())
        self.assertTrue((self.root / '.crewloom' / 'lessons' / (lesson['id'] + '.json')).is_file())
        self.assertIn(ROLE, result['preserved_role_memory'])
        self.assertTrue(result['durable_lessons_kept'])
        binding = pb.load_binding(self.root)
        self.assertEqual(binding['project_root'], str(self.root))
        self.assertEqual(binding['relocations'][-1]['to'], str(moved))
        self.enter()

    def test_relocation_cannot_rename_the_project(self):
        self.enter()
        with self.assertRaisesRegex(ValueError, 'cannot change project identity'):
            pb.rebind(self.root, 'renamed-project', 'operator request')

    def test_two_projects_with_identical_filenames_stay_isolated(self):
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder).resolve() / 'twin'
            other.mkdir()
            shutil.copytree(self.root / '.agents', other / '.agents')
            (other / 'auth.py').write_text((self.root / 'auth.py').read_text())
            git(other, 'init', '-q')
            pb.enter(other, 'twin-project', 'login-fix', ROLE, seeds=['auth.py'])
            mine = self.enter()
            theirs = pb.status(other, 'twin-project')
            self.assertNotEqual(mine['checkout_id'], theirs['checkout_id'])
            self.assertNotEqual(mine['context']['sha256'], theirs['tasks'][0]['context']['sha256'])
            self.assertNotEqual(mine['project_id'], theirs['project_id'])

    def test_unbound_legacy_cache_adopts_a_new_binding_but_foreign_identity_blocks(self):
        import repo_map
        repo_map.build(self.root)
        cache = self.root / '.crewloom' / 'index' / 'map.json'
        value = json.loads(cache.read_text())
        self.assertIsNone(value['project_id'])
        self.enter()
        value = json.loads(cache.read_text())
        self.assertEqual(value['prior_state'], 'rebuilt-unbound-cache')
        self.assertEqual(value['project_id'], 'sample-project')
        _, stats = repo_map.build(self.root)
        self.assertEqual(stats['prior_state'], 'reused-generation')
        value['project_id'] = 'other-project'
        cache.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'another project or checkout'):
            repo_map.build(self.root)

    def test_configured_source_roots_control_the_scan(self):
        import repo_map
        (self.root / 'ui').mkdir(); (self.root / 'server').mkdir()
        (self.root / 'ui' / 'page.ts').write_text('export function page() { return 1; }\n')
        (self.root / 'server' / 'api.py').write_text('def api():\n    pass\n')
        write_config(self.root, source_roots=['ui'])
        self.enter()
        config, _ = pb.load_config(self.root)
        value, _ = repo_map.build(self.root, config=config)
        self.assertEqual(set(value['files']), {'ui/page.ts'})
        write_config(self.root, source_roots=['server'])
        config, _ = pb.load_config(self.root)
        value, _ = repo_map.build(self.root, config=config)
        self.assertEqual(set(value['files']), {'server/api.py'})
        write_config(self.root, source_roots=['../outside'])
        with self.assertRaisesRegex(ValueError, 'parent traversal'):
            self.enter()
        write_config(self.root, source_roots=['alias'])
        (self.root / 'alias').symlink_to(self.root / 'server')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.enter()
        (self.root / 'alias').unlink()
        write_config(self.root, source_roots=['missing-dir'])
        with self.assertRaisesRegex(ValueError, 'not a directory'):
            self.enter()

    def test_second_task_in_the_same_root_is_rejected_while_one_is_reserved(self):
        self.enter()
        with self.assertRaisesRegex(ValueError, 'already has an active context task'):
            self.enter(task_id='other-task')
        self.assertEqual(pb.reservation(self.root)['task_id'], 'login-fix')

    def test_unfinished_managed_workflow_blocks_another_context_task(self):
        plan = {'schema_version': 1, 'id': 'login-fix', 'steps': [
            {'id': 'review', 'role': ROLE, 'summary': 'Review output', 'kind': 'task',
             'inputs': ['auth.py'], 'outputs': ['result.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        self.assertEqual(w.run(self.root, parsed, fingerprint, 'image')['status'], 'awaiting_task')
        with self.assertRaisesRegex(ValueError, 'unfinished managed workflow'):
            self.enter(task_id='other-task')

    def test_native_context_task_blocks_a_different_managed_workflow(self):
        self.enter()
        plan = {'schema_version': 1, 'id': 'other-workflow', 'steps': [
            {'id': 'review', 'role': ROLE, 'summary': 'Review output', 'kind': 'task',
             'inputs': ['auth.py'], 'outputs': ['result.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        with self.assertRaisesRegex(ValueError, 'reserved by native context task'):
            w.run(self.root, parsed, fingerprint, 'image')

    def test_status_is_read_only_and_reports_lifecycle_honestly(self):
        self.enter()
        report = pb.status(self.root, 'sample-project')
        self.assertEqual(report['project_id'], 'sample-project')
        self.assertEqual(report['lifecycle'], 'instruction-assisted')
        self.assertFalse(report['host_callbacks_verified'])
        self.assertEqual(report['tasks'][0]['status'], 'active')
        with self.assertRaisesRegex(ValueError, 'Unknown project task'):
            pb.status(self.root, 'sample-project', 'missing-task')

    def test_task_identity_is_never_inferred(self):
        with self.assertRaisesRegex(ValueError, 'Explicit kebab-case --task-id'):
            self.enter(task_id=None)
        with self.assertRaisesRegex(ValueError, 'Explicit kebab-case --role'):
            self.enter(role=None)

    def test_host_instruction_block_is_bounded_idempotent_and_authorized_only(self):
        write_config(self.root, host_adapter={'enabled': True, 'files': ['AGENTS.md', 'CLAUDE.md']})
        first = self.enter()
        self.assertEqual(sorted(first['instructions_updated']), ['AGENTS.md', 'CLAUDE.md'])
        agents = (self.root / 'AGENTS.md').read_text()
        self.assertTrue(agents.startswith('# Customer rules\nNever rewrite this line.'))
        self.assertIn(pb.MARKER_START, agents)
        self.assertIn('instruction-assisted', agents)
        self.assertEqual(agents.count(pb.MARKER_START), 1)
        snapshot = (self.root / 'CLAUDE.md').read_text()
        second = self.enter()
        self.assertEqual((self.root / 'AGENTS.md').read_text(), agents)
        self.assertEqual((self.root / 'CLAUDE.md').read_text(), snapshot)
        self.assertEqual(sorted(second['instructions_updated']), ['AGENTS.md', 'CLAUDE.md'])
        self.assertLess(len(agents.encode()), pb.MAX_INSTRUCTION_BYTES + 512)
        write_config(self.root, host_adapter={'enabled': False, 'files': ['AGENTS.md']})
        self.enter()
        self.assertEqual((self.root / 'AGENTS.md').read_text(), agents)
        self.assertIn('Local history stays here.', self.brain.read_text())

    def test_unbalanced_markers_are_refused(self):
        (self.root / 'AGENTS.md').write_text('# Customer rules\n' + pb.MARKER_START + '\nno end\n')
        write_config(self.root, host_adapter={'enabled': True, 'files': ['AGENTS.md']})
        with self.assertRaisesRegex(ValueError, 'Unbalanced'):
            self.enter()

    def test_disabling_context_does_not_delete_memory_or_loosen_isolation(self):
        self.enter()
        binding = pb.load_binding(self.root)
        lesson = project_lessons.record(self.root, binding, 'Cache identity must be checked',
                                        'Compare project and checkout IDs')['lesson']
        write_config(self.root, policy={'mode': 'off', 'managed_lifecycle': False})
        result = self.enter()
        self.assertIsNone(result['context'])
        self.assertTrue((self.root / '.crewloom' / 'lessons' / (lesson['id'] + '.json')).is_file())
        self.assertIn('Local history stays here.', self.brain.read_text())
        self.assertEqual(pb.status(self.root)['policy_mode'], 'off')
        with w.lock(w.safe_path(self.root, '.crewloom', internal=True)):
            with self.assertRaisesRegex(ValueError, 'locked'):
                self.enter(task_id='third-task')

    def test_cli_requires_explicit_project_and_task_identity(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            pb.main(['enter', '--project-id', 'sample-project'])
        self.assertEqual(error.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            pb.main(['status'])
        self.assertEqual(error.exception.code, 2)

    def test_agency_ledger_validates_control_status_and_reconciliation(self):
        project, agency, registry = self.agency_case()
        report = pb.agency_registry(str(registry), str(agency), project)
        self.assertEqual(report['project_id'], 'agency-project')
        self.assertFalse(report['evidence_only'])
        self.assertEqual(report['control_status'], 'in_progress')
        result = pb.enter(project, 'agency-project', 'login-fix', ROLE, seeds=['auth.py'],
                           registry_path=str(registry), agency_root=str(agency))
        self.assertFalse(result['evidence_only'])
        self.assertEqual(pb.status(project)['tasks'][-1]['registry_control_status'], 'in_progress')

    def test_needs_reconciliation_is_evidence_only_and_blocks_enforced_mode(self):
        project, agency, registry = self.agency_case(status='needs_reconciliation', evidence=False)
        result = pb.enter(project, 'agency-project', 'login-fix', ROLE, seeds=['auth.py'],
                          registry_path=str(registry), agency_root=str(agency))
        self.assertTrue(result['evidence_only'])
        write_config(project, project_id='agency-project',
                     policy={'mode': 'enforced', 'managed_lifecycle': True})
        with self.assertRaisesRegex(ValueError, 'evidence gathering only'):
            pb.enter(project, 'agency-project', 'login-fix', ROLE, seeds=['auth.py'],
                     registry_path=str(registry), agency_root=str(agency))

    def test_blocked_status_is_evidence_only(self):
        project, agency, registry = self.agency_case(status='blocked')
        report = pb.agency_registry(str(registry), str(agency), project)
        self.assertTrue(report['evidence_only'])

    def test_invalid_ledger_entries_are_rejected(self):
        project, agency, registry = self.agency_case()
        baseline = json.loads(registry.read_text())
        top = json.loads(json.dumps(baseline))
        top['schema_version'] = 2
        registry.write_text(json.dumps(top), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'schema_version 1'):
            pb.agency_registry(str(registry), str(agency), project)
        cases = [
            ({'control_status': 'active'}, 'control_status'),
            ({'active_dir': '/absolute/path'}, 'relative path'),
            ({'active_dir': '../../elsewhere'}, 'escapes the agency workspace root'),
            ({'delivery_owner': 'unknown-role'}, 'installed role'),
            ({'context_snapshot': 'missing/snapshot.md'}, 'context_snapshot'),
            ({'last_verified_at': 'not-a-date'}, 'last_verified_at'),
            ({'state_evidence': {'path': 'x.md', 'sha256': 'a' * 64,
                                 'source_type': 'gossip', 'observed_at': '2026-10-01T00:00:00+00:00'}},
             'source_type'),
        ]
        for patch, message in cases:
            with self.subTest(patch=patch):
                broken = json.loads(json.dumps(baseline))
                broken['projects'][0].update(patch)
                registry.write_text(json.dumps(broken), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, message):
                    pb.agency_registry(str(registry), str(agency), project)
        registry.write_text(json.dumps(baseline), encoding='utf-8')
        self.assertTrue(pb.agency_registry(str(registry), str(agency), project))

    def test_changed_state_evidence_blocks_the_ledger(self):
        project, agency, registry = self.agency_case()
        (project / 'state-evidence.md').write_text('# changed\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed since observation'):
            pb.agency_registry(str(registry), str(agency), project)

    def test_unregistered_root_and_missing_registry_are_rejected(self):
        project, agency, registry = self.agency_case()
        with self.assertRaisesRegex(ValueError, 'not registered'):
            pb.agency_registry(str(registry), str(agency), self.root)
        with self.assertRaisesRegex(ValueError, 'not found|invalid'):
            pb.enter(project, 'agency-project', 'login-fix', ROLE,
                     registry_path=str(project / 'missing.json'), agency_root=str(agency))
        with self.assertRaisesRegex(ValueError, 'agency workspace root'):
            pb.enter(project, 'agency-project', 'login-fix', ROLE, registry_path=str(registry))

    def test_explicitly_selected_agency_validator_runs_first(self):
        project, agency, registry = self.agency_case()
        validator = agency / 'agency-validator.py'
        validator.write_text('import sys\nraise SystemExit(1 if "--blocked" in sys.argv else 0)\n',
                             encoding='utf-8')
        pb.enter(project, 'agency-project', 'login-fix', ROLE, seeds=['auth.py'],
                 registry_path=str(registry), agency_root=str(agency),
                 agency_validator=str(validator))
        validator.write_text('raise SystemExit(1)\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'validator blocked'):
            pb.enter(project, 'agency-project', 'login-fix', ROLE, seeds=['auth.py'],
                     registry_path=str(registry), agency_root=str(agency),
                     agency_validator=str(validator))

    def test_no_second_client_registry_is_created_in_the_project(self):
        self.enter()
        names = sorted(path.name for path in (self.root / '.crewloom').iterdir())
        self.assertEqual(names, ['active_task.json', 'binding.json', 'context', 'index', 'lessons', 'tasks'])

    def test_local_state_ignore_rule_preserves_existing_rules_and_stays_idempotent(self):
        (self.root / '.gitignore').write_text('build/\n*.log\n', encoding='utf-8')
        first = self.enter()
        self.assertIn('.gitignore', first['created'])
        self.assertEqual((self.root / '.gitignore').read_text(), 'build/\n*.log\n.crewloom/\n')
        self.assertEqual(self.enter()['created'], [])
        self.assertEqual((self.root / '.gitignore').read_text(), 'build/\n*.log\n.crewloom/\n')
        with tempfile.TemporaryDirectory() as folder:
            relocated = Path(folder).resolve() / 'relocated'
            shutil.copytree(self.root, relocated, symlinks=True,
                            ignore=shutil.ignore_patterns('.git', '.crewloom', '__pycache__'))
            git(relocated, 'init', '-q')
            again = pb.enter(relocated, 'sample-project', 'login-fix', ROLE, seeds=['auth.py'])
            self.assertNotIn('.gitignore', again['created'])
            self.assertEqual(again['created'], [pb.BINDING_RELATIVE])
            self.assertEqual((relocated / '.gitignore').read_text(), 'build/\n*.log\n.crewloom/\n')

    def test_claimed_failure_fails_closed_and_cannot_be_relabelled(self):
        self.enter()
        report = pb.finish(self.root, 'sample-project', 'login-fix', [],
                           [{'command': ['python3', '-m', 'unittest'], 'exit_code': 3,
                             'scope': 'login unit test'}])
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['verified'])
        self.assertEqual(report['failed_commands'], [['python3', '-m', 'unittest']])
        self.assertIsNone(pb.reservation(self.root))
        again = pb.finish(self.root, 'sample-project', 'login-fix', [],
                          [{'command': ['python3', '-m', 'unittest'], 'exit_code': 0}])
        self.assertEqual(again['status'], 'failed')
        self.assertTrue(again['idempotent'])
        self.assertFalse(again['relabelled'])

    def test_native_cli_entry_is_accepted_and_persists_a_context_file(self):
        result = subprocess.run(['python3', str(CLI), 'project', 'enter', '--project', str(self.root),
                                 '--project-id', 'sample-project', '--task-id', 'login-fix',
                                 '--role', ROLE, '--seed', 'auth.py', '--language', 'ar'],
                                capture_output=True, text=True, cwd=str(CLI.parent))
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['status'], 'active')
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        self.assertEqual(stored['scope']['language'], 'ar')
        self.assertEqual(stored['scope']['project_id'], 'sample-project')
        repeat = subprocess.run(['python3', str(CLI), 'project', 'enter', '--project', str(self.root),
                                 '--project-id', 'sample-project', '--task-id', 'login-fix',
                                 '--role', ROLE, '--seed', 'auth.py', '--language', 'ar'],
                                capture_output=True, text=True, cwd=str(CLI.parent))
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        again = json.loads(repeat.stdout)
        self.assertEqual(again['context']['generation'], payload['context']['generation'])
        self.assertFalse(again['context']['written'])
        finish = subprocess.run(['python3', str(CLI), 'project', 'finish', '--project', str(self.root),
                                 '--project-id', 'sample-project', '--task-id', 'login-fix',
                                 '--verification', json.dumps(
                                     [{'command': ['python3', '-m', 'unittest'], 'exit_code': 0,
                                       'scope': 'login unit test'}])],
                                 capture_output=True, text=True, cwd=str(CLI.parent))
        self.assertEqual(finish.returncode, 2, finish.stdout)
        # A claimed exit code is an attestation; only executed evidence completes a task.
        self.assertEqual(json.loads(finish.stdout)['status'], 'awaiting_verification')
        self.assertFalse(json.loads(finish.stdout)['verified'])


if __name__ == '__main__':
    unittest.main()