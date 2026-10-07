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
                         ['max_concurrent_requests', 'max_elapsed_seconds', 'max_input_bytes', 'max_output_tokens',
                          'max_output_tokens_per_request'])  # W09: the per-request ceiling is its own limit

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

    # Semantic change (W09): removal by saved name was replaced by removal by verified immutable id. The
    # old stub of `docker rm <name>` could not tell our container from a reused name; the identity cases
    # (owned removed, reused name preserved, mismatch, unverifiable, legacy, recovery) live in
    # test_owned_resources.py.

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


class AggregateOutputAndHonestAccounting(unittest.TestCase):
    """W09: per-request ceilings, aggregate reservations, reported usage and unknown limits stay distinct."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-aggregate-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name) / 'batch'

    def configure(self, **limits):
        return adm.configure(self.folder, 'batch-one', limits)

    def admit(self, name, ceiling, **extra):
        return adm.admit(self.folder, name, dict({'output_tokens': ceiling}, **extra))['decision']

    def test_two_individually_legal_requests_cannot_over_reserve_the_batch_ceiling(self):
        self.configure(max_output_tokens=100)
        self.assertEqual(self.admit('a', 100), 'admitted')
        refused = adm.admit(self.folder, 'b', {'output_tokens': 100})
        self.assertEqual(refused['decision'], 'refused')
        self.assertIn('aggregate output reservation', refused['reason'])
        self.assertEqual(adm.summary(self.folder)['reserved_output_tokens'], 100)

    def test_concurrent_reservations_never_exceed_the_ceiling(self):
        self.configure(max_output_tokens=100)
        results = []
        threads = [__import__('threading').Thread(target=lambda n=n: results.append(self.admit('r%d' % n, 40)))
                   for n in range(8)]
        [t.start() for t in threads]
        [t.join(30) for t in threads]
        self.assertEqual(sorted(results), ['admitted'] * 2 + ['refused'] * 6)
        self.assertEqual(adm.summary(self.folder)['reserved_output_tokens'], 80)

    def test_a_negative_control_without_the_aggregate_accounting_admits_both(self):
        self.configure(max_output_tokens=100)
        with patch.object(adm, '_used', side_effect=lambda value, key: 0 if key == 'output' else
                          sum(1 for e in value['requests'].values() if e['state'] in adm.CHARGED)):
            decisions = (self.admit('a', 100), self.admit('b', 100))
        self.assertEqual(decisions, ('admitted', 'admitted'))  # the scenario does expose over-reservation
        self.configure()  # a resume cannot loosen the limit
        self.assertEqual(adm.summary(self.folder)['limits']['max_output_tokens'], 100)

    def test_unknown_or_unenforceable_output_bounds_do_not_pass_a_guaranteed_ceiling(self):
        self.configure(max_output_tokens=100)
        refused = adm.admit(self.folder, 'unbounded', {'output_tokens': None})
        self.assertEqual(refused['decision'], 'refused')
        self.assertIn('no enforceable output ceiling', refused['reason'])
        other = self.folder.parent / 'no-output-limit'
        adm.configure(other, 'x', {})
        self.assertEqual(adm.admit(other, 'unbounded', {'output_tokens': None})['decision'], 'admitted')

    def test_the_per_request_limit_is_its_own_contract(self):
        self.configure(max_output_tokens_per_request=50)
        self.assertEqual(self.admit('ok', 50), 'admitted')
        self.assertEqual(self.admit('over', 51), 'refused')
        self.assertEqual(adm.admit(self.folder, 'unknown', {'output_tokens': None})['decision'], 'refused')
        self.assertEqual(adm.output_ceiling(self.folder, 4096), 50)
        self.assertEqual(adm.output_ceiling(self.folder, 20), 20)
        self.assertIsNone(adm.output_ceiling(self.folder, None))

    def test_settlement_failure_and_orphans_are_reconciled_conservatively(self):
        self.configure(max_output_tokens=300)
        for name in ('ok', 'overran', 'failed'):
            self.assertEqual(self.admit(name, 100), 'admitted', name)
        adm.finish(self.folder, 'ok', 'succeeded', {'output_tokens': 10})          # actual replaces the reservation
        self.assertEqual(adm.summary(self.folder)['reserved_output_tokens'], 10 + 100 + 100)
        adm.finish(self.folder, 'overran', 'succeeded', {'output_tokens': 140})    # an overrun is never hidden
        adm.finish(self.folder, 'failed', 'failed', None)                          # unknown usage keeps the reserve
        self.assertEqual(adm.summary(self.folder)['reserved_output_tokens'], 10 + 140 + 100)
        self.assertEqual(self.admit('late', 51), 'refused')   # 250 held, 50 left
        self.assertEqual(self.admit('late-small', 50), 'admitted')
        orphan = adm.admit(self.folder, 'x', {})  # no enforceable ceiling while the aggregate limit is set
        self.assertEqual(orphan['decision'], 'refused')

    def test_resume_neither_double_charges_nor_obtains_a_replacement_slot(self):
        self.configure(max_output_tokens=100)
        self.assertEqual(self.admit('a', 100), 'admitted')
        adm.finish(self.folder, 'a', 'failed', None)
        again = adm.admit(self.folder, 'a', {'output_tokens': 100})
        self.assertEqual(again['decision'], 'existing')
        self.assertEqual(self.admit('replacement', 100), 'refused')
        self.assertEqual(adm.summary(self.folder)['reserved_output_tokens'], 100)

    def test_malformed_negative_nonfinite_or_invalid_usage_is_rejected_visibly(self):
        self.configure()
        bad = {'input_tokens': True, 'output_tokens': -5, 'total_tokens': float('nan'), 'cost_usd': float('inf')}
        self.assertEqual(adm.clean_usage(bad), ({}, ['input_tokens', 'output_tokens', 'total_tokens', 'cost_usd']))
        self.assertEqual(adm.clean_usage({'input_tokens': 1.5, 'output_tokens': '7', 'cost_usd': -0.1})[1],
                         ['input_tokens', 'output_tokens', 'cost_usd'])
        self.assertEqual(adm.clean_usage({'input_tokens': 12.0, 'cost_usd': 0})[0], {'input_tokens': 12, 'cost_usd': 0})
        self.assertEqual(adm.clean_usage('junk'), ({}, []))
        adm.admit(self.folder, 'r', {})
        adm.finish(self.folder, 'r', 'succeeded', dict(bad, total_tokens=9))
        entry = json.loads((self.folder / 'admission.json').read_text())['requests']['r']
        self.assertEqual((entry['usage'], entry['usage_rejected']),
                         ({'total_tokens': 9}, ['input_tokens', 'output_tokens', 'cost_usd']))

    def test_partial_usage_totals_identify_incomplete_coverage(self):
        self.configure()
        for name, usage in (('a', {'output_tokens': 5, 'cost_usd': 0.5}), ('b', None), ('c', {'output_tokens': 7})):
            adm.admit(self.folder, name, {})
            adm.finish(self.folder, name, 'succeeded', usage)
        usage = adm.summary(self.folder)['recorded_usage']
        self.assertEqual(usage['output_tokens'], 12)
        self.assertEqual(usage['coverage']['output_tokens'],
                         {'reporting_requests': 2, 'settled_requests': 3, 'complete': False})
        self.assertEqual(usage['coverage']['cost_usd']['reporting_requests'], 1)

    def test_unsupported_guarantees_are_stated_not_implied(self):
        with self.assertRaisesRegex(adm.AdmissionError, 'subset of'):
            adm.validate_limits({'max_cost_usd': 5})
        self.configure()
        enforcement = adm.summary(self.folder)['enforcement']
        self.assertIn('not supported', enforcement['cost_cap'])
        self.assertIn('does not stop work in flight', enforcement['elapsed'])
        self.assertIn('not counted or capped', enforcement['unmanaged_activity'])

    def test_elapsed_budget_is_an_admission_deadline_not_a_stop_for_work_in_flight(self):
        self.configure(max_elapsed_seconds=1)
        self.assertEqual(self.admit('inflight', 1), 'admitted')
        record = json.loads((self.folder / 'admission.json').read_text())
        record['started_at'] -= 60
        (self.folder / 'admission.json').write_text(json.dumps(record))
        self.assertEqual(adm.admit(self.folder, 'new', {})['decision'], 'refused')
        self.assertEqual(adm.finish(self.folder, 'inflight', 'succeeded', {})['state'], 'succeeded')


class OutputCeilingReachesTheAdapter(unittest.TestCase):
    def test_the_provider_payload_honors_a_tighter_bound_and_never_a_looser_one(self):
        import provider_gateway as gateway
        payloads = []

        class Opener:
            def open(self, request, timeout=None):
                payloads.append(json.loads(request.data))
                raise ValueError('stop after capture')
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'k', 'ANTHROPIC_API_KEY': 'k'}), \
                patch('urllib.request.build_opener', return_value=Opener()):
            for provider, key in (('openai', 'max_output_tokens'), ('anthropic', 'max_tokens')):
                for requested in (None, 100):
                    with self.assertRaises(ValueError):
                        gateway._request(provider, 'm', 'prompt', 5, requested)
                    self.assertEqual(payloads[-1][key], requested or gateway.MAX_OUTPUT_TOKENS)
            for invalid in (0, -1, gateway.MAX_OUTPUT_TOKENS + 1, True, 1.5, '5'):
                with self.assertRaisesRegex(ValueError, 'Output token ceiling'):
                    gateway._request('openai', 'm', 'prompt', 5, invalid)

    def test_an_installed_cli_host_refuses_a_guaranteed_ceiling_it_cannot_enforce(self):
        with self.assertRaisesRegex(ValueError, 'cannot enforce an output-token ceiling'):
            model_host.generate('codex', 'prompt', ['out.py'], 5, None, None, 100)


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
        self.kwargs = []

    def run_plan(self):
        def generate(host, prompt, outputs, *args, **kwargs):
            self.calls.append(outputs[0])
            self.kwargs.append(kwargs)
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

    def test_the_aggregate_output_ceiling_reaches_the_adapter_and_stops_the_second_request(self):
        adm.configure(self.folder, 'b', {'max_output_tokens': 100, 'max_output_tokens_per_request': 100})
        result = self.run_plan()
        self.assertEqual(self.calls, ['first.py'])
        self.assertEqual(self.kwargs, [{'max_output_tokens': 100}], 'the adapter is told the bound it must honor')
        self.assertIn('aggregate output reservation', json.dumps(result))
        self.assertEqual(adm.summary(self.folder)['reserved_output_tokens'], 7)  # reported actual replaced 100

    def test_a_host_without_an_enforceable_ceiling_is_refused_under_an_aggregate_limit(self):
        steps = [{'id': 'cli', 'role': 'context-guardian', 'kind': 'model', 'host': 'codex', 'model': 'gpt-test',
                  'summary': 'Generate', 'inputs': ['a.py'], 'outputs': ['cli.py']}]
        (self.root / 'cli.json').write_text(json.dumps({'schema_version': 1, 'id': 'cli-flow', 'steps': steps}))
        parsed, fingerprint = w.read_plan(self.root, 'cli.json')
        adm.configure(self.folder, 'b', {'max_output_tokens': 1000})
        with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                patch.object(model_host, 'generate', side_effect=AssertionError('must not dispatch')), \
                adm.context(self.folder, 't'):
            result = w.run(self.root, parsed, fingerprint, 'image', allow_host_cli=True)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('no enforceable output ceiling', json.dumps(result))
        self.assertEqual(adm.summary(self.folder)['charged_requests'], 0)

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

    def test_an_opencode_prompt_beyond_its_argv_bound_is_refused_before_any_reservation_attempt_or_launch(self):
        steps = [{'id': 'cli', 'role': 'context-guardian', 'kind': 'model', 'host': 'opencode', 'model': 'm/test',
                  'summary': 'Generate', 'inputs': ['a.py'], 'outputs': ['cli.py']}]
        (self.root / 'cli.json').write_text(json.dumps({'schema_version': 1, 'id': 'oc-flow', 'steps': steps}))
        parsed, fingerprint = w.read_plan(self.root, 'cli.json')
        adm.configure(self.folder, 'b', {'max_model_requests': 5})
        dispatched = []
        for size, refused in ((model_host.MAX_ARGV_TEXT + 1, True), (153600, True), (model_host.MAX_ARGV_TEXT, False)):
            with self.subTest(size=size), patch.object(w, 'inspect_image', return_value='sha256:t'), \
                    patch.object(model_host, 'build_prompt', return_value='x' * size), \
                    patch.object(model_host, 'generate', side_effect=lambda h, p, o, *a, **k: (
                        dispatched.append(h), ({o[0]: 'x = 1\n'}, {}))[1]), \
                    adm.context(self.folder, 't'):
                dispatched.clear()
                result = w.run(self.root, parsed, fingerprint, 'image', allow_host_cli=True)
                summary = adm.summary(self.folder)
                ledger = self.root / '.crewloom/attempts.json'
                attempts = json.loads(ledger.read_text())['attempts'] if ledger.exists() else []
                if refused:
                    self.assertEqual(result['status'], 'failed')
                    self.assertIn('exceeds the 131072 byte bound', json.dumps(result))
                    self.assertEqual((summary['charged_requests'], attempts, dispatched), (0, [], []))
                else:
                    self.assertEqual(result['status'], 'complete', result)
                    self.assertEqual((summary['charged_requests'], dispatched), (1, ['opencode']))

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
