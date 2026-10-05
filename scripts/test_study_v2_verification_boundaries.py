"""Independent acceptance for post-run verification and v2 limits in the study runner.

Written before the implementation and frozen: the implementer may not edit this file.

A long study reads its fixture, prompt files and grader again for every trial, so a checkout edited
or updated while it runs would leave `protocol.json` claiming digests the graded bytes no longer
match. These cases pin that every frozen input is recomputed after the last trial, that a mismatch
refuses the run without publishing `report.json`, and that a v2 record never describes the v1 arm.

Every case is offline: the provider, the image lookup and the container grader are fakes.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_hosts as e
import test_study_v2_runner_boundaries as runner

IMAGE = runner.IMAGE


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crewloom-v2-verify-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = self.root / 'fixture'
        shutil.copytree(e.study_fixture_root(), self.fixture)
        self.counter = 0
        for patcher in (mock.patch.object(e.w, 'inspect_image', return_value=IMAGE),
                        mock.patch.object(e, 'grade_study', side_effect=runner.fake_grade)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def out(self):
        self.counter += 1
        return self.root / ('out%d' % self.counter)

    def run_study(self, destination, version, after_trial=None, hosts=('codex',)):
        """Run offline; `after_trial(number)` may tamper with an input while the study runs."""
        base = runner.fake_generate()
        state = {'n': 0}

        def generate(*args, **kwargs):
            state['n'] += 1
            if after_trial:
                after_trial(state['n'])
            return base(*args, **kwargs)

        with mock.patch.object(e.host, 'generate', side_effect=generate):
            return e.collect_study(destination, list(hosts), protocol_version=version,
                                   fixture=self.fixture)


class CleanRun(Base):
    def test_a_clean_run_records_a_passing_verification_for_both_protocols(self):
        for version in ('v1', 'v2'):
            destination = self.out()
            self.run_study(destination, version, hosts=('codex',))
            verification = json.loads((destination / 'verification.json').read_text())
            self.assertIs(verification['verified'], True, version)
            self.assertEqual(verification['mismatches'], [], version)
            self.assertGreater(verification['checked'], 10, version)
            self.assertTrue((destination / 'report.json').is_file(), version)

    def test_the_verification_covers_the_fixture_prompts_helpers_and_the_harness(self):
        destination = self.out()
        self.run_study(destination, 'v2')
        verification = json.loads((destination / 'verification.json').read_text())
        names = ' '.join(verification['names'])
        for expected in ('fixture_sha256', 'helper_sha256', 'prompt_sha256', 'grader_sha256',
                         'transport_sha256', 'executor_sha256', 'image_module_sha256',
                         'map_generator_sha256', 'references_sha256'):
            self.assertIn(expected, names)


class TamperedInputs(Base):
    def assert_refused(self, version, tamper, expected):
        destination = self.out()
        with self.assertRaises(ValueError) as raised:
            self.run_study(destination, version, after_trial=lambda n: tamper(n, destination))
        self.assertIn(expected, str(raised.exception))
        self.assertFalse((destination / 'report.json').exists(), 'a refused run publishes no report')
        verification = json.loads((destination / 'verification.json').read_text())
        self.assertIs(verification['verified'], False)
        self.assertTrue(any(expected in item for item in verification['mismatches']), verification)
        results = json.loads((destination / 'results.json').read_text())
        self.assertEqual(len(results), 18 if version == 'v2' else 18)
        return destination

    def test_a_fixture_module_edited_during_the_run_refuses_the_report(self):
        def tamper(number, destination):
            if number == 5:
                path = self.fixture / 'src' / 'money.py'
                path.write_text(path.read_text() + '\n# edited during the run\n')
        self.assert_refused('v2', tamper, 'src/money.py')

    def test_a_helper_edited_during_the_run_refuses_the_report(self):
        def tamper(number, destination):
            if number == 9:
                path = self.fixture / 'src' / 'scheduling.py'
                path.write_text(path.read_text() + '\n# edited during the run\n')
        self.assert_refused('v1', tamper, 'src/scheduling.py')

    def test_a_prompt_file_edited_during_the_run_refuses_the_report(self):
        def tamper(number, destination):
            if number == 3:
                path = destination / 'prompt-dependency-order-closure-map.txt'
                path.write_text(path.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        self.assert_refused('v2', tamper, 'prompt-dependency-order-closure-map.txt')

    def test_an_added_fixture_module_refuses_the_report(self):
        def tamper(number, destination):
            if number == 2:
                (self.fixture / 'src' / 'extra_module.py').write_text('def extra():\n    return 1\n')
        self.assert_refused('v1', tamper, 'src/extra_module.py')

    def test_a_removed_fixture_module_refuses_the_report(self):
        def tamper(number, destination):
            if number == 4:
                (self.fixture / 'src' / 'telemetry.py').unlink()
        self.assert_refused('v2', tamper, 'src/telemetry.py')

    def test_every_mismatch_is_named_not_just_the_first(self):
        def tamper(number, destination):
            if number == 6:
                for name in ('money.py', 'pathutil.py'):
                    path = self.fixture / 'src' / name
                    path.write_text(path.read_text() + '\n# edited\n')
        destination = self.assert_refused('v2', tamper, 'src/money.py')
        verification = json.loads((destination / 'verification.json').read_text())
        self.assertTrue(any('src/pathutil.py' in item for item in verification['mismatches']))


class LimitsDescribeTheArm(Base):
    def test_a_v2_record_never_describes_the_selected_map_comparison(self):
        destination = self.out()
        report = self.run_study(destination, 'v2')
        protocol = json.loads((destination / 'protocol.json').read_text())
        for text in (' '.join(protocol['limits']), ' '.join(report['limits'])):
            self.assertNotIn('selected-map', text)
            self.assertNotIn('selected map', text.lower())
            self.assertIn('closure-map', text)
        self.assertEqual(protocol['limits'], report['limits'])

    def test_a_v1_record_keeps_its_exact_limits(self):
        destination = self.out()
        report = self.run_study(destination, 'v1')
        contracts = e.study_contracts()
        expected = list(e.STUDY_LIMITS) + list(contracts['quality_limits'])
        self.assertEqual(report['limits'], expected)
        self.assertEqual(json.loads((destination / 'protocol.json').read_text())['limits'], expected)

    def test_the_v2_limits_keep_every_non_comparison_caveat(self):
        v1 = set(e.STUDY_LIMITS)
        destination = self.out()
        report = self.run_study(destination, 'v2')
        kept = [item for item in e.STUDY_LIMITS if 'selected-map' not in item and 'selected map' not in item.lower()]
        self.assertGreaterEqual(len(kept), 1)
        for item in kept:
            self.assertIn(item, report['limits'])
        self.assertTrue(any('selected' in item.lower() for item in v1))


if __name__ == '__main__':
    unittest.main()
