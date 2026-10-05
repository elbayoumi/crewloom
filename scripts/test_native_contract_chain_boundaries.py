"""Acceptance authority cannot be laundered through source classification or prior steps."""
import json
from unittest.mock import Mock
import unittest

import host_lifecycle as hl
import test_host_lifecycle as fixture


class NativeContractChainBoundaries(fixture.Fixture):
    def early_checker(self):
        (self.root / 'tools').mkdir()
        (self.root / 'tools/early_checker.py').write_text('raise SystemExit(1)\n')
        path = self.root / fixture.ACCEPTANCE_PLAN
        plan = json.loads(path.read_text())
        plan['steps'].insert(0, {'id': 'early', 'role': fixture.ROLE,
            'summary': 'Earlier acceptance must also remain trusted',
            'argv': ['python3', 'tools/early_checker.py'], 'timeout_seconds': 10,
            'inputs': ['tools/early_checker.py', fixture.SOURCE_FILE],
            'outputs': ['out/early.json']})
        path.write_text(json.dumps(plan))

    def test_criteria_stays_authority_even_if_listed_as_a_source(self):
        with self.assertRaises(ValueError):
            hl.install(self.root, fixture.PROJECT, 'codex', fixture.ROLE,
                criteria_path=fixture.CRITERIA,
                seeds=[fixture.SOURCE_FILE, fixture.CRITERIA],
                sources=[fixture.SOURCE_FILE, fixture.CRITERIA],
                declared_outputs=[fixture.CRITERIA],
                acceptance={'workflow': fixture.ACCEPTANCE_PLAN, 'step': 'acceptance'})

    def test_prior_step_checker_cannot_be_an_output(self):
        self.early_checker()
        with self.assertRaises(ValueError):
            self.install(outputs=('tools/early_checker.py',))

    def test_prior_step_checker_drift_refuses_before_executor(self):
        self.early_checker()
        record = self.install(outputs=(fixture.SOURCE_FILE, fixture.DECLARED))
        result = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        (self.root / 'tools/early_checker.py').write_text('raise SystemExit(0)\n')
        runner = Mock(side_effect=ValueError('Untrusted prior checker reached executor'))
        try:
            result = hl.verify(self.root, fixture.PROJECT, record, result['task_id'], 'Stop', runner=runner)
        except ValueError:
            result = {'verified': False}
        self.assertFalse(result.get('verified'))
        runner.assert_not_called()


if __name__ == '__main__':
    unittest.main()
