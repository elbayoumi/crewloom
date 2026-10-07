"""N02: durable, validated continuation between agents without losing work or weakening scope."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import continuation as cont
import crewloom
import execution_policy
import model_host
import project_binding as pb
import repo_map
import workflow as w

ROLE = 'context-guardian'
PLAN_ID = 'handoff-flow'
RECEIVER = {'id': 'agent-b', 'host': 'codex', 'model': 'gpt-6-sol'}


def git(root, *argv):
    return subprocess.run(['git', '-C', str(root), '-c', 'user.name=F', '-c', 'user.email=f@example.invalid', *argv],
                          env=repo_map.git_environment(), check=True, capture_output=True, timeout=30).stdout


class ContinuationBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-continuation-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'app'
        self.root.mkdir()
        git(self.root, 'init', '-q')
        _, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'input.txt').write_text('input', encoding='utf-8')
        (self.root / 'crewloom.project.json').write_text(json.dumps(pb.default_config('sample-project')), encoding='utf-8')
        pb.bootstrap(self.root, project_id='sample-project')
        git(self.root, 'add', '--', '.')
        git(self.root, 'commit', '-qm', 'base')
        plan = {'schema_version': 1, 'id': PLAN_ID, 'steps': [
            {'id': 'build', 'role': ROLE, 'summary': 'Build', 'argv': ['python3', 'build.py'],
             'inputs': ['input.txt'], 'outputs': ['output.txt']},
            {'id': 'verify', 'role': ROLE, 'summary': 'Verify', 'argv': ['python3', 'verify.py'],
             'inputs': ['output.txt'], 'outputs': ['verified.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        self.parsed, self.fingerprint = w.read_plan(self.root, 'workflow.json')

    def run_flow(self, interrupt_at=None, fail_at=None, plan_file='workflow.json'):
        def execute(root, step, image, timeout):
            if step['id'] == interrupt_at:
                raise KeyboardInterrupt('host quota exhausted mid-step')
            if step['id'] == fail_at:
                return {'exit_code': 1, 'output': 'acceptance failed', 'image_id': image, 'duration_ms': 1}
            for name in step['outputs']:
                (root / name).write_text('produced by ' + step['id'], encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image, 'duration_ms': 1}
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(execution_policy, 'execute', side_effect=execute):
            return w.run(self.root, self.parsed, self.fingerprint, 'image', plan_file=plan_file)

    def interrupted_mid_task(self, plan_file='workflow.json'):
        with self.assertRaises(KeyboardInterrupt):
            self.run_flow(interrupt_at='verify', plan_file=plan_file)
        return json.loads((cont.folder(self.root, PLAN_ID) / 'latest.json').read_text())

    def latest_path(self):
        return str(cont.folder(self.root, PLAN_ID) / 'latest.json')

    def attempts_bytes(self):
        return (self.root / '.crewloom/attempts.json').read_bytes()

    def model_plan(self):
        value = {'schema_version': 1, 'id': PLAN_ID, 'steps': [{
            'id': 'build', 'kind': 'model', 'host': 'anthropic', 'model': 'explicit-original',
            'role': ROLE, 'summary': 'Build', 'inputs': ['input.txt'], 'outputs': ['output.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(value))
        self.parsed, self.fingerprint = w.read_plan(self.root, 'workflow.json')
        return (self.root / 'workflow.json').read_bytes()

    def test_confirmed_quota_resumes_on_fenced_receiver_without_plan_or_budget_reset(self):
        original = self.model_plan()
        failure = model_host.GenerationFailure('Quota rejected', model_host.classify_failure(error_code='insufficient_quota'))
        with patch.object(model_host, 'generate', side_effect=[failure, ({'output.txt': 'receiver output'}, {'usage': {}})]) as generate:
            result = cont.resume(self.root, 'workflow.json', [{'id': 'receiver', 'host': 'openai', 'model': 'explicit-next'}], 1, 2)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([call.args[0] for call in generate.call_args_list], ['anthropic', 'openai'])
        self.assertEqual(generate.call_args_list[1].args[4], 'explicit-next')
        self.assertEqual((self.root / 'workflow.json').read_bytes(), original)
        self.assertEqual(len(cont._ledger(self.root)['attempts']), 2)
        self.assertEqual(json.loads((cont.folder(self.root, PLAN_ID) / 'fallback.json').read_text())['switches'], 1)

    def test_probable_quota_rate_limit_and_timeout_never_switch(self):
        self.model_plan()
        for signal in (model_host.classify_failure(text='usage limit reached'),
                       model_host.classify_failure(http_status=429, retry_after_seconds=30),
                       model_host.classify_failure(timed_out=True)):
            with self.subTest(signal=signal):
                # A distinct workflow keeps failed-attempt history honest for each independent case.
                value = dict(self.parsed, id='quota-' + signal['kind'].replace('_', '-') + '-' + signal['confidence'])
                value['steps'] = [dict(self.parsed['steps'][0], model='fixture-' + signal['kind'])]
                (self.root / 'workflow.json').write_text(json.dumps(value))
                with patch.object(model_host, 'generate', side_effect=model_host.GenerationFailure('Rejected', signal)) as generate:
                    result = cont.resume(self.root, 'workflow.json', [{'id': 'receiver', 'host': 'openai', 'model': 'explicit-next'}], 1, 2)
                self.assertEqual(result['status'], 'failed'); self.assertEqual(generate.call_count, 1)
                self.assertEqual(result['fallback']['switches'], 0)

    def test_fallback_budget_prevents_receiver_dispatch_and_remains_charged(self):
        self.model_plan()
        failure = model_host.GenerationFailure('Quota rejected', model_host.classify_failure(error_code='insufficient_quota'))
        with patch.object(model_host, 'generate', side_effect=failure) as generate:
            result = cont.resume(self.root, 'workflow.json', [{'id': 'receiver', 'host': 'openai', 'model': 'explicit-next'}], 1, 1)
        self.assertEqual(result['status'], 'failed'); self.assertEqual(generate.call_count, 1)
        self.assertIn('budget', result['blocker'].lower())
        self.assertEqual(len(cont._ledger(self.root)['attempts']), 1)

    def test_fallback_refuses_invalid_limits_and_native_optin_before_writes(self):
        self.model_plan()
        before = set(self.root.rglob('*'))
        for receivers, switches, requests in [([{'id': 'receiver', 'host': 'claude'}], 1, 2),
                                             ([{'id': 'receiver', 'host': 'openai'}], 1, 2),
                                             ([{'id': 'receiver', 'host': 'openai', 'model': 'explicit'}], 0, 2)]:
            with self.assertRaises(ValueError): cont.resume(self.root, 'workflow.json', receivers, switches, requests)
        self.assertEqual(set(self.root.rglob('*')), before)

    def test_restart_cannot_replay_a_timed_out_rpc(self):
        self.model_plan()
        receivers = [{'id': 'receiver', 'host': 'openai', 'model': 'explicit-next'}]
        with patch.object(model_host, 'generate', side_effect=model_host.GenerationFailure('timeout', model_host.classify_failure(timed_out=True))):
            cont.resume(self.root, 'workflow.json', receivers, 1, 2)
        self.assertTrue(cont._ledger(self.root)['attempts'][0]['uncertain_side_effects'])
        with patch.object(model_host, 'generate') as generate, self.assertRaisesRegex(ValueError, 'Uncertain prior dispatch'):
            cont.resume(self.root, 'workflow.json', receivers, 1, 2)
        generate.assert_not_called()

    def test_fallback_refuses_copied_or_negative_counter_records_without_dispatch(self):
        self.model_plan()
        receiver = [{'id': 'receiver', 'host': 'openai', 'model': 'explicit-next'}]
        with patch.object(model_host, 'generate', return_value=({'output.txt': 'fixture'}, {'usage': {}})):
            cont.resume(self.root, 'workflow.json', receiver, 1, 2)
        file = cont.folder(self.root, PLAN_ID) / 'fallback.json'
        clean = json.loads(file.read_text())
        for field, value in [('switches', -1), ('identity', {'project_id': 'foreign'})]:
            file.write_text(json.dumps(dict(clean, **{field: value})))
            with patch.object(model_host, 'generate') as generate, self.assertRaisesRegex(ValueError, 'foreign fallback'):
                cont.resume(self.root, 'workflow.json', receiver, 1, 2)
            generate.assert_not_called()

    # exhaustion before generation, and the controller dying before anyone can summarise
    def test_a_checkpoint_exists_before_dispatch_even_if_the_host_dies_immediately(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_flow(interrupt_at='build')
        packet = json.loads(Path(self.latest_path()).read_text())
        self.assertEqual((packet['boundary'], packet['step']), ('dispatched', 'build'))
        self.assertEqual(packet['identity']['project_id'], 'sample-project')
        self.assertEqual(len(packet['in_flight']), 1)
        self.assertIn('reconcile', packet['next_safe_action'])
        summary = (cont.folder(self.root, PLAN_ID) / 'HANDOFF.md').read_text()
        self.assertLess(len(summary.split()), 400)
        self.assertEqual(packet['packet_sha256'], cont.sha({k: v for k, v in packet.items() if k != 'packet_sha256'}))
        if os.name == 'posix':
            self.assertEqual(Path(self.latest_path()).stat().st_mode & 0o077, 0)

    def test_mid_task_checkpoint_preserves_completed_work_attempts_and_dirty_edits(self):
        (self.root / 'notes.txt').write_text('uncommitted user work', encoding='utf-8')
        packet = self.interrupted_mid_task()
        self.assertEqual(list(packet['completed_steps']), ['build'])
        self.assertEqual(packet['completed_steps']['build']['outputs']['output.txt'],
                         hashlib.sha256(b'produced by build').hexdigest())
        self.assertEqual([p['step'] for p in packet['pending_steps']], ['verify'])
        self.assertEqual([a['status'] for a in packet['attempts']], ['succeeded', 'running'])
        dirty = packet['source']['dirty']['entries']
        self.assertEqual(dirty['notes.txt']['sha256'], hashlib.sha256(b'uncommitted user work').hexdigest())
        self.assertNotIn('.crewloom/attempts.json', dirty)

    def test_in_flight_work_must_be_reconciled_and_is_never_replayed_or_recounted(self):
        packet = self.interrupted_mid_task()
        before = json.loads(self.attempts_bytes())
        result = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertTrue(result['accepted'], result['reasons'])
        self.assertTrue(any('reconcile' in action for action in result['pending_actions']))
        calls = []
        with patch.object(execution_policy, 'execute', side_effect=lambda *a, **k: calls.append(a)):
            changed = cont.reconcile(self.root, PLAN_ID)
        self.assertEqual(calls, [], 'reconciling never re-executes the step')
        self.assertEqual([c['step'] for c in changed], ['verify'])
        after = json.loads(self.attempts_bytes())
        self.assertEqual(len(after['attempts']), len(before['attempts']), 'no new allowance and no lost attempt')
        failed = [a for a in after['attempts'] if a['step'] == 'verify'][0]
        self.assertEqual((failed['status'], failed['uncertain_side_effects']), ('failed', True))
        self.assertEqual(cont.reconcile(self.root, PLAN_ID), [])

    def test_accept_does_not_touch_ledger_work_tree_index_or_budgets(self):
        (self.root / 'notes.txt').write_text('uncommitted user work', encoding='utf-8')
        self.interrupted_mid_task()
        cont.reconcile(self.root, PLAN_ID)
        snapshot = (self.attempts_bytes(), git(self.root, 'status', '--porcelain'), git(self.root, 'rev-parse', 'HEAD'),
                    (self.root / 'notes.txt').read_bytes(), git(self.root, 'stash', 'list'))
        result = cont.accept(self.root, self.latest_path(), RECEIVER)
        self.assertEqual(result['owner']['epoch'], 1)
        after = (self.attempts_bytes(), git(self.root, 'status', '--porcelain'), git(self.root, 'rev-parse', 'HEAD'),
                 (self.root / 'notes.txt').read_bytes(), git(self.root, 'stash', 'list'))
        self.assertEqual(snapshot, after)

    def test_receiver_profile_is_recomputed_for_the_receiver(self):
        self.interrupted_mid_task()
        result = cont.validate(self.root, self.latest_path(), dict(RECEIVER, host='opencode', model='free-model'))
        profile = result['receiver_profile']
        self.assertEqual((profile['host']['name'], profile['model']['requested']['value']), ('opencode', 'free-model'))
        self.assertEqual(profile['structured_output']['value'], 'prompt-instructed')

    # no receiving host
    def test_without_an_eligible_receiver_state_stays_resumable_and_the_blocker_is_named(self):
        self.interrupted_mid_task()
        for receiver in (None, {}, {'id': 'x', 'host': 'telepathy'}, {'host': 'codex'}):
            with self.subTest(receiver=receiver):
                result = cont.validate(self.root, self.latest_path(), receiver)
                self.assertFalse(result['accepted'])
                self.assertIn('receiver must name an id and a supported host', result['reasons'])
        self.assertIsNone(cont.read_owner(self.root, PLAN_ID))
        self.assertTrue(Path(self.latest_path()).is_file())

    # changed source / policy
    def test_changed_outputs_are_scoped_stale_while_valid_work_is_preserved(self):
        self.interrupted_mid_task()
        (self.root / 'output.txt').write_text('edited by a human after the checkpoint', encoding='utf-8')
        result = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertEqual(result['stale_steps'], ['build'])
        self.assertIn('output.txt', result['source_drift'])
        clean = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertEqual(clean['preserved_steps'], [])  # still edited: nothing is silently trusted

    def test_policy_drift_and_plan_drift_are_refused(self):
        self.interrupted_mid_task()
        config = json.loads((self.root / 'crewloom.project.json').read_text())
        config['policy']['mode'] = 'enforced'
        (self.root / 'crewloom.project.json').write_text(json.dumps(config), encoding='utf-8')
        self.assertIn('project policy changed since the checkpoint',
                      cont.validate(self.root, self.latest_path(), RECEIVER)['reasons'])
        plan = json.loads((self.root / 'workflow.json').read_text())
        plan['steps'][1]['summary'] = 'Verify differently'
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        reasons = cont.validate(self.root, self.latest_path(), RECEIVER, 'workflow.json')['reasons']
        self.assertIn('workflow plan changed since the checkpoint', reasons)

    # stale / copied / tampered
    def test_stale_copied_tampered_and_foreign_packets_are_refused(self):
        self.interrupted_mid_task()
        first = Path(self.latest_path()).read_text()
        old = self.base / 'old-packet.json'
        old.write_text(first)
        cont.reconcile(self.root, PLAN_ID)
        self.run_flow()  # completes the workflow: a newer checkpoint supersedes the copied one
        self.assertIn('stale or copied packet: it is not the latest checkpoint of this workflow',
                      cont.validate(self.root, str(old), RECEIVER)['reasons'])
        tampered = json.loads(Path(self.latest_path()).read_text())
        tampered['next_safe_action'] = 'delete everything'
        edited = self.base / 'edited.json'
        edited.write_text(json.dumps(tampered))
        self.assertIn('packet hash mismatch: corrupt or edited', cont.validate(self.root, str(edited), RECEIVER)['reasons'])
        other = self.base / 'other'
        other.mkdir()
        git(other, 'init', '-q')
        pb.bootstrap(other, project_id='other-project')
        packet_copy = self.base / 'copy.json'
        shutil.copyfile(self.latest_path(), packet_copy)
        reasons = cont.validate(other, str(packet_copy), RECEIVER)['reasons']
        self.assertTrue(any('different root' in r or 'identity' in r for r in reasons), reasons)

    def forged(self, **identity_changes):
        """A well-formed, correctly hashed packet whose identity differs from the receiving binding."""
        packet = json.loads(Path(self.latest_path()).read_text())
        packet['identity'].update(identity_changes)
        packet.pop('packet_sha256')
        packet['packet_sha256'] = cont.sha(packet)
        path = self.base / ('forged-%d.json' % len(list(self.base.glob('forged-*.json'))))
        path.write_text(json.dumps(packet))
        return str(path)

    def test_each_identity_field_is_checked_on_its_own(self):
        self.interrupted_mid_task()
        cases = [({'project_root': str(self.base / 'elsewhere')}, 'different root'),
                 ({'project_id': 'another-project'}, 'identity does not match'),
                 ({'checkout_id': '0' * 32}, 'identity does not match')]
        for change, expected in cases:
            with self.subTest(change=change):
                reasons = cont.validate(self.root, self.forged(**change), RECEIVER)['reasons']
                self.assertTrue(any(expected in reason for reason in reasons), reasons)
        self.assertTrue(cont.validate(self.root, self.forged(), RECEIVER)['accepted'], 'an unchanged identity is accepted')

    def test_a_moved_checkout_needs_an_explicit_rebind_not_a_copied_binding(self):
        self.interrupted_mid_task()
        moved = self.base / 'moved'
        shutil.copytree(self.root, moved, symlinks=True)
        reasons = cont.validate(moved, str(moved / '.crewloom/handoffs' / PLAN_ID / 'latest.json'), RECEIVER)['reasons']
        self.assertTrue(any('not bound here' in r for r in reasons), reasons)

    # ownership
    def test_one_writable_owner_never_stolen_and_a_second_handoff_extends_the_lineage(self):
        self.interrupted_mid_task()
        cont.reconcile(self.root, PLAN_ID)
        first = cont.accept(self.root, self.latest_path(), RECEIVER)
        self.assertEqual(first['owner']['state'], 'active')
        refused = cont.validate(self.root, self.latest_path(), dict(RECEIVER, id='agent-c'))
        self.assertTrue(any('live owner agent-b' in r for r in refused['reasons']))
        with self.assertRaisesRegex(ValueError, 'Continuation refused'):
            cont.accept(self.root, self.latest_path(), dict(RECEIVER, id='agent-c'))
        classification = model_host.classify_failure(error_code='insufficient_quota')
        cont.interrupt(self.root, PLAN_ID, classification, 'second quota stop')
        owner = cont.read_owner(self.root, PLAN_ID)
        self.assertEqual((owner['state'], owner['failure']['kind']), ('interrupted', 'quota_exhausted'))
        second = cont.accept(self.root, self.latest_path(), dict(RECEIVER, id='agent-c', host='opencode'))
        self.assertEqual(second['owner']['epoch'], 2)
        self.assertEqual([item['owner'] for item in second['owner']['lineage']], ['agent-b'])

    def test_rate_limit_is_recorded_as_not_exhausted_quota(self):
        self.interrupted_mid_task()
        cont.interrupt(self.root, PLAN_ID, model_host.classify_failure(http_status=429, retry_after_seconds=30))
        owner = cont.read_owner(self.root, PLAN_ID)
        self.assertEqual(owner['failure']['kind'], 'rate_limited')
        self.assertIs(owner['failure']['quota_exhausted'], False)

    def test_another_workflow_or_context_task_holding_the_project_blocks_the_receiver(self):
        self.interrupted_mid_task()
        binding = pb.load_binding(self.root)
        pb.write_json(self.root, pb.RESERVATION_RELATIVE, {
            'schema_version': pb.SCHEMA_VERSION, 'project_root': str(self.root), 'project_id': binding['project_id'],
            'checkout_id': binding['checkout_id'], 'task_id': 'different-task', 'owner': 'someone-else',
            'reserved_at': '2026-10-06T00:00:00'})
        reasons = cont.validate(self.root, self.latest_path(), RECEIVER)['reasons']
        self.assertTrue(any('another context task holds the project' in r for r in reasons), reasons)

    # a checkpoint failure must never break the run
    # Semantic change (W04): the pre-dispatch checkpoint is mandatory recovery state, not telemetry. The
    # earlier test required the run to complete while every checkpoint failed; that is exactly the
    # fail-open behavior PR8 review reproduced, so it is replaced by the contracts below.
    def test_a_failed_required_checkpoint_prevents_dispatch_and_output_mutation(self):
        dispatched = []

        def execute(root, step, image, timeout):
            dispatched.append(step['id'])
            return {'exit_code': 0, 'output': '', 'image_id': image, 'duration_ms': 1}
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(execution_policy, 'execute', side_effect=execute), \
                patch.object(cont, 'write_checkpoint', side_effect=OSError('disk full')):
            result = w.run(self.root, self.parsed, self.fingerprint, 'image', plan_file='workflow.json')
        self.assertEqual((result['status'], dispatched), ('failed', []))
        self.assertIn('disk full', result['blocker'])
        self.assertFalse((self.root / 'output.txt').exists())
        self.assertFalse((cont.folder(self.root, PLAN_ID) / 'latest.json').exists())
        attempts = json.loads(self.attempts_bytes())['attempts']
        self.assertEqual([(a['status'], a.get('dispatched')) for a in attempts], [('failed', False)])
        self.assertIn('disk full', (cont.folder(self.root, PLAN_ID) / 'checkpoint-error.txt').read_text())

    def test_optional_boundary_failures_are_visible_but_do_not_abort_safe_work(self):
        real = cont.write_checkpoint

        def selective(root, plan, state, ledger, boundary, *args, **kwargs):
            if boundary != 'dispatched':
                raise OSError('telemetry disk full')
            return real(root, plan, state, ledger, boundary, *args, **kwargs)
        with patch.object(cont, 'write_checkpoint', side_effect=selective):
            result = self.run_flow()
        self.assertEqual(result['status'], 'complete')
        self.assertIn('telemetry disk full', (cont.folder(self.root, PLAN_ID) / 'checkpoint-error.txt').read_text())

    def test_failure_after_effects_never_replays_and_resume_keeps_verified_work(self):
        real = cont.write_checkpoint

        def after_first(root, plan, state, ledger, boundary, step_id=None, *args, **kwargs):
            if boundary == 'dispatched' and step_id == 'verify':
                raise OSError('disk full before second dispatch')
            return real(root, plan, state, ledger, boundary, step_id, *args, **kwargs)
        calls = []

        def execute(root, step, image, timeout):
            calls.append(step['id'])
            for name in step['outputs']:
                (root / name).write_text('produced by ' + step['id'], encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image, 'duration_ms': 1}
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(execution_policy, 'execute', side_effect=execute):
            with patch.object(cont, 'write_checkpoint', side_effect=after_first):
                first = w.run(self.root, self.parsed, self.fingerprint, 'image', plan_file='workflow.json')
            self.assertEqual((first['status'], calls), ('failed', ['build']))
            built = (self.root / 'output.txt').read_bytes()
            second = w.run(self.root, self.parsed, self.fingerprint, 'image', plan_file='workflow.json')
        self.assertEqual((second['status'], calls), ('complete', ['build', 'verify']))  # build was not replayed
        self.assertEqual((self.root / 'output.txt').read_bytes(), built)

    def test_a_partial_checkpoint_is_never_mistaken_for_a_committed_recovery_point(self):
        self.interrupted_mid_task()
        folder = cont.folder(self.root, PLAN_ID)
        committed = cont.committed_latest(self.root, PLAN_ID)
        self.assertIsNotNone(committed)
        # Control: a crash after the sequence record but before the commit rename keeps the old latest intact.
        real = cont._private_write

        def crash_on_latest(path, text):
            if Path(path).name == 'latest.json':
                raise OSError('killed before the commit rename')
            return real(path, text)
        plan, fingerprint = w.read_plan(self.root, 'workflow.json')
        state = w.state_for(self.root, plan, fingerprint)[1]
        with patch.object(cont, '_private_write', side_effect=crash_on_latest):
            with self.assertRaises(OSError):
                cont.write_checkpoint(self.root, plan, state, cont._ledger(self.root), 'manual')
        self.assertEqual(cont.committed_latest(self.root, PLAN_ID)['packet_sha256'], committed['packet_sha256'])
        # Negative: a latest.json whose sequence record is missing or different is not committed.
        record = folder / cont.sequence_name(committed['sequence'], committed['boundary'])
        original = record.read_text()
        record.write_text(original.replace('"step"', '"stepx"', 1))
        self.assertIsNone(cont.committed_latest(self.root, PLAN_ID))
        refused = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertTrue(any('not backed by its sequence record' in r for r in refused['reasons']))
        record.write_text(original)
        self.assertTrue(cont.validate(self.root, self.latest_path(), RECEIVER)['accepted'])

    def test_completed_workflows_checkpoint_history_is_chained_and_ordered(self):
        self.run_flow()
        files = sorted(p.name for p in cont.folder(self.root, PLAN_ID).glob('0*.json'))
        self.assertGreaterEqual(len(files), 5)
        packets = [json.loads((cont.folder(self.root, PLAN_ID) / name).read_text()) for name in files]
        for index, packet in enumerate(packets):
            self.assertEqual(packet['sequence'], index)
            if index:
                self.assertEqual(packet['previous_sha256'], packets[index - 1]['packet_sha256'])
        self.assertEqual(packets[-1]['boundary'], 'complete')
        self.assertIn('nothing to continue', packets[-1]['next_safe_action'])

    # the recorded plan is validated by default (W04)
    def test_private_pilot_plan_is_validated_by_default_and_its_drift_is_refused(self):
        relative = '.crewloom/pilots/' + PLAN_ID + '/workflow.json'
        cont._private_write(w.plan_source(self.root, relative), json.dumps(self.parsed))
        packet = self.interrupted_mid_task(plan_file=relative)
        self.assertEqual(packet['workflow']['plan_file'], relative)
        self.assertTrue(cont.validate(self.root, self.latest_path(), RECEIVER)['accepted'])
        changed = json.loads(w.plan_source(self.root, relative).read_text())
        changed['steps'][1]['summary'] = 'Different verification'
        cont._private_write(w.plan_source(self.root, relative), json.dumps(changed))
        result = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertFalse(result['accepted'])
        self.assertIn('workflow plan changed since the checkpoint', result['reasons'])

    def snapshot_state(self):
        folder = cont.folder(self.root, PLAN_ID)
        return (sorted(p.name for p in folder.iterdir()), self.attempts_bytes(),
                (self.root / 'output.txt').read_bytes())

    def test_the_recorded_plan_path_is_used_by_default_and_drift_is_refused_without_side_effects(self):
        packet = self.interrupted_mid_task()
        self.assertEqual(packet['workflow']['plan_file'], 'workflow.json')
        self.assertEqual(json.loads((w.runtime(self.root, PLAN_ID) / 'state.json').read_text())['plan_file'], 'workflow.json')
        (self.root / 'dirty.txt').write_text('uncommitted edit', encoding='utf-8')
        self.assertTrue(cont.validate(self.root, self.latest_path(), RECEIVER)['accepted'])
        original = (self.root / 'workflow.json').read_text()
        changed = json.loads(original)
        changed['steps'][1]['summary'] = 'Verify differently'
        (self.root / 'workflow.json').write_text(json.dumps(changed), encoding='utf-8')
        before = self.snapshot_state()
        result = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertFalse(result['accepted'])
        self.assertIn('workflow plan changed since the checkpoint', result['reasons'])
        with self.assertRaisesRegex(ValueError, 'workflow plan changed since the checkpoint'):
            cont.accept(self.root, self.latest_path(), RECEIVER)
        self.assertFalse((cont.folder(self.root, PLAN_ID) / 'owner.json').exists(), 'a refusal claims nothing')
        self.assertEqual(self.snapshot_state(), before)
        self.assertEqual((self.root / 'dirty.txt').read_text(), 'uncommitted edit')
        command = ['validate', '--project', str(self.root), '--workflow', PLAN_ID, '--receiver-id', 'agent-b',
                   '--receiver-host', 'codex', '--receiver-model', 'gpt-6-sol']
        with patch('builtins.print'):
            self.assertEqual(cont.main(command), 2, 'the normal command refuses without a --plan argument')
        (self.root / 'workflow.json').write_text(original, encoding='utf-8')
        with patch('builtins.print'):
            self.assertEqual(cont.main(command), 0)

    def test_an_explicit_plan_file_is_held_to_the_recorded_identity_and_fingerprint(self):
        self.interrupted_mid_task()
        shutil.copy(self.root / 'workflow.json', self.root / 'moved.json')
        self.assertTrue(cont.validate(self.root, self.latest_path(), RECEIVER, 'moved.json')['accepted'],
                        'the same plan under another name is the same plan')
        other = json.loads((self.root / 'workflow.json').read_text())
        other['steps'][0]['summary'] = 'Not the recorded build'
        (self.root / 'other.json').write_text(json.dumps(other), encoding='utf-8')
        result = cont.validate(self.root, self.latest_path(), RECEIVER, 'other.json')
        self.assertIn('workflow plan changed since the checkpoint', result['reasons'])
        other['id'] = 'another-flow'
        (self.root / 'renamed.json').write_text(json.dumps(other), encoding='utf-8')
        self.assertIn('workflow plan identity differs from the checkpoint',
                      cont.validate(self.root, self.latest_path(), RECEIVER, 'renamed.json')['reasons'])
        (self.root / 'broken.json').write_text('{not json', encoding='utf-8')
        self.assertTrue(cont.validate(self.root, self.latest_path(), RECEIVER, 'broken.json')['reasons'][0]
                        .startswith('workflow plan cannot be verified'))

    def test_escaping_missing_and_linked_plan_paths_are_refused_safely(self):
        self.interrupted_mid_task()
        outside = self.base / 'outside.json'
        shutil.copy(self.root / 'workflow.json', outside)
        os.symlink(self.root / 'workflow.json', self.root / 'link.json')
        for override in ('../outside.json', str(outside), 'missing.json', 'link.json', '.git/config', '.crewloom/x.json'):
            with self.subTest(override=override):
                result = cont.validate(self.root, self.latest_path(), RECEIVER, override)
                self.assertFalse(result['accepted'])
                self.assertTrue(result['reasons'][0].startswith('workflow plan cannot be verified'), result['reasons'])
        # the recorded path itself replaced by a link to an identical file is refused too
        (self.root / 'real.json').write_text((self.root / 'workflow.json').read_text(), encoding='utf-8')
        (self.root / 'workflow.json').unlink()
        os.symlink(self.root / 'real.json', self.root / 'workflow.json')
        result = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertIn('symlinks', ' '.join(result['reasons']))
        (self.root / 'workflow.json').unlink()
        result = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertIn('the plan file is missing', ' '.join(result['reasons']))

    def test_a_programmatic_plan_has_an_explicit_validated_contract(self):
        self.interrupted_mid_task(plan_file=None)
        packet = json.loads((cont.folder(self.root, PLAN_ID) / 'latest.json').read_text())
        self.assertIsNone(packet['workflow']['plan_file'])
        before = self.snapshot_state()
        refused = cont.validate(self.root, self.latest_path(), RECEIVER)
        self.assertIn('recorded no plan path', ' '.join(refused['reasons']), 'no path is invented and no check is skipped')
        with self.assertRaisesRegex(ValueError, 'recorded no plan path'):
            cont.accept(self.root, self.latest_path(), RECEIVER)
        self.assertEqual(self.snapshot_state(), before)
        self.assertTrue(cont.validate(self.root, self.latest_path(), RECEIVER, plan=self.parsed)['accepted'])
        drifted = json.loads(json.dumps(self.parsed))
        drifted['steps'][0]['summary'] = 'drifted'
        self.assertIn('workflow plan changed since the checkpoint',
                      cont.validate(self.root, self.latest_path(), RECEIVER, plan=drifted)['reasons'])
        wrong_id = dict(self.parsed, id='another-flow')
        self.assertIn('workflow plan identity differs from the checkpoint',
                      cont.validate(self.root, self.latest_path(), RECEIVER, plan=wrong_id)['reasons'])
        invalid = dict(self.parsed, steps=[])
        self.assertTrue(cont.validate(self.root, self.latest_path(), RECEIVER, plan=invalid)['reasons'][0]
                        .startswith('workflow plan cannot be verified'))
        both = cont.validate(self.root, self.latest_path(), RECEIVER, 'workflow.json', plan=self.parsed)
        self.assertIn('not both', ' '.join(both['reasons']))
        accepted = cont.accept(self.root, self.latest_path(), RECEIVER, plan=self.parsed)
        self.assertEqual(accepted['owner']['state'], 'active')


class ContinuationCommand(unittest.TestCase):
    def test_cli_creates_and_validates_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(folder).resolve()
            git(root, 'init', '-q')
            crewloom.install_skills(root, 'agents', [ROLE], False)
            (root / 'input.txt').write_text('x', encoding='utf-8')
            pb.bootstrap(root, project_id='cli-project')
            plan = {'schema_version': 1, 'id': 'cli-flow', 'steps': [{'id': 'build', 'role': ROLE, 'summary': 'B',
                    'argv': ['python3', 'b.py'], 'inputs': ['input.txt'], 'outputs': ['o.txt']}]}
            (root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
            script = str(Path(__file__).resolve().parent / 'crewloom.py')
            env = repo_map.git_environment()
            created = subprocess.run(['python3', script, 'continuation', 'create', '--project', str(root),
                                      '--plan', 'workflow.json'], cwd=elsewhere, env=env, capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stdout + created.stderr)
            self.assertEqual(json.loads(created.stdout)['next_safe_action'].split()[0], 'resume')
            checked = subprocess.run(['python3', script, 'continuation', 'validate', '--project', str(root),
                                      '--workflow', 'cli-flow', '--receiver-id', 'r1', '--receiver-host', 'codex'],
                                     cwd=elsewhere, env=env, capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stdout)
            self.assertTrue(json.loads(checked.stdout)['accepted'])
            self.assertEqual(os.listdir(elsewhere), [])



class ContinuationOwnership(ContinuationBoundaries):
    """Atomic owner claim and runtime fencing with real validation and controlled scheduling."""

    def prepare(self):
        self.interrupted_mid_task()
        cont.reconcile(self.root, PLAN_ID)

    def race(self, receivers):
        """Run `accept` for every receiver while the first stays inside validation until the rest tried."""
        real_validate = cont._validate
        entered, others_done, first = threading.Event(), threading.Event(), []
        outcomes = {}

        def paused(*args, **kwargs):
            result = real_validate(*args, **kwargs)  # the real decision, made before anyone claims
            if not first:
                first.append(True)
                entered.set()
                others_done.wait(10)
            return result

        def attempt(receiver):
            try:
                outcomes[receiver['id']] = cont.accept(self.root, self.latest_path(), receiver)
            except (ValueError, OSError) as exc:
                outcomes[receiver['id']] = exc

        with patch.object(cont, '_validate', side_effect=paused):
            lead = threading.Thread(target=attempt, args=(receivers[0],))
            lead.start()
            self.assertTrue(entered.wait(10))
            for receiver in receivers[1:]:
                attempt(receiver)
            others_done.set()
            lead.join(15)
        return outcomes

    def test_two_simultaneous_receivers_exactly_one_wins(self):
        self.prepare()
        outcomes = self.race([RECEIVER, dict(RECEIVER, id='agent-c', host='opencode')])
        winners = [name for name, value in outcomes.items() if isinstance(value, dict)]
        self.assertEqual(winners, ['agent-b'])
        self.assertIsInstance(outcomes['agent-c'], ValueError)
        self.assertRegex(str(outcomes['agent-c']), 'locked')
        owner = cont.read_owner(self.root, PLAN_ID)
        self.assertEqual((owner['owner'], owner['epoch']), ('agent-b', 1))

    def test_negative_control_without_the_critical_section_both_receivers_are_accepted(self):
        self.prepare()
        import contextlib
        with patch.object(cont, '_project_lock', side_effect=lambda *a, **k: contextlib.nullcontext()):
            outcomes = self.race([RECEIVER, dict(RECEIVER, id='agent-c', host='opencode')])
        self.assertTrue(all(isinstance(value, dict) and value['accepted'] for value in outcomes.values()), outcomes)

    def resume(self, claim):
        calls = []

        def execute(root, step, image, timeout):
            calls.append(step['id'])
            for name in step['outputs']:
                (root / name).write_text('resumed ' + step['id'], encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image, 'duration_ms': 1}
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(execution_policy, 'execute', side_effect=execute):
            try:
                result = w.run(self.root, self.parsed, self.fingerprint, 'image', owner=claim, plan_file='workflow.json')
            except RuntimeError as exc:
                result = exc
        return result, calls

    def test_an_interrupt_between_steps_stops_the_running_owner_before_its_next_dispatch(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_flow(interrupt_at='build')  # nothing completed: both steps are still pending
        cont.reconcile(self.root, PLAN_ID)
        accepted = cont.accept(self.root, self.latest_path(), RECEIVER)
        claim = {'owner': 'agent-b', 'epoch': accepted['owner']['epoch'], 'token': accepted['owner_token']}
        calls = []

        def execute(root, step, image, timeout):
            calls.append(step['id'])
            for name in step['outputs']:
                (root / name).write_text('produced by ' + step['id'], encoding='utf-8')
            if step['id'] == 'build':  # the interrupt lands between the two steps, on the run's own lock
                cont.interrupt(self.root, PLAN_ID, {'kind': 'quota_exhausted', 'confidence': 'confirmed'}, 'host stopped')
            return {'exit_code': 0, 'output': '', 'image_id': image, 'duration_ms': 1}
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(execution_policy, 'execute', side_effect=execute):
            with self.assertRaisesRegex(cont.OwnershipError, 'was interrupted'):
                w.run(self.root, self.parsed, self.fingerprint, 'image', owner=claim, plan_file='workflow.json')
        self.assertEqual(calls, ['build'], 'the second step was never dispatched')
        self.assertFalse((self.root / 'verified.txt').exists())
        self.assertEqual((self.root / 'output.txt').read_text(), 'produced by build', 'completed work is preserved')
        result, calls_after = self.resume(claim)  # the interrupted slot admits nobody, including the old owner
        self.assertIsInstance(result, cont.OwnershipError)
        self.assertEqual(calls_after, [])

    def test_only_the_live_owner_with_its_token_may_dispatch_and_publish(self):
        self.prepare()
        accepted = cont.accept(self.root, self.latest_path(), RECEIVER)
        token, epoch = accepted['owner_token'], accepted['owner']['epoch']
        self.assertNotIn(token, (cont.folder(self.root, PLAN_ID) / 'owner.json').read_text())
        verify_output = self.root / 'verified.txt'
        for label, claim in (('no claim', None),
                             ('copied identity without the token', {'owner': 'agent-b', 'epoch': epoch, 'token': 'x' * 64}),
                             ('another receiver', {'owner': 'agent-c', 'epoch': epoch, 'token': token}),
                             ('stale epoch', {'owner': 'agent-b', 'epoch': epoch - 1, 'token': token})):
            result, calls = self.resume(claim)
            self.assertIsInstance(result, cont.OwnershipError, label)
            self.assertEqual(calls, [], label)
            self.assertFalse(verify_output.exists(), label)
        result, calls = self.resume({'owner': 'agent-b', 'epoch': epoch, 'token': token})
        self.assertEqual((result['status'], calls), ('complete', ['verify']))  # build output was preserved
        self.assertTrue(verify_output.exists())

    def test_changed_policy_wrong_root_and_interruption_withdraw_the_slot(self):
        self.prepare()
        accepted = cont.accept(self.root, self.latest_path(), RECEIVER)
        claim = {'owner': 'agent-b', 'epoch': accepted['owner']['epoch'], 'token': accepted['owner_token']}
        policy = self.root / 'crewloom.project.json'
        original = policy.read_text()
        policy.write_text(original.replace('\n', ' \n', 1) if '\n' in original else original + ' ')
        self.assertRegex(str(self.resume(claim)[0]), 'policy changed')
        policy.write_text(original)
        owner_file = cont.folder(self.root, PLAN_ID) / 'owner.json'
        record = json.loads(owner_file.read_text())
        owner_file.write_text(json.dumps(dict(record, project_root='/elsewhere')))
        self.assertRegex(str(self.resume(claim)[0]), 'root or policy changed')
        owner_file.write_text(json.dumps(record))
        cont.interrupt(self.root, PLAN_ID, None, 'quota stop')
        result, calls = self.resume(claim)
        self.assertRegex(str(result), 'interrupted')
        self.assertEqual(calls, [])
        cont.release(self.root, PLAN_ID)
        self.assertEqual(self.resume(None)[0]['status'], 'complete')  # a released slot is ordinary again

    def test_owner_changes_serialise_with_a_live_run_and_reconcile_needs_the_claim(self):
        self.prepare()
        accepted = cont.accept(self.root, self.latest_path(), RECEIVER)
        with w.project_lock(w.safe_path(self.root, '.crewloom', internal=True), reentrant=False):
            for action in (lambda: cont.interrupt(self.root, PLAN_ID), lambda: cont.release(self.root, PLAN_ID),
                           lambda: cont.reconcile(self.root, PLAN_ID),
                           lambda: cont.accept(self.root, self.latest_path(), dict(RECEIVER, id='agent-c'))):
                with self.assertRaisesRegex(ValueError, 'locked'):
                    action()
            self.assertIn('accepted', cont.validate(self.root, self.latest_path(), RECEIVER))  # advisory read: no lock
        with self.assertRaises(cont.OwnershipError):
            cont.reconcile(self.root, PLAN_ID)
        self.assertEqual(cont.reconcile(self.root, PLAN_ID, {'owner': 'agent-b', 'epoch': 1, 'token': accepted['owner_token']}), [])


if __name__ == '__main__':
    unittest.main()
