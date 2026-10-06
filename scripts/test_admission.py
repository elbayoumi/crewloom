"""W09: aggregate budgets, bounded dispatch, restart-safe reservations and owned-process cancellation."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import admission as adm
import crewloom
import execution_policy
import model_host
import repo_map
import workflow as w

SCRIPTS = Path(__file__).resolve().parent
ADMIT = ("import sys; sys.path.insert(0, %r); import admission as a, json;"
         "r = a.admit(sys.argv[1], sys.argv[2], {'input_bytes': int(sys.argv[3])}, {'task': sys.argv[2]});"
         "print(json.dumps(r['decision']))" % str(SCRIPTS))


def alive(pid):
    return adm.pid_alive(pid)


class AdmissionBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-admission-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name) / 'batch'
        self.children = []
        self.addCleanup(self.reap)

    def reap(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
                child.wait()

    def configure(self, **limits):
        return adm.configure(self.folder, 'batch-one', limits)

    def sleeper(self):
        child = subprocess.Popen(['sleep', '60'])
        self.children.append(child)
        return child

    def cli_admit(self, request_id, size=10):
        out = subprocess.run([sys.executable, '-c', ADMIT, str(self.folder), request_id, str(size)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    # limits
    def test_limit_values_are_validated_and_unset_ones_are_reported_unbounded(self):
        for bad in ({'max_model_requests': 0}, {'max_model_requests': '3'}, {'surprise': 1}, {'max_input_bytes': True}):
            with self.subTest(bad=bad), self.assertRaises(adm.AdmissionError):
                adm.validate_limits(bad)
        self.configure(max_model_requests=2)
        self.assertEqual(adm.summary(self.folder)['unbounded'],
                         ['max_concurrent_requests', 'max_elapsed_seconds', 'max_input_bytes', 'max_output_tokens'])

    def test_a_resume_may_tighten_but_never_loosen_or_reset_limits(self):
        self.configure(max_model_requests=5)
        self.assertEqual(self.configure(max_model_requests=9)['max_model_requests'], 5)
        self.assertEqual(self.configure(max_model_requests=3)['max_model_requests'], 3)
        self.assertEqual(self.configure()['max_model_requests'], 3)
        with self.assertRaises(adm.AdmissionError):
            adm.configure(self.folder, 'another-batch', {})

    # aggregate across worktrees / processes
    def test_the_request_budget_is_atomic_across_separate_processes(self):
        self.configure(max_model_requests=3)
        processes = [subprocess.Popen([sys.executable, '-c', ADMIT, str(self.folder), 'req-%d' % i, '10'],
                                      stdout=subprocess.PIPE, text=True) for i in range(8)]
        decisions = [json.loads(p.communicate(timeout=60)[0]) for p in processes]
        self.assertEqual(decisions.count('admitted'), 3, decisions)
        self.assertEqual(decisions.count('refused'), 5)
        self.assertEqual(adm.summary(self.folder)['charged_requests'], 3)

    def test_input_bytes_and_elapsed_time_are_bounded(self):
        self.configure(max_input_bytes=100)
        self.assertEqual(adm.admit(self.folder, 'a', {'input_bytes': 60})['decision'], 'admitted')
        refused = adm.admit(self.folder, 'b', {'input_bytes': 60})
        self.assertEqual(refused['decision'], 'refused')
        self.assertIn('input byte budget', refused['reason'])
        other = self.folder.parent / 'timed'
        adm.configure(other, 'timed', {'max_elapsed_seconds': 5})
        record = json.loads((other / 'admission.json').read_text())
        record['started_at'] -= 60
        (other / 'admission.json').write_text(json.dumps(record))
        self.assertIn('elapsed-time', adm.admit(other, 'late', {})['reason'])

    def test_estimates_must_be_non_negative_integers(self):
        self.configure()
        for bad in ({'input_bytes': -1}, {'input_bytes': 1.5}, {'output_tokens': '9'}):
            with self.subTest(bad=bad), self.assertRaises(adm.AdmissionError):
                adm.admit(self.folder, 'x', bad)

    # queued state
    def test_the_concurrency_limit_queues_without_charging_and_promotes_later(self):
        self.configure(max_concurrent_requests=1, max_model_requests=5)
        self.assertEqual(adm.admit(self.folder, 'first', {})['decision'], 'admitted')
        second = adm.admit(self.folder, 'second', {})
        self.assertEqual(second['decision'], 'queued')
        self.assertEqual(adm.summary(self.folder)['charged_requests'], 1, 'a queued request holds no budget')
        self.assertEqual(adm.admit(self.folder, 'second', {})['decision'], 'queued')
        adm.finish(self.folder, 'first', 'succeeded')
        self.assertEqual(adm.admit(self.folder, 'second', {})['decision'], 'admitted')
        self.assertEqual(adm.cancel_queued(self.folder), [])

    def test_cancelled_queue_entries_never_dispatch(self):
        self.configure(max_concurrent_requests=1)
        adm.admit(self.folder, 'a', {})
        adm.admit(self.folder, 'b', {})
        self.assertEqual(adm.cancel_queued(self.folder), ['b'])
        self.assertEqual(adm.summary(self.folder)['states'], {'dispatched': 1, 'cancelled': 1})

    # idempotent reservations, restart recovery
    def test_a_resumed_request_is_not_charged_twice_or_given_a_replacement_slot(self):
        self.configure(max_model_requests=2)
        self.assertEqual(self.cli_admit('same'), 'admitted')
        for _ in range(3):
            self.assertEqual(self.cli_admit('same'), 'existing')
        self.assertEqual(adm.summary(self.folder)['charged_requests'], 1)

    def test_an_owner_that_died_leaves_an_orphan_that_stays_charged_and_is_never_replayed(self):
        self.configure(max_model_requests=2)
        self.assertEqual(self.cli_admit('crashed'), 'admitted')  # the owning process has exited
        report = adm.recover(self.folder)
        self.assertEqual(report['orphaned_requests'], ['crashed'])
        self.assertEqual(adm.summary(self.folder)['states'], {'orphaned': 1})
        again = adm.admit(self.folder, 'crashed', {})
        self.assertEqual((again['decision'], again['state']), ('existing', 'orphaned'))
        self.assertEqual(adm.admit(self.folder, 'fresh', {})['decision'], 'admitted')
        self.assertEqual(adm.admit(self.folder, 'third', {})['decision'], 'refused', 'the orphan still counts')
        self.assertEqual(adm.recover(self.folder)['orphaned_requests'], [], 'recovery is idempotent')

    def test_a_live_owner_is_not_orphaned(self):
        self.configure()
        adm.admit(self.folder, 'mine', {})
        self.assertEqual(adm.recover(self.folder)['orphaned_requests'], [])

    def test_reconciliation_keeps_estimates_and_reported_usage_apart_and_unknown_stays_null(self):
        self.configure()
        adm.admit(self.folder, 'a', {'input_bytes': 500, 'output_tokens': 100})
        adm.admit(self.folder, 'b', {'input_bytes': 700})
        adm.finish(self.folder, 'a', 'succeeded', {'input_tokens': 120, 'output_tokens': 30, 'cost_usd': 0.5, 'junk': 'x'})
        adm.finish(self.folder, 'b', 'failed', None)
        summary = adm.summary(self.folder)
        self.assertEqual(summary['estimated_input_bytes'], 1200)
        self.assertEqual(summary['recorded_usage']['input_tokens'], 120)
        value = json.loads((self.folder / 'admission.json').read_text())
        self.assertNotIn('junk', value['requests']['a']['usage'])
        self.assertIsNone(value['requests']['b']['usage'])
        fresh = self.folder.parent / 'no-usage'
        adm.configure(fresh, 'x', {})
        adm.admit(fresh, 'r', {})
        adm.finish(fresh, 'r', 'succeeded', {})
        self.assertIsNone(adm.summary(fresh)['recorded_usage']['input_tokens'])
        self.assertIsNone(adm.finish(self.folder, 'a', 'failed'), 'a finished request cannot be re-finished')

    # cancellation
    def test_cancellation_stops_exactly_the_owned_processes_and_nothing_else(self):
        self.configure()
        owned, unrelated = self.sleeper(), self.sleeper()
        adm.track_process(self.folder, 'process', owned.pid, owned.pid, 'task-a')
        results = adm.terminate_owned(self.folder)
        owned.wait(timeout=10)
        self.assertIsNotNone(owned.poll(), 'the owned process is gone')
        self.assertIsNone(unrelated.poll(), 'an unrelated process is untouched')
        self.assertEqual([r['result'] for r in results], ['terminated'])
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], [])

    def test_a_reused_pid_with_a_different_identity_is_never_signalled(self):
        self.configure()
        bystander = self.sleeper()
        adm.track_process(self.folder, 'process', bystander.pid, bystander.pid, 'task')
        record = json.loads((self.folder / 'admission.json').read_text())
        key = 'process:%d' % bystander.pid
        record['processes'][key]['pid_start'] = 'Thu Jan  1 00:00:00 1970'
        (self.folder / 'admission.json').write_text(json.dumps(record))
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'gone')
        self.assertIsNone(bystander.poll(), 'identity mismatch protects the process')

    def test_owned_containers_are_removed_by_name_and_only_those(self):
        self.configure()
        removed = []
        adm.track_process(self.folder, 'container', 'crewloom-owned-1', 111, 'task-a')
        adm.track_process(self.folder, 'container', 'crewloom-owned-2', 112, 'task-b')
        with patch.object(adm, '_stop_container', side_effect=lambda name: removed.append(name) or True):
            results = adm.terminate_owned(self.folder)
        self.assertEqual(sorted(removed), ['crewloom-owned-1', 'crewloom-owned-2'])
        self.assertEqual({r['result'] for r in results}, {'removed'})
        with patch.object(adm, '_stop_container', return_value=False):
            adm.track_process(self.folder, 'container', 'stubborn', None, 't')
            self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'remove failed')
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], ['container:stubborn'], 'a failure stays visible')

    def test_restart_reconciliation_stops_only_entries_whose_controller_died(self):
        self.configure()
        mine = self.sleeper()
        adm.track_process(self.folder, 'process', mine.pid, mine.pid, 'live-controller')
        orphan = self.sleeper()
        record = json.loads((self.folder / 'admission.json').read_text())
        record['processes']['process:%d' % orphan.pid] = {
            'kind': 'process', 'ident': str(orphan.pid), 'pid': orphan.pid, 'pid_start': adm.process_start(orphan.pid),
            'controller_pid': 2 ** 22 + 12345, 'controller_start': 'gone', 'task': 'dead-controller', 'tracked_at': 0}
        (self.folder / 'admission.json').write_text(json.dumps(record))
        report = adm.recover(self.folder)
        orphan.wait(timeout=10)
        self.assertEqual([item['task'] for item in report['stopped']], ['dead-controller'])
        self.assertIsNotNone(orphan.poll())
        self.assertIsNone(mine.poll(), 'work owned by a live controller is left alone')

    def test_tracking_outside_a_batch_is_a_noop(self):
        self.assertIsNone(adm.track_current('process', 1, 1))
        adm.untrack_current('process', 1)
        with adm.context(self.folder, 'task'):
            self.assertEqual(adm.current()['task'], 'task')
        self.assertIsNone(adm.current())


class BatchBudgetAtTheModelStep(unittest.TestCase):
    """The workflow reserves the batch budget before any ledger entry or provider call."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-admission-flow-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve() / 'app'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        (self.root / 'a.py').write_text('def a():\n    return 1\n', encoding='utf-8')
        steps = [{'id': name, 'role': 'context-guardian', 'kind': 'model', 'host': 'openai', 'model': 'gpt-test',
                  'summary': 'Generate ' + name, 'inputs': ['a.py'], 'outputs': [name + '.py']}
                 for name in ('first', 'second')]
        (self.root / 'workflow.json').write_text(json.dumps({'schema_version': 1, 'id': 'budgeted', 'steps': steps}))
        self.parsed, self.fingerprint = w.read_plan(self.root, 'workflow.json')
        self.folder = Path(temporary.name) / 'batch'
        self.calls = []

    def run_plan(self):
        def generate(host, prompt, outputs, *args, **kwargs):
            self.calls.append(outputs[0])
            return {outputs[0]: 'x = 1\n'}, {'host': host, 'usage': {'input_tokens': 42, 'output_tokens': 7}}
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(model_host, 'generate', side_effect=generate), \
                adm.context(self.folder, 'task-one'):
            return w.run(self.root, self.parsed, self.fingerprint, 'image')

    def test_the_batch_budget_stops_the_second_request_before_any_provider_call(self):
        adm.configure(self.folder, 'b', {'max_model_requests': 1})
        result = self.run_plan()
        self.assertEqual(self.calls, ['first.py'], 'only the admitted request reached the provider')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('Batch admission refused', json.dumps(result))
        summary = adm.summary(self.folder)
        self.assertEqual((summary['states'], summary['recorded_usage']['input_tokens']), ({'succeeded': 1}, 42))
        ledger = json.loads((self.root / '.crewloom/attempts.json').read_text())['attempts']
        self.assertEqual([a['status'] for a in ledger if a.get('kind') == 'model'], ['succeeded'],
                         'the refused request created no ledger attempt')

    def test_resuming_charges_nothing_and_never_replays_a_completed_step(self):
        adm.configure(self.folder, 'b', {'max_model_requests': 2})
        self.assertEqual(self.run_plan()['status'], 'complete')
        before = adm.summary(self.folder)
        self.assertEqual(self.run_plan()['status'], 'complete')
        self.assertEqual(self.calls, ['first.py', 'second.py'])
        self.assertEqual(adm.summary(self.folder)['charged_requests'], before['charged_requests'])

    def test_a_provider_failure_is_reconciled_and_the_charge_is_kept(self):
        adm.configure(self.folder, 'b', {'max_model_requests': 5})

        def broken(*args, **kwargs):
            raise ValueError('Provider rejected generation')
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(model_host, 'generate', side_effect=broken), adm.context(self.folder, 't'):
            result = w.run(self.root, self.parsed, self.fingerprint, 'image')
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(adm.summary(self.folder)['states'], {'failed': 1})

    def test_without_a_batch_context_nothing_is_reserved(self):
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(model_host, 'generate', side_effect=lambda h, p, o, *a, **k: ({o[0]: 'x = 1\n'}, {})):
            self.assertEqual(w.run(self.root, self.parsed, self.fingerprint, 'image')['status'], 'complete')
        self.assertFalse(self.folder.exists())

    def test_a_queued_request_waits_and_is_refused_when_the_batch_is_cancelled(self):
        adm.configure(self.folder, 'b', {'max_concurrent_requests': 1})
        adm.admit(self.folder, 'someone-else', {})          # holds the only concurrent slot
        (self.folder / 'cancel.request').write_text('{}')
        result = self.run_plan()
        self.assertEqual(self.calls, [])
        self.assertIn('cancelled while the request was queued', json.dumps(result))
        self.assertNotIn('queued', adm.summary(self.folder)['states'])


if __name__ == '__main__':
    unittest.main()
