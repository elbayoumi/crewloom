import importlib.util
import json
import os
import unittest
from pathlib import Path

import bilingual_evaluation as pilot
import evaluate_hosts as grading
import workflow as w

ROOT = Path(__file__).resolve().parents[1]
TASKS = json.loads((ROOT / pilot.TASKS).read_text())['tasks']


class Contracts(unittest.TestCase):
    def test_reference_matches_every_frozen_case_without_mutation(self):
        for task in TASKS:
            path = ROOT / 'examples/bilingual-evaluation/references' / Path(task['output']).name
            spec = importlib.util.spec_from_file_location(task['id'], path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            for case in task['cases']:
                value = json.loads(json.dumps(case['input']))
                try:
                    result = getattr(module, task['id'])(value)
                    envelope = {'outcome': 'value', 'value': result}
                except Exception as exc:
                    envelope = {'outcome': 'raised', 'exception': type(exc).__name__}
                self.assertTrue(grading.study_score(envelope, grading.expected_outcome(case['expected'])), case['id'])
                self.assertEqual(value, case['input'])

    def test_prompts_have_same_api_and_outputs_but_no_cases(self):
        for task in TASKS:
            for language in ('en', 'ar'):
                self.assertIn(task['output'], task['prompts'][language])
                self.assertIn('ValueError', task['prompts'][language])
                self.assertNotIn('invalid-0', task['prompts'][language])

    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS') == '1', 'requires actual Docker')
    def test_real_grader_accepts_reference_rejects_mutating_and_always_none(self):
        image = w.inspect_image(w.DEFAULT_IMAGE)
        for task in TASKS:
            source = (ROOT / 'examples/bilingual-evaluation/references' / Path(task['output']).name).read_bytes()
            for case in task['cases']:
                result = grading._grade_case(source, task, case, 0, image, 15, ROOT, (), Path(task['output']).name)
                self.assertEqual(result['passed'], 1, result)
            case = next(c for c in task['cases'] if c['id'] != 'empty' and isinstance(c['input'], (list, dict)))
            for bad in [f'def {task["id"]}(value):\n return None\n',
                        f'def {task["id"]}(value):\n value.clear()\n raise ValueError()\n']:
                result = grading._grade_case(bad.encode(), task, case, 0, image, 15, ROOT, (), Path(task['output']).name)
                self.assertEqual(result['passed'], 0, result)

    def test_telemetry_and_cross_host_metrics_recording(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'pilot-test'
            ref_quote = (ROOT / 'examples/bilingual-evaluation/references/quote.py').read_text()
            ref_reconcile = (ROOT / 'examples/bilingual-evaluation/references/reconcile.py').read_text()
            def mock_gen(h_name, prompt, outputs, timeout, model):
                out_path = outputs[0]
                text = ref_quote if 'quote.py' in out_path else ref_reconcile
                evidence = {
                    'host': h_name,
                    'duration_ms': 1500,
                    'cost_usd': 0.002,
                    'cache_efficiency': 0.4,
                    'usage_metrics': {
                        'input_tokens': 150,
                        'uncached_input_tokens': 90,
                        'cached_input_tokens': 60,
                        'cache_write_tokens': 0,
                        'output_tokens': 45,
                        'reasoning_tokens': None,
                        'total_tokens': 195,
                    }
                }
                return {out_path: text}, evidence
            with patch.object(pilot.model_host, 'generate', side_effect=mock_gen), \
                 patch.object(pilot.grading, '_grade_case', return_value={'passed': 1, 'duration_ms': 10, 'duration_ms_total': 12}):
                report = pilot.run(out, ['codex', 'claude'], timeout=60, models={'codex': 'gpt-6', 'claude': 'claude-3-5'})
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['trials']), 8)
            trial = report['trials'][0]
            self.assertEqual(trial['duration_generation_ms'], 1500)
            self.assertEqual(trial['input_tokens'], 150)
            self.assertEqual(trial['cached_input_tokens'], 60)
            self.assertEqual(trial['cache_efficiency'], 0.4)
            self.assertIn('telemetry', report)
            self.assertEqual(len(report['telemetry']), 8)
            entry = report['telemetry'][0]
            self.assertEqual(entry['planned'], 1)
            self.assertEqual(entry['scored'], 1)
            self.assertEqual(entry['failed'], 0)
            self.assertEqual(entry['pass_rate'], 1.0)
            self.assertEqual(entry['mean_duration_generation_ms'], 1500.0)
            self.assertEqual(entry['mean_input_tokens'], 150.0)
            self.assertEqual(entry['mean_cached_input_tokens'], 60.0)
            self.assertEqual(entry['cache_efficiency'], 0.4)


