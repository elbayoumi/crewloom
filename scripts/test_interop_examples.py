"""Adapter previews cannot masquerade as SDK or container acceptance."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from examples.interop import demo_autogen, demo_crewai, demo_langgraph, demo_runtime

DEMOS = (demo_crewai, demo_autogen, demo_langgraph)


class AdapterExampleTests(unittest.TestCase):
    def invoke(self, demo, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = demo.main(argv)
        return result, stdout.getvalue(), stderr.getvalue()

    def test_default_preview_skips_execution_even_when_docker_is_present(self):
        for demo in DEMOS:
            with self.subTest(demo=demo.__name__), mock.patch.object(demo_runtime.shutil, 'which') as which, \
                    mock.patch.object(demo_runtime.subprocess, 'run') as launch:
                result, output, errors = self.invoke(demo, [])
                self.assertEqual(result, 0, errors)
                self.assertIn('[SKIP] Container execution', output)
                self.assertIn('does not verify an installed framework SDK', output)
                self.assertNotIn('PASS', output)
                which.assert_not_called()
                launch.assert_not_called()

    def test_explicit_execution_refuses_missing_docker(self):
        for demo in DEMOS:
            with self.subTest(demo=demo.__name__), \
                    mock.patch.object(demo_runtime.shutil, 'which', return_value=None):
                result, output, errors = self.invoke(demo, ['--require-execution'])
                self.assertEqual(result, 2)
                self.assertIn('Docker is required', errors)
                self.assertNotIn('completed', output)

    def test_unavailable_daemon_and_missing_image_are_failures(self):
        for demo in DEMOS:
            for results in ([subprocess.CompletedProcess([], 1)],
                            [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1)]):
                with self.subTest(demo=demo.__name__, calls=len(results)), \
                        mock.patch.object(demo_runtime.shutil, 'which', return_value='/bin/docker'), \
                        mock.patch.object(demo_runtime.subprocess, 'run', side_effect=results):
                    result, _, errors = self.invoke(demo, ['--require-execution'])
                    self.assertEqual(result, 2)
                    self.assertIn('unavailable', errors)

    def test_execution_exit_codes_propagate_without_sdk_claims(self):
        for demo in DEMOS:
            for code in (0, 7):
                response = dict(exit_code=code, output='fixture result', timed_out=False, cancelled=False,
                                duration_ms=0, output_truncated=False, isolation='fixture', image_id=demo_runtime.IMAGE)
                with self.subTest(demo=demo.__name__, exit_code=code), \
                        mock.patch.object(demo_runtime.shutil, 'which', return_value='/bin/docker'), \
                        mock.patch.object(demo_runtime.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                        mock.patch('adapters.interop.crewai_sandbox.execute_sandbox_command', return_value=response), \
                        mock.patch('adapters.interop.autogen_sandbox.execute_sandbox_command', return_value=response), \
                        mock.patch('adapters.interop.langgraph_sandbox.execute_sandbox_command', return_value=response):
                    result, output, errors = self.invoke(demo, ['--require-execution'])
                    self.assertEqual(result, code, errors)
                    self.assertIn('no framework SDK is exercised', output)
                    self.assertNotIn('PASS', output)

    def test_previews_work_from_outside_the_checkout(self):
        with tempfile.TemporaryDirectory() as cwd:
            # A populated consumer can have an unrelated regular examples package.
            package = Path(cwd) / 'examples'
            package.mkdir()
            (package / '__init__.py').write_text("raise AssertionError('consumer examples package was imported')\n")
            for demo in DEMOS:
                result = subprocess.run([sys.executable, str(Path(demo.__file__).resolve())], cwd=cwd,
                                        capture_output=True, text=True, timeout=10, env={**os.environ, 'PYTHONPATH': cwd})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('[SKIP]', result.stdout)

    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS') == '1', 'Enable real Docker example acceptance')
    def test_explicit_examples_actually_execute_supplied_code(self):
        for demo in DEMOS:
            with self.subTest(demo=demo.__name__):
                result = subprocess.run([sys.executable, str(Path(demo.__file__).resolve()), '--require-execution'],
                                        cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                self.assertIn('no framework SDK is exercised', result.stdout)
                self.assertIn('Exit Code: 0', result.stdout)
                self.assertNotIn('[SKIP]', result.stdout)


if __name__ == '__main__':
    unittest.main()
