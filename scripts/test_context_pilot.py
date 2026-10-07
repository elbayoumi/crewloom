"""Cold/warm pilot acceptance: the report must match measured behaviour, not claims."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import context_pilot as pilot


class PilotAccountingTests(unittest.TestCase):
    """Measurements that never need the isolated executor."""

    def test_dry_run_never_claims_execution_or_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pilot.synthetic_project(Path(folder).resolve(), 5, 400)
            import project_binding as pb
            pb.bootstrap(root, 'pilot-project')
            report = pilot.measure(root, dry_run=True, project_id='pilot-project')
        self.assertTrue(report['dry_run'])
        self.assertFalse(report['acceptance']['acceptance_executed'])
        self.assertFalse(report['acceptance']['finalization_verified'])
        self.assertIn('dry run', report['acceptance_command']['reason'])
        self.assertEqual(report['finalization']['status'], 'not-finalized')
        self.assertTrue(report['acceptance']['exact_serialized_bytes'])
        self.assertEqual(report['acceptance_command']['executed'], False)
        self.assertFalse(report['provider']['usage_available'])
        self.assertEqual(report['context']['serialized_bytes'], report['context']['selected_bytes'])

    def test_real_project_options_are_required_and_nothing_is_initialized(self):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as folder:
            plain = Path(folder).resolve()
            (plain / 'module.py').write_text('def build():\n    return 1\n', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()) as captured:
                self.assertEqual(pilot.main(['--project', str(plain)]), 2)
            report = json.loads(captured.getvalue())
            self.assertEqual(report['status'], 'rejected')
            self.assertIn('already be bound', report['error'])
            self.assertFalse((plain / 'crewloom.project.json').exists())
            self.assertFalse((plain / '.crewloom').exists())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pilot.main(['--project', '/nonexistent/crewloom/pilot']), 2)

    def test_declared_acceptance_inputs_must_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pilot.synthetic_project(Path(folder).resolve(), 2, 400)
            outcome = pilot.acceptance_workflow(root, 'pilot-task', pilot.w.DEFAULT_IMAGE,
                                                ['src/login.py', 'tests/absent.py'])
        self.assertFalse(outcome['executed'])
        self.assertIn('tests/absent.py', outcome['reason'])

    def test_pilot_plan_is_private_bound_and_never_replaces_the_application_plan(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = pilot.synthetic_project(Path(folder).resolve(), 2, 400)
            existing = b'{"application": "keep this plan unchanged"}'
            (root / 'workflow.json').write_bytes(existing)
            with patch.object(pilot.w, 'run', return_value={'status': 'passed'}) as run:
                result = pilot.acceptance_workflow(root, 'pilot-task', 'fixture-image', pilot.SYNTHETIC_INPUTS)
            self.assertTrue(result['executed'])
            relative = '.crewloom/pilots/pilot-task/workflow.json'
            self.assertEqual(run.call_args.kwargs['plan_file'], relative)
            self.assertEqual((root / 'workflow.json').read_bytes(), existing)
            parsed, fingerprint = pilot.w.read_plan(root, relative)
            self.assertEqual(parsed['id'], 'pilot-task')
            self.assertTrue(fingerprint)
            for forbidden in ('.crewloom/other.json', '.git/config', '../foreign.json'):
                with self.assertRaises(ValueError):
                    pilot.w.plan_source(root, forbidden)

    def test_forced_recorded_timing_changes_measured_bytes_and_nothing_else(self):
        import copy
        import project_binding as pb
        import project_context as pc
        with tempfile.TemporaryDirectory() as folder:
            root = pilot.synthetic_project(Path(folder).resolve(), 3, 200)
            pb.bootstrap(root, 'pilot-project')
            config, _ = pb.load_config(root)
            context = pc.snapshot(root, pb.load_binding(root), 'context-pilot', pilot.ROLE,
                                  config, [], [pilot.SEED], None, [pilot.SEED],
                                  criteria_path='ACCEPTANCE.md')
        self.assertEqual(pc.payload_bytes(context), context['bytes'])
        narrow, wide = 9, 1234567
        digits = len(json.dumps(wide)) - len(json.dumps(narrow))
        self.assertEqual(digits, 6)

        def resealed(duration, mutate=None):
            forced = copy.deepcopy(context)
            forced['telemetry']['duration_ms'] = duration
            if mutate:
                mutate(forced)
            pc.seal(forced)
            return forced

        measured = {}
        for label, duration in (('narrow', narrow), ('wide', wide)):
            forced = resealed(duration)
            measured[label] = (pilot.stable_payload(forced), pc.payload_bytes(forced))
            # The resealed payload is still the exact recorded size, and every actual content
            # field survives unchanged: only the recorded timing digits moved.
            with self.subTest(label=label):
                self.assertEqual(forced['bytes'], measured[label][1])
                self.assertEqual(forced['telemetry']['duration_ms'], duration)
                self.assertEqual(forced['bodies'], context['bodies'])
                self.assertEqual(forced['rules'], context['rules'])
                self.assertEqual(forced['navigation'], context['navigation'])
                self.assertEqual(forced['criteria'], context['criteria'])
        # A timing with a different digit count moves the exact measured size by exactly its own
        # digits and is fully accounted for as volatile bytes, never padded or dropped.
        self.assertEqual(measured['wide'][1] - measured['narrow'][1], digits)
        self.assertEqual(measured['wide'][0]['volatile_bytes'] - measured['narrow'][0]['volatile_bytes'], digits)
        self.assertEqual(measured['narrow'][1] - measured['narrow'][0]['volatile_bytes'],
                         measured['wide'][1] - measured['wide'][0]['volatile_bytes'])
        # The volatile timing alone cannot change the frozen content or its semantic fingerprint.
        self.assertEqual(measured['narrow'][0]['stable_sha256'], measured['wide'][0]['stable_sha256'])
        self.assertEqual(measured['narrow'][0]['stable_semantic_sha256'],
                         measured['wide'][0]['stable_semantic_sha256'])

        def edit_body(payload):
            payload['bodies'][0]['text'] += '\nunrecorded change\n'

        def move_range(payload):
            self.assertTrue(payload['ranges'])
            payload['ranges'][0]['start'] += 1

        # Negative controls: real content changes must still be rejected after normalization.
        for name, mutate in (('body', edit_body), ('range', move_range)):
            with self.subTest(negative_control=name):
                altered = resealed(narrow, mutate)
                self.assertNotEqual(pilot.stable_payload(altered)['stable_sha256'],
                                    measured['narrow'][0]['stable_sha256'])
                self.assertEqual(altered['bytes'], pc.payload_bytes(altered))


@unittest.skipUnless(pilot.docker_available(), 'live acceptance needs a reachable Docker daemon')
class LivePilotTests(unittest.TestCase):
    def test_synthetic_sizes_are_reproducible_and_report_the_measured_crossover(self):
        reports = pilot.run_suite()
        self.assertEqual([report['label'] for report in reports], ['small', 'large'])
        for report in reports:
            with self.subTest(label=report['label']):
                self.assertEqual(sorted(name for name, ok in report['acceptance'].items() if not ok), [])
                self.assertTrue(report['seed_visible'])
                self.assertTrue(report['index']['graph_complete'])
                self.assertEqual(report['index']['cold']['parsed'], report['index']['files'])
                self.assertEqual(report['index']['warm']['parsed'], 0)
                self.assertEqual(report['index']['warm']['reused'], report['index']['files'])
                self.assertGreater(report['context']['rules_bytes'], 0)
                self.assertGreater(report['context']['declared_source_bytes'], 0)
                self.assertEqual(report['acceptance_command']['status'], 'complete')
                self.assertEqual(report['finalization']['status'], 'complete')
                self.assertTrue(report['finalization']['verified'])
                self.assertEqual(report['finalization']['verification_runs'], 1)
                self.assertFalse(report['provider']['usage_available'])
                self.assertFalse(report['provider']['cost_known'])
        small, large = reports
        self.assertTrue(large['context']['selection_wins'])
        self.assertTrue(small['context']['selection_wins'])
        self.assertLess(large['context']['selected_share_of_full_context'], 0.05)
        self.assertLess(large['context']['selected_share_of_full_context'],
                        small['context']['selected_share_of_full_context'])
        self.assertLess(large['context']['selected_bytes'], large['context']['full_context_bytes'])
        self.assertLessEqual(large['context']['map_bytes'], 8192)
        self.assertGreater(large['context']['omitted_files'], 0)

    def test_repeat_measurement_of_the_same_size_is_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            first = pilot.measure(pilot.synthetic_project(Path(folder).resolve(), 30, 400))
        with tempfile.TemporaryDirectory() as folder:
            second = pilot.measure(pilot.synthetic_project(Path(folder).resolve(), 30, 400))
        for key in ('rules_bytes', 'declared_source_bytes', 'map_bytes', 'included_files',
                    'omitted_files', 'indexed_source_bytes', 'full_context_bytes', 'generation'):
            with self.subTest(key=key):
                self.assertEqual(first['context'][key], second['context'][key])
        self.assertEqual(first['context']['omissions'], second['context']['omissions'])
        self.assertEqual(first['index']['files'], second['index']['files'])
        self.assertNotEqual(first['checkout_id'], second['checkout_id'])
        self.assertNotEqual(first['project_root'], second['project_root'])
        for report in (first, second):
            with self.subTest(project_root=report['project_root']):
                # The recorded size stays the exact serialized payload on disk.
                self.assertEqual(report['context']['selected_bytes'], report['context']['serialized_bytes'])
        # A generation records its own canonical project root, checkout ID and the measured
        # wall-clock duration of the scan, so those values legitimately differ between two
        # identical measurements. Normalize exactly them: the rest of the payload must be
        # byte-identical, and the raw size difference must be fully accounted for by the
        # volatile values rather than tolerated as slop.
        self.assertEqual(first['context']['stable_sha256'], second['context']['stable_sha256'])
        self.assertEqual(first['context']['stable_semantic_sha256'], second['context']['stable_semantic_sha256'])
        self.assertEqual(first['context']['selected_bytes'] - first['context']['volatile_bytes'],
                         second['context']['selected_bytes'] - second['context']['volatile_bytes'])
        # The two checkouts are genuinely distinct, so normalization removed real recorded
        # identity instead of hiding a payload that was already identical.
        self.assertNotEqual(first['context']['semantic_sha256'], second['context']['semantic_sha256'])

    def test_cli_pilot_writes_a_report_and_reports_missing_usage_as_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'pilot.json'
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pilot.main(['--out', str(out)]), 0)
            report = json.loads(out.read_text())
            self.assertEqual(sorted(report['crossover']), ['large', 'small'])
            self.assertTrue(all(item for measurement in report['measurements']
                                for item in measurement['acceptance'].values()))
            self.assertIn('unknown', json.dumps(report['provider']))


if __name__ == '__main__':
    unittest.main()
