"""Independent native acceptance contracts and exact UTF-8 context budgets."""
import json
import unittest
from unittest.mock import Mock, patch

import host_lifecycle as hl
import test_host_lifecycle as fixture


class NativeContractBoundaries(fixture.Fixture):
    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts}

    def refuse_output(self, name):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.install(outputs=(name,))
        self.assertEqual(self.snapshot(), before)

    def test_criteria_cannot_be_a_native_output(self):
        self.refuse_output(fixture.CRITERIA)

    def test_acceptance_plan_cannot_be_a_native_output(self):
        self.refuse_output(fixture.ACCEPTANCE_PLAN)

    def test_checker_cannot_be_a_native_output(self):
        self.refuse_output('tests/test_login.py')

    def mutated_contract(self, name):
        record = self.install(outputs=(fixture.SOURCE_FILE, fixture.DECLARED))
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        task_id = injected['task_id']
        if name == fixture.ACCEPTANCE_PLAN:
            plan = json.loads((self.root / name).read_text())
            plan['steps'][0]['summary'] = 'An externally changed acceptance contract'
            (self.root / name).write_text(json.dumps(plan))
        else:
            with (self.root / name).open('a') as stream:
                stream.write('\n# Externally changed after install\n')
        runner = Mock(side_effect=ValueError('The forbidden runner was reached'))
        try:
            result = hl.verify(self.root, fixture.PROJECT, record, task_id, 'Stop', runner=runner)
        except ValueError:
            result = {'verified': False}
        self.assertFalse(result.get('verified'))
        runner.assert_not_called()

    def test_changed_criteria_refuses_before_executor(self):
        self.mutated_contract(fixture.CRITERIA)

    def test_changed_plan_refuses_before_executor(self):
        self.mutated_contract(fixture.ACCEPTANCE_PLAN)

    def test_changed_checker_refuses_before_executor(self):
        self.mutated_contract('tests/test_login.py')

    def test_declared_candidate_can_change_and_reach_executor(self):
        record = self.install(outputs=(fixture.SOURCE_FILE, fixture.DECLARED))
        injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        with (self.root / fixture.SOURCE_FILE).open('a') as stream:
            stream.write('\n# A declared candidate edit\n')
        runner = Mock(side_effect=ValueError('Stop before actual Docker in this offline test'))
        hl.verify(self.root, fixture.PROJECT, record, injected['task_id'], 'Stop', runner=runner)
        runner.assert_called_once()

    def budget(self, text):
        record = self.install(acceptance=False)
        record['additional_context_limit'] = 1024
        context = {'generation': 1, 'semantic_sha256': 'f' * 64, 'criteria': ['retain acceptance'], 'rules': []}
        binding = {'checkout_id': record['checkout_id']}
        with patch.object(hl.pc, 'bodies', return_value={'src/input.py': {'text': text}}):
            result = hl.injected_context(self.root, binding, record, context)
        actual = len(result['additionalContext'].encode('utf-8'))
        self.assertLessEqual(actual, 1024)
        self.assertEqual(result['bytes'], actual)
        if result['omissions']:
            self.assertNotIn(text, result['additionalContext'])
        else:
            self.assertIn(text, result['additionalContext'])

    def test_ascii_context_accounts_for_receipt_and_separators(self):
        self.budget('x' * 290)

    def test_arabic_context_uses_utf8_bytes_without_partial_bodies(self):
        self.budget('عربي' * 80)

    def test_receipt_is_not_completion_or_executor_evidence(self):
        record = self.install(acceptance=False)
        result = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        receipt = hl.marker_text(record).lower()
        self.assertIn(record['marker'], result['additionalContext'])
        self.assertNotIn('only after', receipt)
        self.assertNotIn('when the task is complete', result['additionalContext'].lower())
        self.assertIn('receipt', receipt)
        self.assertIn('not', receipt)
        status = hl.status(self.root, fixture.PROJECT, 'codex')
        self.assertFalse(status.get('verified', False))


if __name__ == '__main__':
    unittest.main()
