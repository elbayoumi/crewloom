"""Independent acceptance for the study v2 runner.

Written before the implementation and frozen: the implementer may not edit this file. It pins what
an operator and a reader must be able to rely on before the 18-call v2 study is run:

* v1 behaviour and its protocol record are unchanged;
* v2 freezes its inputs, refuses to start when the offline sufficiency gate fails (before any
  provider call and before anything is written), and records every planned trial;
* groups and pairs describe full-source against closure-map only, with failures in denominators.

Every case is offline: the provider transport, the Docker image lookup and the container grader are
replaced by deterministic fakes, so nothing real is called and nothing is written outside a
disposable directory.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_hosts as e
import repo_map
import test_context_study as study_fixtures

REFERENCE = study_fixtures.REFERENCE
V2 = 'crewloom-context-study-v2'
V1 = 'crewloom-context-study-v1'
CLOSURE = 'closure-map'
IMAGE = 'sha256:' + 'a' * 64


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fake_generate(arm_tokens=None, fail_when=None, calls=None):
    """A deterministic stand-in for the provider transport: it returns the frozen reference."""
    arm_tokens = arm_tokens or {'full-source': 100, 'closure-map': 60, 'selected-map': 70}

    def generate(host_name, prompt, outputs, timeout, model, evidence=None):
        if calls is not None:
            calls.append((host_name, prompt))
        arm = ('closure-map' if '"mode":"closure-map"' in prompt else
               'selected-map' if '"mode":"selected-map"' in prompt else 'full-source')
        if fail_when and fail_when(host_name, arm, outputs[0]):
            raise ValueError('fake provider failure')
        source = REFERENCE[outputs[0]] + '\n# arm:' + arm + '\n'
        tokens = arm_tokens[arm]
        return {outputs[0]: source}, {'duration_ms': 7, 'model_reported': None,
                                      'host_version': 'fake 1.0', 'cost_usd': None,
                                      'usage_metrics': {'input_tokens': tokens,
                                                        'uncached_input_tokens': tokens,
                                                        'cached_input_tokens': 0,
                                                        'cache_write_tokens': None,
                                                        'output_tokens': 10,
                                                        'reasoning_tokens': None,
                                                        'total_tokens': tokens + 10}}
    return generate


def fake_grade(source, task, image_id, timeout, case_runs, fixture):
    passed = 6 if b'arm:closure-map' in source else 11
    return {'held_out_pass_count': passed, 'held_out_total': 11, 'checks_total': 11,
            'task': task['id']}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crewloom-v2-runner-')
        self.addCleanup(self.temp.cleanup)
        self.counter = 0
        for patcher in (mock.patch.object(e.w, 'inspect_image', return_value=IMAGE),
                        mock.patch.object(e, 'grade_study', side_effect=fake_grade)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def out(self):
        self.counter += 1
        return Path(self.temp.name) / ('out%d' % self.counter)

    def run_study(self, generate=None, **kwargs):
        destination = self.out()
        with mock.patch.object(e.host, 'generate', side_effect=generate or fake_generate()):
            report = e.collect_study(destination, kwargs.pop('hosts', ['codex']), **kwargs)
        return destination, report


class References(unittest.TestCase):
    def test_the_frozen_references_are_public_data_identical_to_the_acceptance_fixtures(self):
        references = e.study_references()
        outputs = {task['output'] for task in e.study_contracts()['tasks']}
        self.assertEqual(set(references), outputs)
        for output in outputs:
            self.assertEqual(references[output], REFERENCE[output], output)

    def test_no_reference_body_appears_in_any_generation_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            project = e.materialize_project(Path(folder) / 'project')
            prompts = [e.study_prompt(task, condition, project)[0]
                       for task in e.study_contracts()['tasks']
                       for condition in e.CONDITIONS + (CLOSURE,)]
        for output, text in e.study_references().items():
            body = [line.strip() for line in text.splitlines()
                    if len(line.strip()) >= 40 and not line.lstrip().startswith(('from ', 'import ', '"""'))]
            self.assertTrue(body, output)
            for prompt in prompts:
                for line in body:
                    self.assertNotIn(line, prompt, output)


class V1Unchanged(Base):
    def test_the_default_run_is_still_the_v1_protocol_with_its_exact_record(self):
        destination, report = self.run_study(hosts=['codex', 'opencode'])
        protocol = json.loads((destination / 'protocol.json').read_text())
        self.assertEqual(protocol['protocol'], V1)
        self.assertEqual(protocol['seed'], e.STUDY_SEED)
        self.assertEqual(protocol['conditions'], ['full-source', 'selected-map'])
        self.assertEqual(protocol['planned_calls'], 36)
        self.assertEqual(protocol['trial_order'], e.study_plan(['codex', 'opencode']))
        for key in ('sufficiency', 'references_sha256', 'map_generator_sha256'):
            self.assertNotIn(key, protocol)
        self.assertEqual({row['condition'] for row in report['results']}, {'full-source', 'selected-map'})
        self.assertEqual({group['condition'] for group in report['groups']}, {'full-source', 'selected-map'})

    def test_an_unknown_protocol_version_is_refused_before_anything_is_written(self):
        destination = self.out()
        with self.assertRaises(ValueError):
            e.collect_study(destination, ['codex'], protocol_version='v3')
        self.assertFalse(destination.exists())


