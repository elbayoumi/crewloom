"""N04 execution bounds: native tool receipts, timeout/output refusals and private path guards.

Internal acceptance fixture, not a public tool. Every target is disposable; no provider is called.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import repo_map
import tempfile
import unittest
from unittest.mock import patch

import admission
import crewloom
import continuation
import workflow


@unittest.skipUnless(os.name in ('posix', 'nt'), 'no native process backend on this platform')
class ToolExecution(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crewloom-tool-execution-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.script = self.root / 'target.py'
        self.item = {'id': 'fixture-tool', 'limits': {'timeout_seconds': 2, 'output_bytes': 1024}}
        self.provenance = {'source': 'source-fixture', 'contract': 'contract-fixture', 'support': 'support-fixture'}

    def run_target(self, code):
        self.script.write_text(code)
        output = io.StringIO()
        with patch('tool_catalog.provenance', return_value=self.provenance), contextlib.redirect_stdout(output):
            status = crewloom.run_registered(self.item, self.script, [], self.root)
        receipts = list((self.root / '.crewloom' / 'tools' / self.item['id']).glob('*/execution.json'))
        self.assertEqual(len(receipts), 1)
        return status, output.getvalue(), json.loads(receipts[0].read_text())

    def test_clean_execution_has_bounded_output_current_identity_and_an_ignored_receipt(self):
        status, output, receipt = self.run_target('print("accepted")')
        self.assertEqual(status, 0)
        self.assertEqual(output.strip(), 'accepted')
        self.assertEqual(receipt['state'], 'finished')
        self.assertEqual(receipt['project_root'], str(self.root))
        self.assertEqual(receipt['source_sha256'], 'source-fixture')
        self.assertEqual(receipt['output_bytes_observed'], len(output.encode()))
        self.assertTrue(receipt['output_complete'])
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        ignored = subprocess.run(['git', 'check-ignore', '-q', '.crewloom/tools/fixture-tool'], cwd=self.root, env=repo_map.git_environment())
        self.assertEqual(ignored.returncode, 0, 'the actual Git privacy rule ignores execution receipts')
        self.assertEqual(admission.summary(next((self.root / '.crewloom' / 'tools' / self.item['id']).iterdir()))['tracked_processes'], [])

    def test_timeout_stops_the_target_and_is_not_reported_as_success(self):
        status, _, receipt = self.run_target('import time;time.sleep(120)')
        self.assertEqual(status, 124)
        self.assertEqual(receipt['reason'], 'timeout')
        self.assertFalse(receipt['output_complete'])

    def test_output_limit_is_enforced_even_when_the_target_exits_zero(self):
        status, output, receipt = self.run_target('print("x"*4096)')
        self.assertEqual(status, 2)
        self.assertLessEqual(len(output.encode()), 1024)
        self.assertEqual(receipt['reason'], 'output-limit')
        self.assertGreater(receipt['output_bytes_observed'], 1024)

    def test_required_intent_failure_cannot_launch_a_target(self):
        self.script.write_text('raise RuntimeError("must not run")')
        with patch('tool_catalog.provenance', return_value=self.provenance), \
                patch.object(continuation, '_private_write', side_effect=OSError('fixture disk failure')), \
                patch.object(admission, 'launch_owned', side_effect=AssertionError('must not launch')):
            with self.assertRaisesRegex(OSError, 'fixture disk failure'):
                crewloom.run_registered(self.item, self.script, [], self.root)

    def test_project_selectors_and_abbreviations_cannot_redirect_or_write_receipts(self):
        nested = self.root / 'other-project'; nested.mkdir()
        self.script.write_text('raise RuntimeError("must not dispatch")')
        for args in (['--project', str(nested)], ['--project-root=' + str(nested)], ['--proj', str(nested)],
                     ['--roo=../foreign'], ['--manifest', '../foreign/plan.json']):
            with self.subTest(args=args), patch.object(admission, 'launch_owned', side_effect=AssertionError('must not launch')):
                with self.assertRaises(ValueError): crewloom.run_registered(self.item, self.script, args, self.root)
        self.assertFalse((self.root / '.crewloom').exists())
        self.assertFalse((self.root / '.gitignore').exists())
        crewloom.validate_project_paths('fixture-tool', ['--project', '.', '--file', 'other-project/input.json'], self.root)

    def test_consumer_catalog_mutation_and_future_declared_paths_stay_scoped(self):
        with self.assertRaisesRegex(ValueError, 'consumer runs cannot modify'):
            crewloom.validate_project_paths('tool-catalog', ['record-evidence', 'context'], self.root)
        crewloom.validate_project_paths('tool-catalog', ['discover'], self.root)
        crewloom.validate_project_paths('tool-catalog', ['--root', '.', 'render'], self.root)
        declaration = {'--destination': {'type': 'path'}}
        with self.assertRaisesRegex(ValueError, 'escapes selected'):
            crewloom.validate_project_paths('future-tool', ['--destination', '../foreign'], self.root, declaration)
        with self.assertRaisesRegex(ValueError, 'Abbreviated'):
            crewloom.validate_project_paths('future-tool', ['--dest', 'output.json'], self.root, declaration)
        crewloom.validate_project_paths('future-tool', ['--destination', 'output.json'], self.root, declaration)

    def test_linked_runtime_cannot_write_into_another_project(self):
        other = tempfile.TemporaryDirectory(); self.addCleanup(other.cleanup)
        (self.root / '.crewloom').symlink_to(Path(other.name).resolve(), target_is_directory=True)
        with patch.object(admission, 'launch_owned', side_effect=AssertionError('must not launch')):
            with self.assertRaises(ValueError):
                crewloom.run_registered(self.item, self.script, [], self.root)
        self.assertEqual(list(Path(other.name).iterdir()), [])
        self.assertFalse((self.root / '.gitignore').exists(), 'path refusal precedes privacy writes')


if __name__ == '__main__':
    unittest.main()