class UnderstandingContracts(unittest.TestCase):
    def test_grader_change_invalidates_collection_before_next_call(self):
        import tempfile
        import project_binding as pb
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            grader = root / 'grader.py'; grader.write_text('original grader')
            def generation(*args, **kwargs):
                grader.write_text('changed grader')
                return {'decision.json': '{}'}, {}
            with patch.object(pb, 'project_root', return_value=root), \
                    patch.object(pb, 'load_binding', return_value={'project_root': str(root)}), \
                    patch.object(pilot.grading, '__file__', str(grader)), \
                    patch.object(pilot.model_host, 'generate', side_effect=generation) as generate:
                with self.assertRaisesRegex(ValueError, 'frozen inputs changed'):
                    pilot.run_understanding(root, '.crewloom/private/evaluations/grader-change',
                                            ['codex'], {'codex': 'fixture-model'})
                self.assertEqual(generate.call_count, 1)
                report = json.loads((root / '.crewloom/private/evaluations/grader-change/report.json').read_text())
                self.assertIn(str(grader), report['frozen_inputs'])
                self.assertIn('invalidated', report)
                self.assertFalse(report['complete'])

    def test_input_audit_refuses_obsolete_selected_and_missing_raw_records(self):
        case = pilot.understanding_cases()[0]
        for language in ('en', 'ar'):
            raw = pilot.understanding_prompt(case, language, 'raw-history')
            selected = pilot.understanding_prompt(case, language, 'selected-context')
            with self.assertRaisesRegex(ValueError, 'required source'):
                pilot.audit_understanding_inputs(case, language, 'selected-context', raw)
            with self.assertRaisesRegex(ValueError, 'required source'):
                pilot.audit_understanding_inputs(case, language, 'raw-history', selected)

    def test_private_collector_preserves_all_trials_and_refuses_restart(self):
        import tempfile
        import project_binding as pb
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            binding = {'project_id': 'study', 'checkout_id': 'a' * 32, 'project_root': str(root)}
            answer = json.dumps(pilot.understanding_cases()[0]['expected'])
            with patch.object(pb, 'project_root', return_value=root), \
                    patch.object(pb, 'load_binding', return_value=binding), \
                    patch.object(pilot.model_host, 'generate', return_value=({'decision.json': answer}, {'synthetic': True})) as generate:
                relative = '.crewloom/private/evaluations/study'
                report = pilot.run_understanding(root, relative, ['codex'], {'codex': 'fixture-model'})
                self.assertEqual(generate.call_count, 36)
                self.assertEqual(len(report['trials']), 36)
                self.assertTrue(report['complete'])
                self.assertEqual(sum(g['planned'] for g in report['summary']), 36)
                self.assertTrue(report['coverage']['full_suite'])
                subset = pilot.run_understanding(root, relative + '-subset', ['codex'], {'codex': 'fixture-model'},
                                                 case_ids=['latest-correction'])
                self.assertEqual(len(subset['trials']), 4)
                self.assertEqual(subset['coverage']['case_ids'], ['latest-correction'])
                self.assertFalse(subset['coverage']['full_suite'])
                with self.assertRaisesRegex(ValueError, 'distinct known'):
                    pilot.run_understanding(root, relative + '-unknown', ['codex'], {'codex': 'fixture-model'},
                                            case_ids=['unknown'])
                for path in (root / relative).iterdir():
                    self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)
                with self.assertRaisesRegex(ValueError, 'overwritten'):
                    pilot.run_understanding(root, relative, ['codex'], {'codex': 'fixture-model'})
                with self.assertRaisesRegex(ValueError, 'private/evaluations'):
                    pilot.run_understanding(root, 'public', ['codex'], {'codex': 'fixture-model'})
                with self.assertRaisesRegex(ValueError, 'explicit model'):
                    pilot.run_understanding(root, relative + '-other', ['codex'], {})

    def test_private_collector_preserves_failed_and_blocked_attempts(self):
        import tempfile
        import project_binding as pb
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.object(pb, 'project_root', return_value=root), \
                    patch.object(pb, 'load_binding', return_value={'project_root': str(root)}), \
                    patch.object(pilot.model_host, 'generate', side_effect=ValueError('fixture unavailable')) as generate:
                report = pilot.run_understanding(root, '.crewloom/private/evaluations/failed',
                                                  ['codex'], {'codex': 'fixture-model'})
                self.assertEqual(generate.call_count, 2)
                self.assertEqual(len(report['trials']), 36)
                self.assertFalse(report['complete'])
                self.assertEqual([t['status'] for t in report['trials'][:3]], ['failed', 'failed', 'blocked'])

    def test_input_audit_rejects_lost_quote_and_changed_scope(self):
        case = next(c for c in pilot.understanding_cases()
                    if c['id'] == 'hypothesis-does-not-erase-quote')
        for language in ('en', 'ar'):
            prompt = pilot.understanding_prompt(case, language, 'selected-context')
            prefix, raw = prompt.split('Inputs:\n', 1)
            payload = json.loads(raw)
            payload['records'] = payload['records'][1:]
            with self.assertRaisesRegex(ValueError, 'required source'):
                pilot.audit_understanding_inputs(case, language, 'selected-context',
                                                  prefix + 'Inputs:\n' + json.dumps(payload))
            payload = json.loads(raw)
            payload['scope']['project_id'] = 'foreign'
            with self.assertRaisesRegex(ValueError, 'authoritative scope'):
                pilot.audit_understanding_inputs(case, language, 'selected-context',
                                                  prefix + 'Inputs:\n' + json.dumps(payload))

    def test_frozen_reference_and_every_single_field_mutation(self):
        for case in pilot.understanding_cases():
            expected = case['expected']
            self.assertTrue(pilot.understanding_score(expected, expected)['passed'])
            alternatives = {'project_id': 'foreign-project', 'user_id': 'foreign-user',
                            'task_id': 'foreign-task',
                            'language': 'ar' if expected['language'] != 'ar' else 'en',
                            'needs_clarification': not expected['needs_clarification'],
                            'questions': ['unexpected_field'],
                            'publication_requested': not expected['publication_requested'],
                            'verified_claims': ['tests_passed']}
            for field, replacement in alternatives.items():
                candidate = dict(expected, **{field: replacement})
                result = pilot.understanding_score(candidate, expected)
                self.assertFalse(result['passed'], (case['id'], field))
                self.assertFalse(result['fields'][field])

    def test_malformed_extra_and_boolean_coercions_never_receive_credit(self):
        expected = pilot.understanding_cases()[0]['expected']
        for candidate in [None, [], 'answer', dict(expected, rationale='trust me'),
                          dict(expected, publication_requested=0),
                          dict(expected, needs_clarification='false')]:
            result = pilot.understanding_score(candidate, expected)
            self.assertFalse(result['valid_response'])
            self.assertFalse(any(result['fields'].values()))

    def test_prompts_exclude_held_out_answers_and_preserve_scope(self):
        for case in pilot.understanding_cases():
            for language in ('en', 'ar'):
                for arm in ('raw-history', 'selected-context'):
                    prompt = pilot.understanding_prompt(case, language, arm)
                    payload = json.loads(prompt.split('Inputs:\n', 1)[1])
                    self.assertEqual(payload['scope'], case['scope'])
                    self.assertEqual(payload['current_user_request'], case['request'][language])
                    self.assertNotIn('expected', payload)
                    self.assertNotIn(json.dumps(case['expected'], ensure_ascii=False), prompt)
                    for record in payload['records']:
                        self.assertEqual(record['value'], record['source']['quote'])

    def test_selected_arm_uses_actual_task_and_user_correction_precedence(self):
        cases = {case['id']: case for case in pilot.understanding_cases()}
        chosen = {'latest-correction': 2, 'task-overrides-global': 2,
                  'other-task-is-excluded': 1, 'other-user-is-excluded': 1}
        for name, revision in chosen.items():
            for language in ('en', 'ar'):
                prompt = pilot.understanding_prompt(cases[name], language, 'selected-context')
                payload = json.loads(prompt.split('Inputs:\n', 1)[1])
                self.assertEqual([item['id'] for item in payload['records']], [revision])

    def test_fixture_change_is_refused_without_silent_refreeze(self):
        from unittest.mock import patch
        with patch.object(pilot.w, 'digest', return_value='modified'):
            with self.assertRaisesRegex(ValueError, 'explicit refreeze'):
                pilot.understanding_cases()

    def test_verification_is_offline_and_conflicting_provider_arguments_are_refused(self):
        from unittest.mock import patch
        with patch.object(pilot.model_host, 'generate', side_effect=AssertionError('provider reached')):
            self.assertEqual(pilot.main(['--verify-understanding']), 0)
            self.assertEqual(pilot.main(['--verify-understanding', '--host', 'codex']), 2)
            self.assertEqual(pilot.main([]), 2)
        report = pilot.verify_understanding()
        self.assertEqual(report['model_trials'], 0)
        self.assertFalse(report['model_improvement_measured'])
        self.assertEqual(report['fixture_sha256'], pilot.UNDERSTANDING_SHA256)


if __name__ == '__main__':
    unittest.main()
