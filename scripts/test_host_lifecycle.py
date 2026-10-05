"""Native lifecycle adapter boundaries: install, guard, callbacks and verification stay honest.

Every case here is offline. No host provider is called, no authentication is read, and no global
configuration is written. The Docker cases run only when the parent sets CREWLOOM_DOCKER_TESTS=1,
because the managed acceptance ledger is the only thing that may ever promote a task.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10 have no TOML reader in the standard library
    tomllib = None

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))
import crewloom
import host_lifecycle as hl
import project_binding as pb
import repo_map
import workflow as w

PROJECT = 'native-fixture'
ROLE = 'context-guardian'
CRITERIA = 'criteria.md'
SOURCE_FILE = 'src/login.py'
DECLARED = 'out/report.txt'
UNUSED_OUTPUT = 'out/other.txt'
ACCEPTANCE_PLAN = 'acceptance.json'
ACCEPTANCE_ARGV = ['python3', '-m', 'unittest', 'discover', '-s', 'tests']


def patch_text(*records):
    """Render a real apply_patch payload. A move is an Update record plus its Move to endpoint."""
    lines = ['*** Begin Patch']
    for operation, name, body, *rest in records:
        move_to = rest[0] if rest else None
        lines.append('*** ' + operation.capitalize() + ' File: ' + name)
        if move_to:
            lines.append('*** Move to: ' + move_to)
        if operation == 'add':
            lines.append('+' + body)
        elif operation == 'update':
            lines.extend(['@@', '-' + body, '+' + body + ' edited'])
    lines.append('*** End Patch')
    return '\n'.join(lines) + '\n'


class Fixture(unittest.TestCase):
    """A disposable bound project with a role, a criteria file, a source and an acceptance plan."""

    def setUp(self):
        # A machine without the host installed (hosted CI) reports no version; fall back to the
        # supported release these fixtures were written against. A real host still wins.
        real_version = hl._version_of
        fallback = {'codex': 'codex-cli 0.155.1', 'opencode': '1.18.32'}
        patcher = mock.patch.object(hl, '_version_of',
                                    side_effect=lambda host: real_version(host) or fallback.get(host))
        patcher.start()
        self.addCleanup(patcher.stop)
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-native-lifecycle-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.git('init', '-q')
        self.git('config', 'gc.auto', '0')
        self.git('config', 'maintenance.auto', 'false')
        self.git('config', 'user.name', 'Native lifecycle fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        installed, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertFalse(errors)
        self.assertEqual(installed, [ROLE])
        config = pb.default_config(PROJECT, 'enforced')
        config['policy']['managed_lifecycle'] = True
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        pb.bootstrap(self.root, project_id=PROJECT)
        (self.root / 'src').mkdir()
        (self.root / SOURCE_FILE).write_text(
            'def login(user):\n    """Authenticate a user."""\n    return user\n', encoding='utf-8')
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / '__init__.py').write_text('"""Native lifecycle fixture tests."""\n',
                                                   encoding='utf-8')
        (self.root / 'tests' / 'test_login.py').write_text(
            'import unittest\n\nfrom src.login import login\n\n\n'
            'class LoginTest(unittest.TestCase):\n'
            '    def test_login(self):\n        self.assertEqual(login("a"), "a")\n', encoding='utf-8')
        (self.root / 'tests' / 'test_acceptance.py').write_text(
            'import unittest\nfrom pathlib import Path\n\n'
            'REPORT = ' + repr(DECLARED) + '\n\n\n'
            'class AcceptanceTest(unittest.TestCase):\n'
            '    def test_declared_report_is_written(self):\n'
            '        path = Path(REPORT)\n        path.parent.mkdir(parents=True, exist_ok=True)\n'
            '        path.write_text("native acceptance executed\\n", encoding="utf-8")\n'
            '        self.assertTrue(path.is_file())\n', encoding='utf-8')
        (self.root / CRITERIA).write_text('- login returns the submitted user\n', encoding='utf-8')
        (self.root / 'out').mkdir()
        self.write_acceptance()
        self.git('add', '.')
        self.git('commit', '-qm', 'Freeze the native lifecycle fixture')

    def git(self, *arguments):
        return subprocess.run(['git', *arguments], cwd=self.root, env=repo_map.git_environment(),
                              capture_output=True, text=True, check=True, timeout=30).stdout.strip()

    def write_acceptance(self, plan_id='native-acceptance'):
        plan = {'schema_version': 1, 'id': plan_id, 'criteria': CRITERIA,
                'steps': [{'id': 'acceptance', 'role': ROLE,
                           'summary': 'Run the fixed acceptance check',
                           'argv': list(ACCEPTANCE_ARGV), 'timeout_seconds': 120,
                           'inputs': ['tests/__init__.py', 'tests/test_login.py',
                                      'tests/test_acceptance.py', 'src/__init__.py', SOURCE_FILE],
                           'outputs': [DECLARED]}]}
        (self.root / 'src' / '__init__.py').write_text('"""Native lifecycle fixture package."""\n',
                                                      encoding='utf-8')
        (self.root / ACCEPTANCE_PLAN).write_text(json.dumps(plan), encoding='utf-8')
        return plan

    def install(self, host='codex', acceptance=True, outputs=(DECLARED,), commands=(), **options):
        return hl.install(self.root, PROJECT, host, ROLE, criteria_path=CRITERIA,
                          seeds=[SOURCE_FILE], sources=[SOURCE_FILE],
                          declared_outputs=list(outputs) + ([UNUSED_OUTPUT] if outputs == (DECLARED,)
                                                             and 'other' in options else []),
                          acceptance={'workflow': ACCEPTANCE_PLAN, 'step': 'acceptance',
                                      'image': w.DEFAULT_IMAGE} if acceptance else None,
                          managed_commands=list(commands), **options)

    def install_default(self, **options):
        return hl.install(self.root, PROJECT, 'codex', ROLE, criteria_path=CRITERIA,
                          seeds=[SOURCE_FILE], sources=[SOURCE_FILE],
                          declared_outputs=[DECLARED],
                          acceptance={'workflow': ACCEPTANCE_PLAN, 'step': 'acceptance',
                                      'image': w.DEFAULT_IMAGE},
                          managed_commands=[{'argv': list(ACCEPTANCE_ARGV), 'cwd': '.'}], **options)

    def install_contract(self, outputs, **options):
        """One installation with an exact declared output set, for a changed-contract case."""
        return hl.install(self.root, PROJECT, 'codex', ROLE, criteria_path=CRITERIA,
                          seeds=[SOURCE_FILE], sources=[SOURCE_FILE], declared_outputs=list(outputs),
                          acceptance={'workflow': ACCEPTANCE_PLAN, 'step': 'acceptance',
                                      'image': w.DEFAULT_IMAGE},
                          managed_commands=[{'argv': list(ACCEPTANCE_ARGV), 'cwd': '.'}], **options)

    def payload(self, **overrides):
        value = {'session_id': 'session-1', 'turn_id': 'turn-1', 'cwd': str(self.root),
                 'host_version': 'codex-cli 0.155.1'}
        value.update(overrides)
        return value


class InstallBoundaries(Fixture):
    def test_install_is_idempotent_and_preserves_unrelated_host_settings(self):
        first = self.install_default()
        control = self.root / '.codex' / 'hooks.json'
        document = json.loads(control.read_text(encoding='utf-8'))
        document['hooks']['SessionStart'].insert(0, {'matcher': 'foreign',
                                                     'hooks': [{'type': 'command',
                                                                'command': 'foreign-keep-me'}]})
        document['unrelated_setting'] = {'kept': True}
        control.write_text(json.dumps(document, indent=2), encoding='utf-8')
        second = self.install_default()
        self.assertEqual(first['payload_sha256'], second['payload_sha256'])
        merged = json.loads(control.read_text(encoding='utf-8'))
        self.assertEqual(merged['unrelated_setting'], {'kept': True})
        commands = [hook['command'] for event in merged['hooks'].values() for group in event
                    for hook in group['hooks']]
        self.assertEqual(commands.count('foreign-keep-me'), 1)
        self.assertEqual(commands.count(second['bridge_command']), len(first['callback_caps']['stages']))
        self.assertEqual(hl.status(self.root, PROJECT, 'codex')['lifecycle'], 'needs-trust')

    def test_uninstall_removes_only_unchanged_owned_items_and_keeps_foreign_ones(self):
        self.install_default()
        report = hl.uninstall(self.root, PROJECT, 'codex')
        self.assertEqual(report['state'], 'removed')
        self.assertEqual(report['conflicts'], [])
        document = json.loads((self.root / '.codex' / 'hooks.json').read_text(encoding='utf-8'))
        self.assertNotIn('hooks', document)
        self.assertIsNone(hl.load_install(self.root, 'codex'))

    def test_an_altered_owned_hook_is_preserved_and_reported_as_a_conflict(self):
        self.install_default()
        control = self.root / '.codex' / 'hooks.json'
        document = json.loads(control.read_text(encoding='utf-8'))
        for event in document['hooks']:
            document['hooks'][event][0]['hooks'][0]['command'] += ' && curl https://example.invalid'
        control.write_text(json.dumps(document, indent=2), encoding='utf-8')
        report = hl.uninstall(self.root, PROJECT, 'codex')
        self.assertEqual(report['state'], 'conflict')
        self.assertTrue(report['conflicts'])
        self.assertEqual(report['removed'], [])
        self.assertTrue(control.is_file())
        self.assertEqual(hl.status(self.root, PROJECT, 'codex')['lifecycle'], 'altered')

    def test_an_unsupported_host_version_is_refused_rather_than_extrapolated(self):
        with self.assertRaisesRegex(hl.LifecycleError, 'Unsupported codex host version 0.155.0'):
            hl.install(self.root, PROJECT, 'codex', ROLE, declared_outputs=[DECLARED],
                       host_version='codex-cli 0.155.0')
        self.assertFalse((self.root / '.codex' / 'hooks.json').exists())

    def test_a_missing_explicit_project_id_never_bootstraps_or_guesses_identity(self):
        before = sorted(item.name for item in self.root.iterdir())
        with self.assertRaisesRegex(hl.LifecycleError, 'project-id is required'):
            hl.install(self.root, '', 'codex', ROLE, declared_outputs=[DECLARED])
        with self.assertRaisesRegex(hl.LifecycleError, 'does not match the local binding'):
            hl.install(self.root, 'some-other-project', 'codex', ROLE, declared_outputs=[DECLARED])
        self.assertEqual(sorted(item.name for item in self.root.iterdir()), before)
        self.assertFalse((self.root / 'crewloom.project.json').with_suffix('.json.bak').exists())

    def test_an_empty_declared_output_set_is_refused(self):
        with self.assertRaisesRegex(hl.LifecycleError, 'declared output files are required'):
            hl.install(self.root, PROJECT, 'codex', ROLE, criteria_path=CRITERIA)
        self.assertFalse((self.root / '.codex' / 'hooks.json').exists())

    def test_two_declared_outputs_that_fold_to_one_file_are_refused(self):
        (self.root / 'out' / 'Report.txt').write_text('existing\n', encoding='utf-8')
        with self.assertRaisesRegex(hl.LifecycleError, 'collapse to one destination'):
            hl.install(self.root, PROJECT, 'codex', ROLE, criteria_path=CRITERIA,
                       declared_outputs=['out/Report.txt', 'out/report.txt'])

    def test_a_role_that_is_not_installed_is_refused_before_any_write(self):
        before = sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*'))
        with self.assertRaisesRegex(hl.LifecycleError, 'Role is not installed'):
            hl.install(self.root, PROJECT, 'codex', 'role-not-installed', criteria_path=CRITERIA,
                       declared_outputs=[DECLARED])
        self.assertEqual(sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*')),
                         before)
        self.assertFalse((self.root / '.codex').exists())

    def test_a_foreign_owner_and_extensions_survive_a_merge_verbatim(self):
        control = self.root / '.codex' / 'hooks.json'
        control.parent.mkdir()
        control.write_text(json.dumps(
            {'owner': 'existing-tool', 'schema_version': 7, 'extension': {'enabled': True},
             'hooks': {'SessionStart': [{'matcher': 'startup',
                                         'hooks': [{'type': 'command', 'command': 'echo existing'}]}]}}),
            encoding='utf-8')
        self.install_default()
        merged = json.loads(control.read_text(encoding='utf-8'))
        self.assertEqual(merged['owner'], 'existing-tool')
        self.assertEqual(merged['schema_version'], 7)
        self.assertEqual(merged['extension'], {'enabled': True})
        self.assertIn({'matcher': 'startup',
                       'hooks': [{'type': 'command', 'command': 'echo existing'}]},
                      merged['hooks']['SessionStart'])

    def test_a_foreign_unmergeable_plugin_file_is_never_replaced(self):
        plugin = self.root / '.opencode' / 'plugins' / 'crewloom-lifecycle.js'
        plugin.parent.mkdir(parents=True)
        plugin.write_text('export const OtherPlugin = async () => ({});\n', encoding='utf-8')
        before = plugin.read_bytes()
        with self.assertRaisesRegex(hl.LifecycleError, 'not owned by this installer'):
            hl.install(self.root, PROJECT, 'opencode', ROLE, criteria_path=CRITERIA,
                       declared_outputs=[DECLARED])
        self.assertEqual(plugin.read_bytes(), before)
        self.assertFalse((self.root / hl.STATE_RELATIVE).exists())

    def test_an_altered_owned_hook_cannot_record_a_new_callback(self):
        self.install_default()
        control = self.root / '.codex' / 'hooks.json'
        document = json.loads(control.read_text(encoding='utf-8'))
        document['hooks']['PreToolUse'] = []
        control.write_text(json.dumps(document), encoding='utf-8')
        before = sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*'))
        with self.assertRaisesRegex(hl.LifecycleError, 'cannot record a callback'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                        config_sha=hl.load_install(self.root, 'codex')['payload_sha256'])
        self.assertEqual(sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*')),
                         before)

    def test_the_state_directory_is_owner_only_and_bounded(self):
        self.install_default()
        folder = self.root / hl.STATE_RELATIVE / 'codex'
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((folder / 'install.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((folder / 'events.jsonl').stat().st_mode & 0o777, 0o600)

    def test_the_installation_identity_covers_the_whole_declared_contract(self):
        first = self.install_default()
        self.assertTrue(first['install_id'])
        # The rendered payload is unchanged by a contract change, so the payload digest alone
        # cannot be the identity of an installation. Re-installing the identical contract is the
        # same installation; changing the declared outputs is a different one.
        self.assertEqual(self.install_default()['install_id'], first['install_id'])
        (self.root / UNUSED_OUTPUT).write_text('extra\n', encoding='utf-8')
        changed = self.install_contract((DECLARED, UNUSED_OUTPUT))
        self.assertNotEqual(changed['install_id'], first['install_id'])
        self.assertEqual(changed['payload_sha256'], first['payload_sha256'])
        record = hl.load_install(self.root, 'codex')
        self.assertEqual(record['install_id'], changed['install_id'])

    def test_a_symlinked_owned_control_path_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix='crewloom-foreign-')).resolve()
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(outside)]))
        (outside / 'hooks.json').write_text('{"hooks": {}}\n', encoding='utf-8')
        (self.root / '.codex').mkdir()
        (self.root / '.codex' / 'hooks.json').symlink_to(outside / 'hooks.json')
        with self.assertRaisesRegex(hl.LifecycleError, 'may not use symlinks'):
            self.install_default()
        self.assertEqual((outside / 'hooks.json').read_text(encoding='utf-8'), '{"hooks": {}}\n')

    def test_a_reserved_root_is_never_stolen_by_an_install(self):
        self.install_default()
        binding = pb.load_binding(self.root)
        pb.reserve(self.root, binding, 'some-other-task', 'other-owner')
        with self.assertRaisesRegex(hl.LifecycleError, 'never steals a reservation'):
            self.install_default()

    def test_a_paused_managed_workflow_blocks_an_install(self):
        binding = pb.load_binding(self.root)
        plan, fingerprint = w.read_plan(self.root, ACCEPTANCE_PLAN)
        w.reserve_workflow(self.root, plan, fingerprint)
        with self.assertRaisesRegex(hl.LifecycleError, 'managed workflow native-acceptance'):
            self.install_default()
        pb.release(self.root, binding['project_id'])

    def test_a_coordinator_reservation_blocks_an_install(self):
        reservation = self.root / '.crewloom' / 'active_coordinator.json'
        reservation.write_text(json.dumps({'schema_version': 1, 'project_root': str(self.root),
                                           'project_id': PROJECT,
                                           'checkout_id': pb.load_binding(self.root)['checkout_id'],
                                           'batch': 'batch-one', 'manifest': 'batch.json',
                                           'manifest_sha256': 'f' * 64,
                                           'reserved_at': pb.now()}), encoding='utf-8')
        with self.assertRaisesRegex(hl.LifecycleError, 'coordinator batch batch-one'):
            self.install_default()

    def test_the_opencode_plugin_payload_is_rendered_with_real_placeholders_only(self):
        record = hl.install(self.root, PROJECT, 'opencode', ROLE, criteria_path=CRITERIA,
                            declared_outputs=[DECLARED])
        plugin = (self.root / '.opencode' / 'plugins' / 'crewloom-lifecycle.js').read_text(encoding='utf-8')
        self.assertNotIn('__CREWLOOM_', plugin)
        self.assertIn(record['payload_sha256'], plugin)
        self.assertIn('CrewloomLifecycle', plugin)
        self.assertEqual(hl.status(self.root, PROJECT, 'opencode')['lifecycle'], 'config-ready')


class GuardBoundaries(Fixture):
    def setUp(self):
        super().setUp()
        self.record = self.install_default()

    def allowed(self, tool, args):
        response = hl.callback(self.root, PROJECT, 'codex', 'PreToolUse',
                               self.payload(tool=tool, args=args))
        self.assertTrue(response['allowed'], response)
        return response

    def denied(self, tool, args):
        response = hl.callback(self.root, PROJECT, 'codex', 'PreToolUse',
                               self.payload(tool=tool, args=args))
        self.assertFalse(response['allowed'])
        self.assertEqual(response['hookSpecificOutput']['hookEventName'], 'PreToolUse')
        self.assertEqual(response['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertTrue(response['hookSpecificOutput']['permissionDecisionReason'])
        return response

    def test_a_declared_output_add_is_allowed(self):
        response = self.allowed('apply_patch', {'command': patch_text(('add', DECLARED, 'done'))})
        self.assertEqual(response['decision']['operations'], ['add'])

    def test_an_undeclared_destination_is_denied(self):
        self.denied('apply_patch', {'command': patch_text(('add', 'out/undeclared.txt', 'no'))})

    def test_runtime_policy_role_memory_and_git_paths_are_denied_in_every_spelling(self):
        for name in ('.crewloom/hosts/codex/install.json', '.git/config', '.agents/skills/x/SKILL.md',
                     '.claude/skills/x/SKILL.md', 'crewloom.project.json', 'CREWLOOM.PROJECT.JSON',
                     '.Crewloom/hosts/codex/install.json'):
            with self.assertRaises(hl.LifecycleError):
                hl.check_endpoint(self.root, name, self.record)

    def test_both_endpoints_of_a_move_are_validated(self):
        record = dict(self.record,
                      declared_output_keys=sorted(w.path_key(n)
                                                  for n in (DECLARED, UNUSED_OUTPUT)))
        text = patch_text(('update', DECLARED, 'old', '.crewloom/escaped.txt'))
        with self.assertRaisesRegex(hl.LifecycleError, 'Runtime, Git, role-memory'):
            hl.guard_file_edits(self.root, record, text)
        text = patch_text(('update', DECLARED, 'old', UNUSED_OUTPUT))
        with self.assertRaisesRegex(hl.LifecycleError, 'not a declared output'):
            hl.guard_file_edits(self.root, self.record, text)
        decision = hl.guard_file_edits(self.root, record, text)
        self.assertEqual(sorted(decision['operations']), ['move-destination', 'update'])

    def test_a_multi_record_patch_is_preflighted_before_any_endpoint_is_allowed(self):
        third = 'out/third.txt'
        text = patch_text(('add', DECLARED, 'fine'), ('add', UNUSED_OUTPUT, 'also fine'),
                          ('delete', third, ''))
        with self.assertRaisesRegex(hl.LifecycleError, 'not a declared output'):
            hl.guard_file_edits(self.root, self.record, text)
        both = dict(self.record,
                    declared_output_keys=sorted(w.path_key(n)
                                                for n in (DECLARED, UNUSED_OUTPUT, third)))
        decision = hl.guard_file_edits(self.root, both, text)
        self.assertEqual(sorted(decision['operations']), ['add', 'delete'])

    def test_one_patch_may_not_touch_one_destination_twice(self):
        text = patch_text(('add', DECLARED, 'a'), ('add', 'out/../' + DECLARED, 'b'))
        with self.assertRaises(hl.LifecycleError):
            hl.guard_file_edits(self.root, self.record, text)

    def test_a_symlinked_destination_is_denied(self):
        outside = Path(tempfile.mkdtemp(prefix='crewloom-foreign-')).resolve()
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(outside)]))
        (outside / 'target.txt').write_text('foreign\n', encoding='utf-8')
        (self.root / 'out' / 'linked.txt').symlink_to(outside / 'target.txt')
        record = dict(self.record,
                      declared_output_keys=sorted(w.path_key(n)
                                                  for n in (DECLARED, UNUSED_OUTPUT, 'out/linked.txt')))
        with self.assertRaises(hl.LifecycleError):
            hl.check_endpoint(self.root, 'out/linked.txt', record)

    def test_a_hardlinked_destination_is_denied_and_the_foreign_file_survives(self):
        outside = Path(tempfile.mkdtemp(prefix='crewloom-foreign-')).resolve()
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(outside)]))
        shared = outside / 'shared.txt'
        shared.write_text('shared\n', encoding='utf-8')
        os.link(str(shared), str(self.root / 'out' / 'hard.txt'))
        record = dict(self.record,
                      declared_output_keys=sorted(w.path_key(n)
                                                  for n in (DECLARED, UNUSED_OUTPUT, 'out/hard.txt')))
        with self.assertRaisesRegex(hl.LifecycleError, 'without hardlinks'):
            hl.check_endpoint(self.root, 'out/hard.txt', record)
        self.assertEqual(shared.read_text(encoding='utf-8'), 'shared\n')

    def test_a_physical_case_alias_destination_is_denied(self):
        (self.root / 'out' / 'Report.txt').write_text('existing\n', encoding='utf-8')
        if not (self.root / 'out' / 'report.txt').exists():
            self.skipTest('Actual case-insensitive filesystem required; the macOS CI job proves it')
        record = dict(self.record,
                      declared_output_keys=sorted(w.path_key(n)
                                                  for n in (DECLARED, UNUSED_OUTPUT, 'out/report.txt')))
        with self.assertRaisesRegex(hl.LifecycleError, 'physical case alias'):
            hl.check_endpoint(self.root, 'out/report.txt', record)

    def test_the_managed_command_allowlist_is_exact_and_not_a_substring(self):
        self.allowed('shell', {'command': ' '.join(ACCEPTANCE_ARGV), 'workdir': str(self.root)})
        self.denied('shell', {'command': 'python3 -m unittest discover -s tests && rm -rf /',
                              'workdir': str(self.root)})
        self.denied('shell', {'command': ' '.join(ACCEPTANCE_ARGV), 'workdir': '/tmp'})
        self.denied('shell', {'command': 'echo ' + ' '.join(ACCEPTANCE_ARGV),
                              'workdir': str(self.root)})
        self.denied('shell', {'command': 'python3 -c "import os"', 'workdir': str(self.root)})

    def test_an_unknown_hosted_tool_is_denied_under_strict_policy(self):
        response = self.denied('web_search', {'query': 'anything'})
        self.assertIn('web_search', response['hookSpecificOutput']['permissionDecisionReason'])

    def test_the_opencode_guard_returns_a_raised_error_instead_of_a_decision_object(self):
        opencode = hl.install(self.root, PROJECT, 'opencode', ROLE, criteria_path=CRITERIA,
                              declared_outputs=[DECLARED])
        response = hl.callback(self.root, PROJECT, 'opencode', 'tool.execute.before',
                               {'session_id': 'session-1', 'turn_id': 'turn-1', 'cwd': str(self.root),
                                'call_id': 'call-1', 'tool': 'patch',
                                'args': {'patchText': patch_text(('add', 'out/nope.txt', 'no'))}})
        self.assertFalse(response['allowed'])
        self.assertTrue(response['thrown'])
        self.assertIn('not a declared output', response['error'])
        self.assertEqual(opencode['callback_caps']['guard_tools'], ['patch', 'write', 'edit', 'bash'])

    def test_a_host_agent_may_not_edit_its_own_guard(self):
        self.denied('apply_patch', {'command': patch_text(('add', '.codex/hooks.json', '{}'))})


class CallbackBoundaries(Fixture):
    def setUp(self):
        super().setUp()
        self.record = self.install_default()

    def test_a_foreign_working_directory_is_refused_before_any_state_is_written(self):
        before = sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*'))
        with self.assertRaisesRegex(hl.LifecycleError, 'not the bound canonical root'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                        self.payload(cwd='/tmp'), config_sha=self.record['payload_sha256'])
        self.assertEqual(sorted(str(item.relative_to(self.root)) for item in self.root.rglob('*')),
                         before)

    def test_a_foreign_project_id_in_the_payload_is_refused(self):
        with self.assertRaisesRegex(hl.LifecycleError, 'foreign project ID'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                        self.payload(project_id='another-project'),
                        config_sha=self.record['payload_sha256'])

    def test_a_copied_payload_digest_is_refused_before_any_state_is_written(self):
        with self.assertRaisesRegex(hl.LifecycleError, 'copied or altered hook configuration'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                        config_sha='a' * 64)

    def test_an_unknown_host_version_is_refused(self):
        with self.assertRaisesRegex(hl.LifecycleError, 'host version does not match'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                        self.payload(host_version='codex-cli 0.155.0'),
                        config_sha=self.record['payload_sha256'])

    def test_a_missing_session_or_turn_is_refused_and_no_anonymous_task_is_created(self):
        with self.assertRaisesRegex(hl.LifecycleError, 'real host session ID'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                        self.payload(session_id=None), config_sha=self.record['payload_sha256'])
        with self.assertRaisesRegex(hl.LifecycleError, 'real host turn ID'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                        self.payload(turn_id=None), config_sha=self.record['payload_sha256'])

    def test_session_start_prepares_a_session_scope_without_inventing_a_turn(self):
        response = hl.callback(self.root, PROJECT, 'codex', 'SessionStart',
                               {'session_id': 'session-1', 'cwd': str(self.root)},
                               config_sha=self.record['payload_sha256'])
        self.assertEqual(response['scope'], 'session')
        self.assertEqual(response['session_task_id'], response['task_id'])
        state = pb.task_state(self.root, response['task_id'])
        self.assertIsNone(state, 'SessionStart must not create a frozen generation by itself')
        self.assertEqual(pb.reservation(self.root)['task_id'], response['task_id'])

    def test_an_unsupported_event_name_is_refused(self):
        with self.assertRaisesRegex(hl.LifecycleError, 'Unsupported codex lifecycle event'):
            hl.callback(self.root, PROJECT, 'codex', 'SessionRotated', self.payload(),
                        config_sha=self.record['payload_sha256'])

    def test_a_stop_hook_that_is_already_active_does_not_re_run_acceptance(self):
        response = hl.callback(self.root, PROJECT, 'codex', 'Stop',
                               self.payload(stop_hook_active=True),
                               config_sha=self.record['payload_sha256'])
        self.assertTrue(response['skipped'])
        self.assertFalse(response['verified'])
        self.assertEqual(len([item for item in hl.observed_events(self.root, 'codex')
                              if item.get('stage') == 'verify']), 0)

    def test_an_unrelated_turn_may_not_steal_a_reserved_root(self):
        hl.callback(self.root, PROJECT, 'codex', 'SessionStart',
                    {'session_id': 'session-1', 'cwd': str(self.root)},
                    config_sha=self.record['payload_sha256'])
        held = pb.reservation(self.root)
        binding = pb.load_binding(self.root)
        (self.root / pb.RESERVATION_RELATIVE).write_text(json.dumps(
            {'schema_version': pb.SCHEMA_VERSION, 'project_root': str(self.root),
             'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
             'task_id': 'host-codex-0000000000000000', 'owner': 'other-owner',
             'reserved_at': pb.now()}), encoding='utf-8')
        with self.assertRaisesRegex(hl.LifecycleError, 'did not take the reservation'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                        self.payload(session_id='session-2'), config_sha=self.record['payload_sha256'])
        self.assertEqual(pb.reservation(self.root)['task_id'], 'host-codex-0000000000000000')
        self.assertIsNotNone(held)

    def test_an_interrupted_scope_is_re_entered_by_a_retry_with_the_same_scope(self):
        first = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                            config_sha=self.record['payload_sha256'])
        state = pb.task_state(self.root, first['task_id'])
        self.assertEqual(state['status'], 'active')
        state['status'] = 'interrupted'
        pb.save_task_state(self.root, state)
        again = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                            config_sha=self.record['payload_sha256'])
        self.assertEqual(again['task_id'], first['task_id'])
        self.assertEqual(pb.reservation(self.root)['task_id'], first['task_id'])
        self.assertEqual(pb.task_state(self.root, first['task_id'])['status'], 'active')

    def test_a_different_host_session_gets_a_different_task_scope(self):
        first = hl.task_scope('codex', self.root, pb.load_binding(self.root),
                              self.record['payload_sha256'], 'session-1', 'turn-1')
        second = hl.task_scope('codex', self.root, pb.load_binding(self.root),
                               self.record['payload_sha256'], 'session-2', 'turn-1')
        self.assertNotEqual(first['task_id'], second['task_id'])
        self.assertNotEqual(first['scope_sha256'], second['scope_sha256'])
        self.assertEqual(first, hl.task_scope('codex', self.root, pb.load_binding(self.root),
                                              self.record['payload_sha256'], 'session-1', 'turn-1'),
                         'the same scope must be re-enterable deterministically')
        self.assertNotEqual(first['scope_sha256'], hl.task_scope(
            'codex', self.root, pb.load_binding(self.root), self.record['payload_sha256'],
            'session-1', 'turn-2')['scope_sha256'],
            'a different turn of one session is a different scope, not a shared task')
        self.assertEqual(first['task_id'], hl.task_scope(
            'codex', self.root, pb.load_binding(self.root), self.record['payload_sha256'],
            'session-1', 'turn-2')['task_id'],
            'one session holds one reservation and one frozen generation')
        self.assertNotEqual(first['task_id'], hl.task_scope('opencode', self.root,
                                                           pb.load_binding(self.root),
                                                           self.record['payload_sha256'],
                                                           'session-1', 'turn-1')['task_id'])

    def test_a_second_live_session_may_not_steal_the_reserved_root(self):
        first = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                            config_sha=self.record['payload_sha256'])
        with self.assertRaisesRegex(hl.LifecycleError, 'did not take the reservation'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                        self.payload(session_id='session-2'),
                        config_sha=self.record['payload_sha256'])
        self.assertEqual(pb.reservation(self.root)['task_id'], first['task_id'])

    def test_injection_carries_complete_mandatory_bodies_and_the_marker(self):
        response = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                               config_sha=self.record['payload_sha256'])
        context = response['additionalContext']
        self.assertIn('login returns the submitted user', context)
        rule = (self.root / '.agents' / 'skills' / ROLE / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn(rule.strip().splitlines()[0], context)
        self.assertIn('def login(user):', context)
        self.assertIn(self.record['marker'], context)
        self.assertLessEqual(response['context_bytes'], response['context_limit'])

    def test_the_delivery_marker_never_appears_in_a_prompt_source_or_instruction_file(self):
        hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                    config_sha=self.record['payload_sha256'])
        marker = self.record['marker']
        for name in ('AGENTS.md', CRITERIA, SOURCE_FILE, 'tests/test_login.py', '.codex/hooks.json',
                     pb.CONFIG_NAME, 'tests/__init__.py'):
            path = self.root / name
            if path.is_file():
                self.assertNotIn(marker, path.read_text(encoding='utf-8'), name)
        self.assertIn(marker, (self.root / hl.STATE_RELATIVE / 'codex' / 'install.json')
                      .read_text(encoding='utf-8'))

    def test_mandatory_content_beyond_the_configured_limit_is_refused_not_truncated(self):
        narrow = self.install_default(context_limit=256)
        with self.assertRaisesRegex(hl.LifecycleError, 'exceed the configured host context limit'):
            hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                        config_sha=narrow['payload_sha256'])

    def test_a_checkpoint_invalidates_the_generation_so_the_next_turn_is_fresh(self):
        first = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                            config_sha=self.record['payload_sha256'])
        (self.root / SOURCE_FILE).write_text('def login(user):\n    """Authenticate."""\n'
                                             '    return (user, True)\n', encoding='utf-8')
        response = hl.callback(self.root, PROJECT, 'codex', 'PostToolUse',
                               self.payload(args={'changed_paths': [SOURCE_FILE]}),
                               config_sha=self.record['payload_sha256'])
        self.assertEqual(response['declared_changes'], [SOURCE_FILE])
        self.assertTrue(response['invalidated'])
        second = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                             config_sha=self.record['payload_sha256'])
        self.assertNotEqual(second['context_semantic_sha256'], first['context_semantic_sha256'])
        self.assertIn('return (user, True)', second['additionalContext'])

    def test_a_stop_event_without_configured_acceptance_is_never_a_verified_success(self):
        plain = hl.install(self.root, PROJECT, 'codex', ROLE, criteria_path=CRITERIA,
                           seeds=[SOURCE_FILE], sources=[SOURCE_FILE],
                           declared_outputs=[DECLARED], acceptance=None)
        response = hl.callback(self.root, PROJECT, 'codex', 'Stop', self.payload(),
                               config_sha=plain['payload_sha256'])
        self.assertFalse(response['verified'])
        self.assertFalse(response['attempted'])
        self.assertEqual(hl.status(self.root, PROJECT, 'codex')['verified_executor'], False)

    def test_a_fabricated_native_claim_never_promotes_to_verified(self):
        def lying_runner(root, plan, fingerprint, image):
            return {'status': 'complete', 'steps': {plan['steps'][0]['id']: {'status': 'complete'}}}

        hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                    config_sha=self.record['payload_sha256'])
        response = hl.callback(self.root, PROJECT, 'codex', 'Stop', self.payload(),
                               config_sha=self.record['payload_sha256'], runner=lying_runner)
        self.assertFalse(response['verified'])
        self.assertTrue(response['attempted'])
        self.assertIn('not complete in the recorded ledger', response['reason'])
        self.assertEqual(hl.status(self.root, PROJECT, 'codex')['verified_executor'], False)
        self.assertEqual(pb.task_state(self.root, response['task_id'])['status'], 'active')

    def test_an_idle_or_session_end_event_leaves_the_task_incomplete_and_records_no_lesson(self):
        hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                    config_sha=self.record['payload_sha256'])
        for event in ('SessionEnd',):
            response = hl.callback(self.root, PROJECT, 'codex', event, self.payload(),
                                   config_sha=self.record['payload_sha256'])
            self.assertTrue(response['closed'])
            self.assertFalse(response['verified'])
        state = pb.task_state(self.root, response['task_id'])
        self.assertEqual(state['status'], 'active')
        self.assertEqual(state.get('lessons', []), [])

    def test_a_stale_output_hash_keeps_finalization_unverified(self):
        def stale_runner(root, plan, fingerprint, image):
            (self.root / DECLARED).write_text('stale\n', encoding='utf-8')
            return {'status': 'complete', 'steps': {plan['steps'][0]['id']: {'status': 'complete'}}}

        response = hl.callback(self.root, PROJECT, 'codex', 'Stop', self.payload(),
                               config_sha=self.record['payload_sha256'], runner=stale_runner)
        self.assertFalse(response['verified'])

    def test_status_never_conflates_installed_observed_and_verified(self):
        self.assertEqual(hl.status(self.root, PROJECT, 'codex')['lifecycle'], 'needs-trust')
        self.assertFalse(hl.status(self.root, PROJECT, 'codex')['observed_events'])
        hl.callback(self.root, PROJECT, 'codex', 'SessionStart',
                    {'session_id': 'session-1', 'cwd': str(self.root)},
                    config_sha=self.record['payload_sha256'])
        report = hl.status(self.root, PROJECT, 'codex')
        self.assertEqual(report['lifecycle'], 'observed')
        self.assertTrue(report['observed_events'])
        self.assertFalse(report['verified_executor'])
        self.assertFalse(report['delivered'])

    def test_an_installed_configuration_is_never_reported_as_delivered(self):
        # The control config exists on disk, so this installation is configured. A configured host
        # is not a host that received anything: delivery is an observed successful injection.
        installed = hl.status(self.root, PROJECT, 'codex')
        self.assertTrue(installed['installed'])
        self.assertTrue(installed['config_ready'])
        self.assertTrue(installed['content_intact'])
        self.assertEqual(installed['observed_callbacks'], 0)
        self.assertFalse(installed['delivered'])
        self.assertFalse(installed['verified_executor'])
        hl.callback(self.root, PROJECT, 'codex', 'SessionStart',
                    {'session_id': 'session-1', 'cwd': str(self.root)},
                    config_sha=self.record['payload_sha256'])
        prepared = hl.status(self.root, PROJECT, 'codex')
        self.assertFalse(prepared['delivered'], 'a prepare callback delivered no context')
        hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                    config_sha=self.record['payload_sha256'])
        delivered = hl.status(self.root, PROJECT, 'codex')
        self.assertTrue(delivered['delivered'])
        self.assertEqual(delivered['observed_events'], ['SessionStart', 'UserPromptSubmit'])
        self.assertFalse(delivered['verified_executor'], 'delivery is not verification')

    def test_a_changed_installation_inherits_no_observation_or_delivery(self):
        injected = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                               config_sha=self.record['payload_sha256'])
        self.assertTrue(injected['injected'])
        observed = hl.status(self.root, PROJECT, 'codex')
        self.assertTrue(observed['delivered'])
        pb.cancel(self.root, PROJECT, injected['task_id'], 'The installed contract is being replaced')
        (self.root / UNUSED_OUTPUT).write_text('another declared output\n', encoding='utf-8')
        changed = self.install_contract((DECLARED, UNUSED_OUTPUT))
        self.assertNotEqual(changed['install_id'], observed['install_id'])
        report = hl.status(self.root, PROJECT, 'codex')
        self.assertTrue(report['config_ready'])
        self.assertFalse(report['delivered'], 'the previous contract delivered nothing here')
        self.assertEqual(report['observed_callbacks'], 0)
        self.assertFalse(report['verified_executor'])
        # The evidence of the previous installation is kept, not deleted; it simply cannot answer
        # for the one that replaced it.
        history = hl.observed_events(self.root, 'codex')
        self.assertTrue(any(item.get('install_id') == observed['install_id'] for item in history))
        self.assertEqual(report['unattributed_events'], len(history) - 1)

    def test_a_finished_session_task_does_not_freeze_the_next_turn_of_that_session(self):
        first = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                            config_sha=self.record['payload_sha256'])
        self.assertEqual(first['task_state'], 'active')
        pb.cancel(self.root, PROJECT, first['task_id'], 'The first turn ended')
        source = self.root / SOURCE_FILE
        source.write_text(source.read_text(encoding='utf-8') + '\n# SECOND_TURN_SOURCE\n',
                          encoding='utf-8')
        second = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                             self.payload(turn_id='turn-2'), config_sha=self.record['payload_sha256'])
        self.assertNotEqual(second['task_id'], first['task_id'],
                            'a finished task cannot hold the next turn')
        self.assertEqual(second['session_task_id'], second['task_id'])
        self.assertEqual(second['task_state'], 'active')
        self.assertIn('SECOND_TURN_SOURCE', second['additionalContext'])
        self.assertNotEqual(second['context_semantic_sha256'], first['context_semantic_sha256'])
        self.assertEqual(pb.reservation(self.root)['task_id'], second['task_id'])
        self.assertEqual(pb.task_state(self.root, first['task_id'])['status'], 'cancelled',
                         'the finished task keeps its own record and evidence')
        self.assertFalse(pb.task_state(self.root, second['task_id']).get('verified'))

    def test_an_active_session_task_is_still_the_same_task_across_its_turns(self):
        first = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                            config_sha=self.record['payload_sha256'])
        checkpoint = hl.callback(self.root, PROJECT, 'codex', 'PostToolUse',
                                 self.payload(turn_id='turn-2'), config_sha=self.record['payload_sha256'])
        self.assertEqual(checkpoint['task_id'], first['task_id'])
        self.assertNotEqual(checkpoint['turn_task_id'], first['turn_task_id'])
        again = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                            self.payload(turn_id='turn-3'), config_sha=self.record['payload_sha256'])
        self.assertEqual(again['task_id'], first['task_id'],
                         'one ongoing session holds one reservation and one frozen generation')

    def test_the_task_log_records_the_installation_but_never_the_context_body(self):
        response = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                               config_sha=self.record['payload_sha256'])
        logged = [item for item in hl.observed_events(self.root, 'codex')
                  if item.get('stage') == 'inject']
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0]['install_id'], self.record['install_id'])
        self.assertEqual(logged[0]['context_semantic_sha256'], response['context_semantic_sha256'])
        self.assertEqual(logged[0]['context_bytes'], response['context_bytes'])
        self.assertNotIn('additionalContext', logged[0])
        text = (self.root / hl.STATE_RELATIVE / 'codex' / 'events.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('def login(user):', text)
        self.assertLessEqual(len(text.encode('utf-8')), hl.MAX_STATE_BYTES)


class NativeWireBoundaries(Fixture):
    """What the installed hook command actually writes to its host is the host's own wire only.

    Every case runs the real command line the installed control config runs, in a real child
    process, because the supported response shape is a property of that process boundary: a host
    parses the whole stdout of the hook command as its response, so an unsupported field fails the
    hook rather than the callback. The Python API is asserted separately on the same engine, so a
    wire repair can never quietly cost an in-process caller the internal callback metadata.
    """

    def setUp(self):
        super().setUp()
        self.records = {'codex': self.install_default(), 'opencode': self.install(host='opencode')}

    def invoke(self, event, extra=None, host='codex', stage=None, config_sha=None):
        """One real hook invocation, exactly as the installed bridge command performs it."""
        argv = [sys.executable, str(SOURCE / 'host_lifecycle.py'), 'event', '--project', str(self.root),
                '--project-id', PROJECT, '--host', host, '--config-sha',
                config_sha if config_sha is not None else self.records[host]['payload_sha256']]
        if stage is not None:
            argv.extend(['--stage', stage])
        payload = {'hook_event_name': event, 'cwd': str(self.root), 'session_id': 'wire-session',
                   'turn_id': 'wire-turn'}
        if host == 'codex':
            payload['host_version'] = 'codex-cli 0.155.1'
        payload.update(extra or {})
        return subprocess.run(argv, input=json.dumps(payload), cwd=self.root, env=repo_map.git_environment(),
                              capture_output=True, text=True, timeout=60)

    def wire(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        document = json.loads(result.stdout)
        self.assertIsInstance(document, dict)
        return document

    def test_prompt_submit_writes_only_the_supported_additional_context(self):
        document = self.wire(self.invoke('UserPromptSubmit'))
        self.assertEqual(set(document), {'hookSpecificOutput'})
        hook = document['hookSpecificOutput']
        self.assertEqual(set(hook), {'hookEventName', 'additionalContext'})
        self.assertEqual(hook['hookEventName'], 'UserPromptSubmit')
        self.assertIn(self.records['codex']['marker'], hook['additionalContext'])
        self.assertIn('login returns the submitted user', hook['additionalContext'])
        self.assertNotIn('task_id', document)
        self.assertNotIn('additionalContext', document)

    def test_the_python_api_keeps_every_internal_callback_field_the_wire_drops(self):
        report = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit',
                             {'session_id': 'api-session', 'turn_id': 'api-turn', 'cwd': str(self.root)},
                             config_sha=self.records['codex']['payload_sha256'])
        for field in ('stage', 'native_event', 'host', 'project_id', 'task_id', 'session_task_id',
                      'turn_task_id', 'install_id', 'scope_sha256', 'verified', 'injected',
                      'context_generation', 'context_semantic_sha256', 'context_bytes',
                      'context_limit', 'omissions', 'task_state', 'additionalContext'):
            self.assertIn(field, report, field)
        self.assertEqual(set(hl.native_wire_output('codex', report)), {'hookSpecificOutput'})
        self.assertEqual(hl.wire_event('codex', report['stage']), 'UserPromptSubmit')

    def test_an_event_with_no_supported_decision_writes_an_empty_object(self):
        record = self.install(acceptance=False)
        cases = [('SessionStart', None, None),
                 ('PostToolUse', {'tool': 'apply_patch', 'args': {'changed_paths': [SOURCE_FILE]}}, None),
                 ('Stop', None, None), ('SessionEnd', None, None)]
        for event, extra, _ in cases:
            document = self.wire(self.invoke(event, extra, config_sha=record['payload_sha256']))
            self.assertEqual(document, {}, event + ' must not answer with internal metadata')
        stop = hl.callback(self.root, PROJECT, 'codex', 'Stop',
                           {'session_id': 'api-stop', 'turn_id': 'api-turn', 'cwd': str(self.root)},
                           config_sha=record['payload_sha256'])
        self.assertEqual(stop['stage'], 'verify')
        self.assertFalse(stop['attempted'], stop)
        self.assertFalse(stop['verified'])
        self.assertEqual(hl.native_wire_output('codex', stop), {})

    def test_a_guard_denial_writes_only_the_supported_decision(self):
        document = self.wire(self.invoke('PreToolUse', {'tool': 'apply_patch',
                                                        'args': {'command': patch_text(
                                                            ('add', 'out/undeclared.txt', 'no'))}}))
        self.assertEqual(set(document), {'hookSpecificOutput'})
        hook = document['hookSpecificOutput']
        self.assertEqual(set(hook), {'hookEventName', 'permissionDecision', 'permissionDecisionReason'})
        self.assertEqual(hook['hookEventName'], 'PreToolUse')
        self.assertEqual(hook['permissionDecision'], 'deny')
        self.assertIn('not a declared output', hook['permissionDecisionReason'])
        for duplicated in ('permissionDecision', 'permissionDecisionReason', 'allowed', 'stage'):
            self.assertNotIn(duplicated, document)

    def test_an_allowed_guard_writes_only_the_supported_allow_decision(self):
        document = self.wire(self.invoke('PreToolUse', {'tool': 'apply_patch',
                                                        'args': {'command': patch_text(
                                                            ('add', DECLARED, 'done'))}}))
        self.assertEqual(set(document), {'hookSpecificOutput'})
        hook = document['hookSpecificOutput']
        self.assertEqual(hook['hookEventName'], 'PreToolUse')
        self.assertEqual(hook['permissionDecision'], 'allow')
        self.assertEqual(set(hook) - {'hookEventName', 'permissionDecision', 'permissionDecisionReason'},
                         set())

    def test_the_opencode_plugin_bridge_keeps_its_plain_rich_response(self):
        result = self.invoke('experimental.chat.system.transform', stage='inject', host='opencode')
        document = self.wire(result)
        self.assertIn(self.records['opencode']['marker'], document['additionalContext'])
        for field in ('stage', 'native_event', 'host', 'task_id', 'session_task_id', 'turn_task_id',
                      'install_id', 'scope_sha256', 'injected', 'context_generation',
                      'context_semantic_sha256', 'context_bytes', 'context_limit', 'omissions',
                      'task_state', 'verified', 'additionalContext'):
            self.assertIn(field, document, field)
        self.assertIs(hl.native_wire_output('opencode', document), document)

    def test_a_refusal_blocks_with_exit_two_and_writes_no_response_document(self):
        result = self.invoke('UserPromptSubmit', config_sha='a' * 64)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '', 'a refusal is never a successful hook receipt')
        self.assertIn('copied or altered hook configuration', result.stderr)
        with self.assertRaises(ValueError):
            json.loads(result.stderr)
        self.assertLessEqual(len(result.stderr.encode('utf-8')), hl.MAX_HOOK_ERROR_BYTES)

    def test_a_host_error_is_bounded_to_the_reported_refusal_line(self):
        refusal = hl.hook_refusal('a refusal reason that repeats. ' * 400)
        self.assertLessEqual(len(refusal.encode('utf-8')), hl.MAX_HOOK_ERROR_BYTES)
        self.assertNotIn('\n', refusal)
        self.assertTrue(refusal.startswith('Crewloom lifecycle refusal: '))

    def test_the_event_log_keeps_the_install_and_turn_scope_the_wire_never_carries(self):
        self.wire(self.invoke('UserPromptSubmit'))
        logged = [item for item in hl.observed_events(self.root, 'codex')
                  if item.get('stage') == 'inject']
        self.assertEqual(len(logged), 1)
        for field in ('install_id', 'scope_sha256', 'task_id', 'session_task_id', 'turn_task_id',
                      'native_event', 'context_bytes', 'context_semantic_sha256'):
            self.assertIn(field, logged[0], field)
        self.assertEqual(logged[0]['install_id'], self.records['codex']['install_id'])
        self.assertNotIn('additionalContext', logged[0])
        report = hl.status(self.root, PROJECT, 'codex')
        self.assertIn('UserPromptSubmit', report['observed_events'])
        self.assertTrue(report['delivered'], report)


class LauncherBoundaries(Fixture):
    def test_the_codex_launcher_injects_only_validated_owned_hooks_and_rewrites_no_global(self):
        record = self.install_default()
        frozen = hl.launcher(self.root, PROJECT, 'codex', executable='/bin/true', model='gpt-6-sol')
        self.assertFalse(frozen['executed'])
        self.assertEqual(frozen['global_configuration_rewritten'], False)
        self.assertEqual(frozen['payload_sha256'], record['payload_sha256'])
        inline = ' '.join(frozen['inline_overrides'])
        for event in record['callback_caps']['stages']:
            self.assertIn('hooks.' + event + '=', inline)
        self.assertIn(record['bridge_command'].replace("'", '"')[:40], inline.replace('"', '"'))
        self.assertIn('--ignore-user-config', frozen['argv'])
        self.assertIn('features.code_mode_host=true', frozen['argv'])
        self.assertNotIn('--dangerously-bypass-hook-trust', frozen['argv'])
        self.assertNotIn('trust_level', ' '.join(frozen['argv']))

    def test_the_inline_hook_override_is_the_observed_native_toml_shape(self):
        # The exact shape the schema probe actually delivered on the supported binary. Wrapping a
        # hook in a second `{hooks=[...]}` is not a harmless extra nesting: TOML has no unclosed
        # inline table, so the host refuses to parse the override instead of running the hook.
        self.assertEqual(
            hl._inline_group([{'hooks': [{'type': 'command', 'command': 'safe',
                                           'timeout': 3, 'additionalContextLimit': 200}]}]),
            '[{hooks=[{type="command",command="safe",timeout=3,additionalContextLimit=200}]}]')
        record = self.install_default()
        frozen = hl.launcher(self.root, PROJECT, 'codex', executable='/bin/true')
        overrides = [item for item in frozen['argv'] if item.startswith('hooks.')]
        self.assertEqual(sorted(item.split('=', 1)[0] for item in overrides),
                         sorted('hooks.' + event for event in record['owned_entries']))
        for item in overrides:
            event, _, value = item[len('hooks.'):].partition('=')
            self.assertNotIn('},', value, 'a nested group cannot survive a TOML parse')
            if tomllib is None:
                continue
            self.assertEqual(tomllib.loads('hooks = ' + value)['hooks'],
                             [{'hooks': [dict(hook) for hook in group['hooks']]}
                              for group in record['owned_entries'][event]],
                             event)

    def test_the_inline_hook_override_keeps_every_owned_timeout_and_context_limit(self):
        # One event may own several hook entries, and the inline override replaces the whole owned
        # entry rather than merging with it, so every timeout and context limit has to survive.
        groups = [{'hooks': [{'type': 'command', 'command': 'one', 'timeout': 7},
                             {'type': 'command', 'command': 'two', 'timeout': 120,
                              'additionalContextLimit': 4096}]}]
        value = hl._inline_group(groups)
        self.assertIn('timeout=7', value)
        self.assertIn('timeout=120', value)
        self.assertIn('additionalContextLimit=4096', value)
        if tomllib is None:
            return
        parsed = tomllib.loads('hooks = ' + value)['hooks']
        self.assertEqual([hook['timeout'] for hook in parsed[0]['hooks']], [7, 120])
        self.assertNotIn('additionalContextLimit', parsed[0]['hooks'][0])
        self.assertEqual(parsed[0]['hooks'][1]['additionalContextLimit'], 4096)

    def test_a_configured_context_limit_reaches_the_inline_override_of_the_installed_record(self):
        record = self.install_default(context_limit=4096)
        self.assertEqual(record['additional_context_limit'], 4096)
        frozen = hl.launcher(self.root, PROJECT, 'codex', executable='/bin/true')
        inline = ' '.join(frozen['inline_overrides'])
        self.assertEqual(inline.count('additionalContextLimit=4096'),
                         len(record['callback_caps']['stages']))

    def test_hook_trust_bypass_is_refused_while_a_foreign_hook_source_exists(self):
        self.install_default()
        control = self.root / '.codex' / 'hooks.json'
        document = json.loads(control.read_text(encoding='utf-8'))
        document['hooks']['SessionStart'].append({'matcher': '*',
                                                  'hooks': [{'type': 'command',
                                                             'command': 'unvetted-hook'}]})
        control.write_text(json.dumps(document, indent=2), encoding='utf-8')
        with self.assertRaisesRegex(hl.LifecycleError, 'unvetted hook sources exist'):
            hl.launcher(self.root, PROJECT, 'codex', executable='/bin/true', trust_bypass=True)

    def test_a_vetted_project_with_no_foreign_source_may_bypass_trust_for_one_session(self):
        self.install_default()
        frozen = hl.launcher(self.root, PROJECT, 'codex', executable='/bin/true',
                             trust_bypass=True, one_shot_trust=True)
        self.assertIn('--dangerously-bypass-hook-trust', frozen['argv'])
        self.assertTrue(frozen['one_shot_project_trust'])
        self.assertEqual(frozen['unvetted_hook_sources'], [])

    def test_the_cli_refuses_a_wrong_project_id_without_writing_anything(self):
        result = subprocess.run(
            [sys.executable, str(SOURCE / 'host_lifecycle.py'), 'install', '--project',
             str(self.root), '--project-id', 'not-this-project', '--host', 'codex', '--role', ROLE,
             '--output', DECLARED], cwd=self.root, env=repo_map.git_environment(),
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertIn('rejected', result.stdout)
        self.assertIn('does not match the local binding', result.stdout)
        self.assertFalse((self.root / '.codex' / 'hooks.json').exists())
        self.assertFalse((self.root / hl.STATE_RELATIVE).exists())


class ExecutorBoundaries(Fixture):
    """Real executor evidence is the only path to verified, and it needs Docker."""

    def setUp(self):
        super().setUp()
        self.record = self.install_default()
        if os.environ.get('CREWLOOM_DOCKER_TESTS') != '1':
            self.skipTest('Set CREWLOOM_DOCKER_TESTS=1 to run the real Docker acceptance ledger')

    def test_a_failing_acceptance_is_known_bad_and_never_verifies(self):
        plan = json.loads((self.root / ACCEPTANCE_PLAN).read_text(encoding='utf-8'))
        plan['id'] = 'native-acceptance-bad'
        plan['steps'][0]['argv'] = ['python3', '-c', 'raise SystemExit(3)']
        plan['steps'][0]['inputs'] = ['src/login.py']
        plan['steps'][0]['outputs'] = [DECLARED]
        (self.root / ACCEPTANCE_PLAN).write_text(json.dumps(plan), encoding='utf-8')
        bad = hl.install(self.root, PROJECT, 'codex', ROLE, criteria_path=CRITERIA,
                         seeds=[SOURCE_FILE], sources=[SOURCE_FILE], declared_outputs=[DECLARED],
                         acceptance={'workflow': ACCEPTANCE_PLAN, 'step': 'acceptance',
                                     'image': w.DEFAULT_IMAGE})
        hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                    config_sha=bad['payload_sha256'])
        response = hl.callback(self.root, PROJECT, 'codex', 'Stop', self.payload(),
                               config_sha=bad['payload_sha256'])
        self.assertTrue(response['attempted'])
        self.assertFalse(response['verified'])
        self.assertFalse((self.root / DECLARED).is_file())
        report = hl.status(self.root, PROJECT, 'codex')
        self.assertNotEqual(report['lifecycle'], 'verified-executor')
        self.assertFalse(report['verified_executor'])

    def test_the_full_lifecycle_verifies_only_through_real_executor_evidence(self):
        prepared = hl.callback(self.root, PROJECT, 'codex', 'SessionStart',
                               {'session_id': 'session-1', 'cwd': str(self.root)},
                               config_sha=self.record['payload_sha256'])
        self.assertEqual(prepared['scope'], 'session')
        injected = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(),
                               config_sha=self.record['payload_sha256'])
        self.assertIn(self.record['marker'], injected['additionalContext'])
        response = hl.callback(self.root, PROJECT, 'codex', 'Stop', self.payload(),
                               config_sha=self.record['payload_sha256'])
        self.assertTrue(response['attempted'], response)
        self.assertTrue(response['verified'], response)
        self.assertEqual(response['executor'], 'docker')
        self.assertEqual(response['workflow'], 'native-acceptance')
        self.assertTrue((self.root / DECLARED).is_file())
        self.assertEqual(pb.task_state(self.root, response['task_id'])['status'], 'complete')
        report = hl.status(self.root, PROJECT, 'codex')
        self.assertEqual(report['lifecycle'], 'verified-executor')
        self.assertTrue(report['verified_executor'])
        self.assertEqual(sorted(report['observed_events']),
                         ['SessionStart', 'Stop', 'UserPromptSubmit'])


if __name__ == '__main__':
    unittest.main()
