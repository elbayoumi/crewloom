"""W03/N03: capability facts are labelled, never self-reported, and bound dispatch before side effects."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import crewloom
import execution_policy
import model_host as host
import repo_map
import workflow as w


class CapabilityProfile(unittest.TestCase):
    def profile(self, name='codex', model='gpt-6-sol', version='codex-cli 9.1.0', **kwargs):
        info = {'version': version} if version else None
        return host.capability_profile(name, model, probe_info=info, now='2026-10-06T10:00:00', **kwargs)

    def test_every_fact_has_a_basis_and_unknowns_stay_unknown(self):
        profile = self.profile(version=None)
        self.assertEqual(profile['host']['version']['basis'], 'unknown')
        self.assertIsNone(profile['host']['version']['value'])
        for name in ('remaining', 'reset_at'):
            self.assertEqual(profile['quota'][name]['basis'], 'unknown')
        for name in ('context_window_tokens', 'knowledge_cutoff'):
            self.assertEqual(profile['limits'][name]['basis'], 'unknown')
            self.assertIsNone(profile['limits'][name]['value'])
        self.assertEqual(profile['model']['reported']['basis'], 'unknown')

        def walk(node):
            if isinstance(node, dict):
                if 'basis' in node:
                    self.assertIn(node['basis'], host.FACT_BASES)
                    self.assertTrue(node['source'])
                for value in node.values():
                    walk(value)
        walk(profile)

    def test_requested_and_reported_model_stay_separate_and_conflicts_are_visible(self):
        reported = {'model_reported': 'something-else'}
        profile = host.capability_profile('codex', 'gpt-6-sol', reported=reported, now='2026-10-06T10:00:00')
        self.assertEqual(profile['model']['requested']['value'], 'gpt-6-sol')
        self.assertEqual(profile['model']['reported']['value'], 'something-else')
        self.assertEqual(len(host.profile_conflicts(profile)), 1)
        consistent = host.capability_profile('codex', 'gpt-6', reported={'model_reported': 'gpt-6-sol'},
                                             now='2026-10-06T10:00:00')
        self.assertEqual(host.profile_conflicts(consistent), [])
        self.assertEqual(host.profile_conflicts(self.profile()), [])

    def test_invalid_metadata_is_refused(self):
        for args in (('nothing',), ('codex', ''), ('codex', 'x' * 201), ('codex', 'a\0b')):
            with self.subTest(args=args), self.assertRaises(ValueError):
                host.capability_profile(*args)
        with self.assertRaises(ValueError):
            host.capability_profile('codex', 'm', launch_mode='telepathy')
        with self.assertRaises(ValueError):
            host._fact(1, 'self-reported', 'model')

    def test_managed_generation_is_tool_free_and_stronger_host_ability_cannot_widen_scope(self):
        profile = self.profile()
        self.assertTrue(all(profile['tools'][a]['value'] is False for a in host.ACTIONS))
        allowed = ('write_files', 'run_commands', 'browser')
        decisions = host.effective_execution(profile, allowed, allowed, allowed, requested=allowed)
        self.assertEqual(decisions['write_files']['decision'], 'controller')
        self.assertEqual(decisions['run_commands']['decision'], 'controller')
        self.assertEqual(decisions['browser']['decision'], 'refused')
        self.assertIn('unavailable', ' '.join(decisions['browser']['reasons']))

    def test_effective_execution_is_the_intersection_of_all_four_layers(self):
        profile = self.profile()
        full = ('write_files',)
        for missing, layers in (('project policy', ((), full, full)), ('task declaration', (full, (), full)),
                                ('user authorization', (full, full, ()))):
            with self.subTest(missing=missing):
                result = host.effective_execution(profile, *layers, requested=('write_files',))['write_files']
                self.assertEqual(result['decision'], 'refused')
                self.assertIn('not permitted by ' + missing, result['reasons'])
        self.assertEqual(host.effective_execution(profile, full, full, full, requested=('write_files',))
                         ['write_files']['decision'], 'controller')
        self.assertEqual(host.effective_execution(profile, full, full, full, requested=('format_disk',))
                         ['format_disk']['decision'], 'refused')

    def test_unknown_native_tools_are_unavailable_for_dispatch(self):
        profile = host.capability_profile('claude', 'm', launch_mode='native-interactive', now='2026-10-06T10:00:00')
        self.assertEqual(profile['tools']['browser']['basis'], 'unknown')
        everything = host.ACTIONS
        decisions = host.effective_execution(profile, everything, everything, everything, requested=everything)
        for action in ('read_files', 'network', 'browser', 'image_input', 'delegate_agents'):
            self.assertEqual(decisions[action]['decision'], 'refused', action)
            self.assertIn('unknown', ' '.join(decisions[action]['reasons']))

    def test_prompt_limits_refuse_before_dispatch_and_unknown_limits_need_a_configured_bound(self):
        profile = self.profile()
        self.assertEqual(host.check_prompt_fits(profile, 1000), host.MAX_TEXT)
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            host.check_prompt_fits(profile, host.MAX_TEXT + 1)
        unknown = copy.deepcopy(profile)
        unknown['limits']['input_bytes'] = host._fact(None, 'unknown', 'removed', None)
        with self.assertRaisesRegex(ValueError, 'unknown'):
            host.check_prompt_fits(unknown, 10)
        self.assertEqual(host.check_prompt_fits(unknown, 10, configured_bound=100), 100)
        with self.assertRaises(ValueError):
            host.check_prompt_fits(unknown, 101, configured_bound=100)

    def test_profile_goes_stale_on_host_model_version_mode_or_age(self):
        profile = self.profile()
        epoch = 1791280800  # 2026-10-06T10:00:00Z
        same = dict(host='codex', model='gpt-6-sol', probe_info={'version': 'codex-cli 9.1.0'})
        self.assertTrue(host.profile_is_current(profile, now_epoch=epoch + 60, **same))
        self.assertFalse(host.profile_is_current(profile, now_epoch=epoch + host.PROFILE_TTL_SECONDS + 1, **same))
        for change in ({'host': 'claude'}, {'model': 'other'}, {'probe_info': {'version': 'codex-cli 9.2.0'}},
                       {'launch_mode': 'native-interactive'}):
            with self.subTest(change=change):
                self.assertFalse(host.profile_is_current(profile, now_epoch=epoch + 60, **dict(same, **change)))
        self.assertFalse(host.profile_is_current(dict(profile, observed_at='garbage'), now_epoch=epoch, **same))

    def test_receiver_recomputes_its_own_profile_instead_of_copying_the_senders(self):
        sender = self.profile('claude', 'sender-model', 'claude 2.0')
        receiver = self.profile('opencode', 'receiver-model', 'opencode 1.4')
        self.assertNotEqual(sender['fingerprint'], receiver['fingerprint'])
        self.assertEqual(receiver['host']['name'], 'opencode')
        self.assertEqual(receiver['host']['version']['value'], 'opencode 1.4')
        self.assertEqual(receiver['structured_output']['value'], 'prompt-instructed')
        self.assertFalse(host.profile_is_current(sender, 'opencode', 'receiver-model',
                                                 probe_info={'version': 'opencode 1.4'}, now_epoch=1791280801))

    def test_failures_are_classified_without_confusing_rate_limits_with_exhausted_quota(self):
        cases = [
            (dict(error_code='insufficient_quota', http_status=429), 'quota_exhausted', 'confirmed'),
            (dict(http_status=429, retry_after_seconds=30), 'rate_limited', 'confirmed'),
            (dict(http_status=401), 'authentication', 'confirmed'),
            (dict(timed_out=True), 'timeout', 'confirmed'),
            (dict(text='Claude usage limit reached'), 'quota_exhausted', 'probable'),
            (dict(http_status=500), 'unknown', 'unknown'),
            (dict(), 'unknown', 'unknown'),
        ]
        for kwargs, kind, confidence in cases:
            with self.subTest(kwargs=kwargs):
                result = host.classify_failure(**kwargs)
                self.assertEqual((result['kind'], result['confidence']), (kind, confidence))
        limited = host.classify_failure(http_status=429, retry_after_seconds=30)
        self.assertIs(limited['quota_exhausted'], False)
        self.assertEqual(host.classify_failure(timed_out=True)['side_effects'], 'uncertain')
        self.assertIsNone(host.classify_failure(http_status=429)['quota_exhausted'])

    def test_completion_claims_need_current_evidence_of_their_own_kind(self):
        evidence = {'artifacts': {'src/a.py': 'abc'}, 'commands': [{'argv': ['python3', '-m', 'unittest'], 'exit_code': 0}],
                    'acceptance': {'configured': True, 'passed': True}}
        good = [{'kind': 'edit', 'subject': 'src/a.py'}, {'kind': 'executed', 'subject': 'python3 -m unittest'},
                {'kind': 'accepted', 'subject': 'login-fix'}]
        self.assertTrue(host.verify_claims(good, evidence)['all_supported'])
        bad = [{'kind': 'edit', 'subject': 'src/other.py'}, {'kind': 'executed', 'subject': 'pytest'},
               {'kind': 'accepted', 'subject': 'x'}, {'kind': 'tested', 'subject': 'y'}]
        weak = dict(evidence, acceptance={'configured': False, 'passed': True},
                    commands=[{'argv': ['pytest'], 'exit_code': 1}])
        result = host.verify_claims(bad, weak)
        self.assertEqual([item['supported'] for item in result['results']], [False] * 4)
        self.assertFalse(result['all_supported'])


class DispatchPreflight(unittest.TestCase):
    """The workflow refuses an unsupported model step before any ledger entry or provider call."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        _, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        self.assertEqual(errors, [])
        (self.root / 'a.py').write_text('def a():\n    return 1\n', encoding='utf-8')
        plan = {'schema_version': 1, 'id': 'preflight', 'steps': [
            {'id': 'generate', 'role': 'context-guardian', 'kind': 'model', 'host': 'openai', 'model': 'gpt-test',
             'summary': 'Generate', 'inputs': ['a.py'], 'outputs': ['generated.py']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        self.parsed, self.fingerprint = w.read_plan(self.root, 'workflow.json')

    def run_plan(self, generate):
        def execute(root, step, image, timeout):
            return {'exit_code': 0, 'output': '', 'image_id': image, 'duration_ms': 1}
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(execution_policy, 'execute', side_effect=execute), \
                patch.object(host, 'generate', side_effect=generate):
            return w.run(self.root, self.parsed, self.fingerprint, 'image')

    def test_a_prompt_over_the_profile_bound_is_refused_before_provider_or_ledger(self):
        calls = []
        original = host.capability_profile

        def tight(*args, **kwargs):
            profile = original(*args, **kwargs)
            profile['limits']['input_bytes'] = host._fact(64, 'documented', 'test bound')
            return profile
        with patch.object(host, 'capability_profile', side_effect=tight):
            result = self.run_plan(lambda *a, **k: calls.append(a) or ({'generated.py': 'x=1\n'}, {}))
        self.assertEqual(calls, [], 'the provider is never called')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('exceeds the 64 byte bound', json.dumps(result))
        ledger_file = self.root / '.crewloom/attempts.json'
        attempts = json.loads(ledger_file.read_text())['attempts'] if ledger_file.is_file() else []
        self.assertEqual([a for a in attempts if a.get('kind') == 'model'], [])
        self.assertFalse((self.root / 'generated.py').exists())

    def test_a_supported_step_records_the_capability_fingerprint_it_ran_under(self):
        result = self.run_plan(lambda host_name, prompt, outputs, *a, **k: ({outputs[0]: 'x = 1\n'}, {'host': host_name}))
        self.assertEqual(result['status'], 'complete')
        state = json.loads(next((self.root / '.crewloom').rglob('state.json')).read_text())
        record = state['steps']['generate']['capability_profile']
        self.assertEqual(record['fingerprint'], host.capability_profile('openai', 'gpt-test')['fingerprint'])
        self.assertEqual(record['tools'], 'none (managed text generation)')


class CapabilityCommand(unittest.TestCase):
    def run_cli(self, *argv, cwd):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        return subprocess.run([sys.executable, str(Path(__file__).resolve().parent / 'crewloom.py'),
                               'capabilities', *argv], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)

    def test_command_prints_and_stores_a_profile_only_inside_the_selected_project(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as elsewhere:
            result = self.run_cli('--host', 'openai', '--model', 'm-1', '--project', folder, cwd=elsewhere)
            self.assertEqual(result.returncode, 0, result.stderr)
            printed = json.loads(result.stdout)
            stored = Path(folder) / '.crewloom/capabilities/openai.json'
            self.assertEqual(json.loads(stored.read_text()), {k: v for k, v in printed.items() if k != 'stored'})
            self.assertEqual(printed['host']['version']['basis'], 'unknown', 'an API provider has no binary version')
            self.assertEqual(list(Path(elsewhere).iterdir()), [], 'the working directory is not a project')

    def test_invalid_host_or_mode_exits_nonzero_without_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = self.run_cli('--host', 'telepathy', '--project', folder, cwd=folder)
            self.assertEqual(bad.returncode, 2)
            self.assertFalse((Path(folder) / '.crewloom').exists())


if __name__ == '__main__':
    unittest.main()