class V2Freeze(Base):
    def test_the_protocol_record_freezes_every_v2_input_before_the_first_call(self):
        destination, report = self.run_study(protocol_version='v2')
        protocol = json.loads((destination / 'protocol.json').read_text())
        self.assertEqual(protocol['protocol'], V2)
        self.assertEqual(protocol['benchmark'], V2)
        self.assertEqual(protocol['seed'], e.STUDY_V2_SEED)
        self.assertEqual(protocol['conditions'], list(e.CONDITIONS_V2))
        self.assertEqual(protocol['planned_calls'], 18)
        self.assertEqual(protocol['trial_order'], e.study_plan_v2(['codex']))
        self.assertEqual(protocol['map_generator_sha256'],
                         hashlib.sha256(Path(repo_map.__file__).read_bytes()).hexdigest())
        for task in e.study_contracts()['tasks']:
            ident = task['id']
            self.assertEqual(protocol['references_sha256'][ident], digest(REFERENCE[task['output']]))
            for condition in e.CONDITIONS_V2:
                self.assertTrue(protocol['sufficiency'][ident][condition]['sufficient'], ident + condition)
                self.assertTrue((destination / ('prompt-%s-%s.txt' % (ident, condition))).is_file())
                self.assertIn(condition, protocol['prompt_sha256'][ident])
            self.assertEqual(protocol['mandatory_sha256'][ident]['full-source'],
                             protocol['mandatory_sha256'][ident][CLOSURE])
        self.assertFalse((destination / ('prompt-%s-selected-map.txt' % task['id'])).exists())

    def test_the_closure_prompts_on_disk_match_their_recorded_digests(self):
        destination, _ = self.run_study(protocol_version='v2')
        protocol = json.loads((destination / 'protocol.json').read_text())
        for ident, arms in protocol['prompt_sha256'].items():
            for condition, recorded in arms.items():
                text = (destination / ('prompt-%s-%s.txt' % (ident, condition))).read_text(encoding='utf-8')
                self.assertEqual(digest(text), recorded)

    def test_the_default_seed_for_v2_is_the_preregistered_one_and_can_be_overridden(self):
        destination, _ = self.run_study(protocol_version='v2')
        self.assertEqual(json.loads((destination / 'protocol.json').read_text())['seed'], 20261006)
        other, _ = self.run_study(protocol_version='v2', seed=11)
        self.assertEqual(json.loads((other / 'protocol.json').read_text())['seed'], 11)


class V2Gate(Base):
    def test_an_insufficient_reference_stops_the_study_before_any_call_or_write(self):
        references = dict(e.study_references())
        references['src/scheduler.py'] = ('from .scheduling import check_task\n\n\n'
                                          'def plan(tasks):\n    return [check_task(t)["id"] for t in tasks]\n')
        destination = self.out()
        calls = []
        with mock.patch.object(e.host, 'generate', side_effect=fake_generate(calls=calls)):
            with self.assertRaises(ValueError) as raised:
                e.collect_study(destination, ['codex'], protocol_version='v2', references=references)
        self.assertEqual(calls, [])
        self.assertFalse(destination.exists())
        self.assertIn('dependency-order', str(raised.exception))

    def test_an_undefined_imported_name_also_stops_the_study(self):
        references = dict(e.study_references())
        references['src/ledger.py'] = ('from src.money import parse_amount, not_a_real_helper\n\n\n'
                                       'def summarize(records):\n    return parse_amount(records)\n')
        destination = self.out()
        calls = []
        with mock.patch.object(e.host, 'generate', side_effect=fake_generate(calls=calls)):
            with self.assertRaises(ValueError):
                e.collect_study(destination, ['codex'], protocol_version='v2', references=references)
        self.assertEqual(calls, [])
        self.assertFalse(destination.exists())

    def test_the_same_gate_is_not_applied_to_v1(self):
        references = dict(e.study_references())
        references['src/scheduler.py'] = 'from .scheduling import check_task\n'
        destination, report = self.run_study(references=references)
        self.assertEqual(json.loads((destination / 'protocol.json').read_text())['protocol'], V1)

    def test_a_missing_reference_for_a_task_is_refused(self):
        references = dict(e.study_references())
        del references['src/paths.py']
        destination = self.out()
        with self.assertRaises(ValueError):
            e.collect_study(destination, ['codex'], protocol_version='v2', references=references)
        self.assertFalse(destination.exists())


