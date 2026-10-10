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


if __name__ == '__main__':
    unittest.main()