class V2Results(Base):
    def test_every_planned_trial_is_recorded_once_with_a_v2_arm(self):
        destination, report = self.run_study(protocol_version='v2')
        rows = report['results']
        self.assertEqual(len(rows), 18)
        self.assertEqual({row['condition'] for row in rows}, set(e.CONDITIONS_V2))
        self.assertEqual({(row['task'], row['condition'], row['repeat']) for row in rows},
                         {(task['id'], condition, repeat) for task in e.study_contracts()['tasks']
                          for condition in e.CONDITIONS_V2 for repeat in (1, 2, 3)})
        saved = json.loads((destination / 'results.json').read_text())
        self.assertEqual(saved, rows)
        self.assertTrue(report['study_complete'])
        self.assertEqual(json.loads((destination / 'report.json').read_text())['protocol']['protocol'], V2)

    def test_groups_cover_only_the_v2_arms(self):
        _, report = self.run_study(protocol_version='v2')
        self.assertEqual({group['condition'] for group in report['groups']}, set(e.CONDITIONS_V2))
        self.assertEqual(len(report['groups']), 6)
        for group in report['groups']:
            self.assertEqual(group['planned'], 3)
            self.assertEqual(group['scored'], 3)
            expected = 11 / 11 if group['condition'] == 'full-source' else 6 / 11
            self.assertAlmostEqual(group['held_out_mean_pass_rate'], expected)

    def test_pairs_are_full_source_minus_closure_map_over_matched_scored_repeats(self):
        _, report = self.run_study(protocol_version='v2')
        self.assertEqual(len(report['pairs']), 3)
        for pair in report['pairs']:
            self.assertEqual(pair['paired_repeats'], 3)
            self.assertAlmostEqual(pair['held_out_pass_rate']['mean'], 1 - 6 / 11)
            self.assertAlmostEqual(pair['input_tokens']['mean'], 40)

    def test_failures_stay_in_the_denominators_and_are_never_replaced(self):
        calls = []

        def fails(host_name, arm, output):
            return arm == CLOSURE and output == 'src/paths.py'

        destination, report = self.run_study(protocol_version='v2',
                                             generate=fake_generate(fail_when=fails, calls=calls))
        self.assertEqual(len(calls), 18)
        self.assertEqual(len(report['results']), 18)
        failed = [row for row in report['results'] if row['status'] == 'failed']
        self.assertEqual(len(failed), 3)
        self.assertEqual({(row['task'], row['condition']) for row in failed},
                         {('project-path', CLOSURE)})
        self.assertFalse(report['study_complete'])
        group = next(item for item in report['groups']
                     if item['task'] == 'project-path' and item['condition'] == CLOSURE)
        self.assertEqual((group['planned'], group['scored'], group['failed']), (3, 0, 3))
        pair = next(item for item in report['pairs'] if item['task'] == 'project-path')
        self.assertEqual(pair['paired_repeats'], 0)

    def test_an_unavailable_host_is_recorded_for_every_remaining_trial(self):
        def unavailable(host_name, prompt, outputs, timeout, model, evidence=None):
            raise e.host.HostUnavailable('fake host is unavailable')

        destination, report = self.run_study(protocol_version='v2', generate=unavailable)
        self.assertEqual(len(report['results']), 18)
        self.assertEqual({row['status'] for row in report['results']}, {'host-unavailable'})
        self.assertFalse(report['study_complete'])

    def test_an_existing_output_directory_is_never_overwritten(self):
        destination = self.out()
        destination.mkdir()
        with self.assertRaises(ValueError):
            e.collect_study(destination, ['codex'], protocol_version='v2')


class V2Command(Base):
    def test_the_command_runs_v2_with_the_preregistered_seed_and_returns_zero_when_complete(self):
        destination = self.out()
        with mock.patch.object(e.host, 'generate', side_effect=fake_generate()):
            code = e.main(['--study-v2', '--output', str(destination), '--study-host', 'codex'])
        self.assertEqual(code, 0)
        protocol = json.loads((destination / 'protocol.json').read_text())
        self.assertEqual((protocol['protocol'], protocol['seed'], protocol['planned_calls']), (V2, 20261006, 18))

    def test_the_command_returns_a_failure_code_for_an_incomplete_study(self):
        destination = self.out()
        with mock.patch.object(e.host, 'generate',
                               side_effect=fake_generate(fail_when=lambda h, a, o: True)):
            code = e.main(['--study-v2', '--output', str(destination), '--study-host', 'codex'])
        self.assertEqual(code, 2)

    def test_the_v1_command_flag_still_runs_v1(self):
        destination = self.out()
        with mock.patch.object(e.host, 'generate', side_effect=fake_generate()):
            e.main(['--study', '--output', str(destination), '--study-host', 'codex'])
        self.assertEqual(json.loads((destination / 'protocol.json').read_text())['protocol'], V1)

    def test_the_two_study_flags_together_are_refused(self):
        destination = self.out()
        code = e.main(['--study', '--study-v2', '--output', str(destination), '--study-host', 'codex'])
        self.assertNotEqual(code, 0)
        self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
