"""Evidence-linked lessons: executor-gated promotion, negative evidence, provenance and isolation."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import crewloom
import execution_policy
import project_binding as pb
import project_lessons as pl
import repo_map
import workflow as w

ROLE = 'context-guardian'


class LessonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        self.installed, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'input.txt').write_text('input', encoding='utf-8')
        self.binding = pb.enter(self.root, 'sample-project', 'evidence-task', ROLE, seeds=['input.txt'])['project_id']
        self.binding = pb.load_binding(self.root)

    def run_workflow(self, name='evidence-flow', exit_code=0):
        plan = {'schema_version': 1, 'id': name, 'steps': [
            {'id': 'check', 'role': ROLE, 'summary': 'Run the acceptance check',
             'argv': ['python3', 'build.py'],
             'inputs': ['input.txt'], 'outputs': ['output.txt']}]}
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')

        def execute(root, step, image_id, timeout):
            if not exit_code:
                (root / 'output.txt').write_text('verified', encoding='utf-8')
            return {'exit_code': exit_code, 'output': '', 'image_id': image_id, 'duration_ms': 1}

        with patch.object(w, 'inspect_image', return_value='sha256:test'), \
                patch.object(execution_policy, 'execute', side_effect=execute):
            result = w.run(self.root, parsed, fingerprint, 'image')
        return parsed, fingerprint, result

    def lesson(self, issue='Map cache identity must be checked', remedy='Compare project and checkout IDs',
               conditions=None):
        return pl.record(self.root, self.binding, issue, remedy, conditions)['lesson']

    def test_new_lessons_are_candidates_without_objective_evidence(self):
        value = self.lesson()
        self.assertEqual(value['state'], 'candidate')
        self.assertFalse(value['verification']['executed'])
        self.assertEqual(value['command_execution'].split(';')[0], 'never-automatic')

    def test_forged_success_claims_cannot_verify_a_lesson(self):
        value = self.lesson()
        forged = [{'command': ['python3', '-c', 'raise RuntimeError()'], 'exit_code': 0, 'executed': True,
                   'scope': 'claimed success'}]
        with self.assertRaisesRegex(ValueError, 'workflow identifier'):
            pl.verify(self.root, value['id'], forged)
        self.assertEqual(pl.read(self.root, value['id'])['state'], 'candidate')
        with self.assertRaisesRegex(ValueError, 'unverified claims'):
            pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check', 'exit_code': 0,
                                                'executed': True}])
        self.assertEqual(pl.read(self.root, value['id'])['state'], 'candidate')
        with self.assertRaisesRegex(ValueError, 'No executor evidence recorded'):
            pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])

    def test_real_executor_evidence_promotes_with_scope_and_fingerprints(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        plan, fingerprint, result = self.run_workflow()
        self.assertEqual(result['status'], 'complete')
        value = self.lesson()
        promoted = pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check',
                                                       'scope': 'output.txt content'}])
        self.assertEqual(promoted['state'], 'verified')
        evidence = promoted['verification']['evidence'][0]
        self.assertEqual(evidence['source'], 'project-executor-state')
        self.assertEqual(evidence['exit_code'], 0)
        self.assertEqual(evidence['scope'], 'output.txt content')
        self.assertIn('output.txt', evidence['outputs'])
        self.assertTrue(evidence['attempt_signature'])
        self.assertIn('tested scope only', promoted['verification']['proves'])

    def test_failed_executor_evidence_keeps_the_lesson_a_candidate_with_negative_evidence(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow(exit_code=1)
        value = self.lesson()
        outcome = pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        self.assertEqual(outcome['state'], 'candidate')
        self.assertTrue(outcome['negative'])
        self.assertTrue(outcome['attempts'])
        selection = pl.select(self.root, ['auth.py'], set(), 10)
        self.assertEqual(selection['lessons'], [])
        self.assertEqual(selection['negative_evidence_count'], 1)

    def test_incomplete_or_foreign_evidence_is_refused(self):
        value = self.lesson()
        cases = [
            ([], 'at least one executor evidence reference'),
            ([{'workflow': 'missing-flow', 'step': 'check'}], 'No executor evidence recorded'),
            ([{'workflow': 'Bad Name', 'step': 'check'}], 'lowercase'),
            ([{'workflow': 'evidence-flow', 'step': 'unknown'}], 'No executor evidence recorded'),
        ]
        for references, message in cases:
            with self.subTest(references=references):
                with self.assertRaises(ValueError) as error:
                    pl.verify(self.root, value['id'], references)
                self.assertTrue(str(error.exception))
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder).resolve() / 'other'
            other.mkdir()
            import shutil
            shutil.copytree(self.root / '.agents', other / '.agents')
            subprocess.run(['git', 'init', '-q'], cwd=other, check=True, env=repo_map.git_environment())
            with self.assertRaisesRegex(ValueError, 'another project root'):
                pl.record(other, pb.load_binding(self.root), 'x', 'y')

    def test_external_attestations_stay_candidates(self):
        value = self.lesson()
        attested = pl.attach_external_attestation(self.root, value['id'],
                                                  {'source': 'client-owner', 'claim': 'reviewed and accepted'})
        self.assertEqual(attested['state'], 'candidate')
        self.assertIn('none; review required', attested['attestations'][0]['state_effect'])

    def test_deduplication_preserves_provenance_without_a_second_record(self):
        first = self.lesson()
        second = pl.record(self.root, self.binding, 'Map cache identity must be checked',
                           'Compare project and checkout IDs')['lesson']
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(len(pl.all_lessons(self.root)), 1)
        self.assertEqual(len(second['provenance']['observations']), 2)
        other = self.lesson('Different issue entirely', 'Other remedy')
        self.assertNotEqual(other['id'], first['id'])
        self.assertEqual(len(pl.all_lessons(self.root)), 2)

    def test_changed_policy_invalidates_a_verified_lesson(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow()
        value = self.lesson()
        pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        config = json.loads((self.root / pb.CONFIG_NAME).read_text())
        config['budgets']['map_bytes'] = 4096
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        outcome = pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        self.assertEqual(outcome['state'], 'invalidated')
        self.assertIn('policy configuration changed', outcome['provenance']['invalidations'][0]['reason'])
        self.assertEqual(pl.revalidate(self.root, 'f' * 64), [])

    def test_supersede_and_condition_matching(self):
        value = self.lesson('Cache reuse hides a renamed file', 'Re-hash after every change',
                            {'paths': ['auth.py']})
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow()
        pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        replacement = self.lesson('Replacement lesson', 'New remedy')
        superseded = pl.supersede(self.root, value['id'], replacement['id'], 'fixed by the new adapter')
        self.assertEqual(superseded['state'], 'superseded')
        self.assertEqual(superseded['superseded_by'], replacement['id'])
        matching = pl.select(self.root, ['auth.py'], set(), 10)
        self.assertEqual([item['id'] for item in matching['lessons']], [])
        other = self.lesson('Rename handling lesson', 'Detect renames with Git',
                            {'paths': ['session.py']})
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        with self.assertRaises(ValueError):
            pl.verify(self.root, other['id'], [{'workflow': 'evidence-flow', 'step': 'unknown'}])
        selected = pl.select(self.root, ['session.py'], set(), 10)
        self.assertEqual(selected['lessons'], [])

    def test_export_requires_review_and_import_verifies_identity(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow()
        value = self.lesson()
        pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        candidate = self.lesson('Another observation', 'Another remedy')
        with tempfile.TemporaryDirectory() as folder:
            packet = Path(folder) / 'lessons.json'
            with self.assertRaisesRegex(ValueError, 'Only verified lessons'):
                pl.export_reviewed(self.root, str(packet), [candidate['id']], 'owner')
            written = pl.export_reviewed(self.root, str(packet), [value['id']], 'owner')
            self.assertEqual(written, str(packet.resolve()))
            with self.assertRaisesRegex(ValueError, 'packets belong outside runtime state'):
                pl.export_reviewed(self.root, str(self.root / '.crewloom' / 'lessons.json'), [value['id']], 'owner')
            with tempfile.TemporaryDirectory() as other:
                twin = Path(other).resolve() / 'twin'
                twin.mkdir()
                import shutil
                shutil.copytree(self.root / '.agents', twin / '.agents')
                subprocess.run(['git', 'init', '-q'], cwd=twin, check=True, env=repo_map.git_environment())
                (twin / 'input.txt').write_text('input', encoding='utf-8')
                pb.enter(twin, 'twin-project', 'twin-task', ROLE, seeds=['input.txt'])
                twin_binding = pb.load_binding(twin)
                with self.assertRaisesRegex(ValueError, 'another project'):
                    pl.import_reviewed(twin, str(packet), twin_binding)
                imported = pl.import_reviewed(self.root, str(packet), self.binding)
                self.assertEqual(len(imported), 1)
                self.assertEqual(pl.read(self.root, imported[0])['state'], 'candidate')
                self.assertFalse(pl.read(self.root, imported[0])['verification']['executed'])

    def test_evidence_is_rehashed_and_a_stale_input_invalidates_reuse(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow()
        (self.root / 'input.txt').write_text('changed after the recorded run', encoding='utf-8')
        value = self.lesson()
        outcome = pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        self.assertEqual(outcome['state'], 'candidate')
        self.assertTrue(outcome['negative'])
        evidence = outcome['verification']['evidence'][0]
        self.assertFalse(evidence['passed'])
        self.assertEqual(evidence['consumed_inputs_changed']['input.txt'], 'changed-since-execution')
        self.assertIn('inputs changed or vanished', evidence['failure_reason'])

    def test_changed_output_artifact_invalidates_recorded_evidence(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow()
        (self.root / 'output.txt').write_text('rewritten after the fact', encoding='utf-8')
        value = self.lesson()
        outcome = pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        self.assertEqual(outcome['state'], 'candidate')
        self.assertIn('output.txt', outcome['verification']['evidence'][0]['failure_reason'])

    def test_in_place_input_and_output_stay_valid_evidence(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        plan = {'schema_version': 1, 'id': 'inplace-flow', 'steps': [
            {'id': 'rewrite', 'role': ROLE, 'summary': 'Rewrite the report in place',
             'argv': ['python3', 'build.py'], 'inputs': ['report.txt'], 'outputs': ['report.txt']}]}
        (self.root / 'report.txt').write_text('draft', encoding='utf-8')
        (self.root / 'workflow.json').write_text(json.dumps(plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')

        def execute(root, step, image_id, timeout):
            (root / 'report.txt').write_text('final', encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image_id, 'duration_ms': 1}

        with patch.object(w, 'inspect_image', return_value='sha256:test'), \
                patch.object(execution_policy, 'execute', side_effect=execute):
            self.assertEqual(w.run(self.root, parsed, fingerprint, 'image')['status'], 'complete')
        value = self.lesson('In-place artifacts are legitimate', 'Re-hash the written file')
        promoted = pl.verify(self.root, value['id'], [{'workflow': 'inplace-flow', 'step': 'rewrite'}])
        self.assertEqual(promoted['state'], 'verified')
        evidence = promoted['verification']['evidence'][0]
        self.assertEqual(evidence['consumed_inputs_changed'], {})
        self.assertEqual(evidence['observed_output_sha256']['report.txt'],
                         w.digest((self.root / 'report.txt').read_bytes()))

    def test_failed_verification_then_a_passing_one_is_retrievable_again(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow(exit_code=1)
        value = self.lesson('Retry after a real fix', 'Run the acceptance check again',
                            {'paths': ['input.txt']})
        failed = pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        self.assertEqual(failed['state'], 'candidate')
        self.assertTrue(failed['negative'])
        self.assertEqual(pl.select(self.root, ['input.txt'], set(), 5)['lessons'], [])
        state = json.loads((self.root / '.crewloom' / 'workflows' / 'evidence-flow' / 'state.json').read_text())
        state['steps']['check']['status'] = 'complete'
        state['steps']['check']['outputs'] = {'output.txt': w.digest((self.root / 'output.txt').read_bytes())
                                              if (self.root / 'output.txt').is_file() else 'f' * 64}
        (self.root / 'output.txt').write_text('verified', encoding='utf-8')
        state['steps']['check']['outputs'] = {'output.txt': w.digest((self.root / 'output.txt').read_bytes())}
        state['steps']['check']['attempts'].append(
            {'status': 'finished', 'exit_code': 0, 'signature': 'a' * 64})
        (self.root / '.crewloom' / 'workflows' / 'evidence-flow' / 'state.json').write_text(
            json.dumps(state), encoding='utf-8')
        ledger = json.loads((self.root / '.crewloom' / 'attempts.json').read_text())
        ledger['attempts'].append({'signature': 'a' * 64, 'status': 'succeeded',
                                   'workflow': 'evidence-flow', 'step': 'check'})
        (self.root / '.crewloom' / 'attempts.json').write_text(json.dumps(ledger), encoding='utf-8')
        recovered = pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        self.assertEqual(recovered['state'], 'verified')
        self.assertFalse(recovered['negative'])
        self.assertTrue(recovered['negative_history'])
        chosen = pl.select(self.root, ['input.txt'], set(), 5)
        self.assertEqual([item['id'] for item in chosen['lessons']], [value['id']])
        self.assertEqual(chosen['negative_evidence_count'], 0)

    def test_changed_source_invalidates_a_verified_lesson_on_revalidation(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow()
        value = self.lesson('Declared source changed', 'Re-hash before reuse')
        pl.verify(self.root, value['id'], [{'workflow': 'evidence-flow', 'step': 'check'}])
        self.assertEqual(pl.revalidate(self.root), [])
        (self.root / 'input.txt').write_text('a different input', encoding='utf-8')
        self.assertEqual(pl.revalidate(self.root), [value['id']])
        self.assertEqual(pl.read(self.root, value['id'])['state'], 'invalidated')
        self.assertIn('verified input changed', pl.read(self.root, value['id'])
                      ['provenance']['invalidations'][0]['reason'])

    def test_zero_exit_failed_artifact_record_is_never_a_pass(self):
        value = self.lesson('Zero exit is not acceptance', 'Require a complete validated step')
        folder = self.root / '.crewloom' / 'workflows' / 'zeroexit'
        folder.mkdir(parents=True)
        (folder / 'state.json').write_text(json.dumps({
            'schema_version': 1, 'project_root': str(self.root), 'workflow': 'zeroexit',
            'plan_sha256': 'a' * 64, 'project_id': self.binding['project_id'],
            'checkout_id': self.binding['checkout_id'], 'status': 'failed',
            'steps': {'check': {'kind': 'command', 'role': ROLE, 'argv': ['python3', 'build.py'],
                                'status': 'failed', 'attempts': [{'status': 'finished', 'exit_code': 0,
                                                                  'signature': 'b' * 64}],
                                'inputs': {'input.txt': w.digest((self.root / 'input.txt').read_bytes())},
                                'outputs': {}}}}), encoding='utf-8')
        (self.root / '.crewloom' / 'attempts.json').write_text(json.dumps(
            {'attempts': [{'signature': 'b' * 64, 'status': 'failed', 'workflow': 'zeroexit',
                           'step': 'check'}]}), encoding='utf-8')
        outcome = pl.verify(self.root, value['id'], [{'workflow': 'zeroexit', 'step': 'check'}])
        self.assertEqual(outcome['state'], 'candidate')
        self.assertTrue(outcome['negative'])
        evidence = outcome['verification']['evidence'][0]
        self.assertEqual(evidence['exit_code'], 0)
        self.assertFalse(evidence['passed'])
        self.assertIn('no complete step', evidence['failure_reason'])
        self.assertEqual(pl.select(self.root, ['input.txt'], set(), 5)['lessons'], [])

    def test_provider_generation_is_not_an_acceptance_check(self):
        value = self.lesson('Model output is not acceptance', 'Execute a real command instead')
        folder = self.root / '.crewloom' / 'workflows' / 'modelstep'
        folder.mkdir(parents=True)
        (self.root / 'generated.py').write_text('def generated():\n    return 1\n', encoding='utf-8')
        (folder / 'state.json').write_text(json.dumps({
            'schema_version': 1, 'project_root': str(self.root), 'workflow': 'modelstep',
            'plan_sha256': 'c' * 64, 'project_id': self.binding['project_id'],
            'checkout_id': self.binding['checkout_id'], 'status': 'complete',
            'steps': {'write': {'kind': 'model', 'role': ROLE, 'host': 'openai',
                                'argv': ['python3', 'build.py'], 'status': 'complete',
                                'attempts': [{'status': 'finished', 'exit_code': 0,
                                              'signature': 'c' * 64}],
                                'inputs': {}, 'outputs': {}}}}), encoding='utf-8')
        (self.root / '.crewloom' / 'attempts.json').write_text(json.dumps(
            {'attempts': [{'signature': 'c' * 64, 'status': 'succeeded', 'workflow': 'modelstep',
                           'step': 'write', 'kind': 'model'}]}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'command step, not a task or model step'):
            pl.verify(self.root, value['id'], [{'workflow': 'modelstep', 'step': 'write'}])
        self.assertEqual(pl.read(self.root, value['id'])['state'], 'candidate')

    def test_lesson_stored_commands_are_never_executed(self):
        value = self.lesson('A command that would destroy the checkout', 'rm -rf /')
        self.assertEqual(value['command_execution'], 'never-automatic; lesson commands are references for a human operator')
        self.assertTrue(self.root.is_dir())
        self.assertTrue((self.root / 'input.txt').is_file())

    def test_finalization_records_candidates_and_never_promotes_them(self):
        result = pb.finish(self.root, 'sample-project', 'evidence-task', ['input.txt'],
                           [{'command': ['python3', '-m', 'unittest'], 'exit_code': 0, 'scope': 'unit tests'}],
                           lessons=[{'issue': 'Lesson from finalization', 'remedy': 'Review the evidence'}])
        # An operator attestation is never executed evidence, so the task stays open.
        self.assertEqual(result['status'], 'awaiting_verification')
        self.assertFalse(result['verified'])
        self.assertEqual(result['lessons'][0]['state'], 'candidate')
        self.assertFalse(result['lessons'][0]['verified'])
        self.assertIn('executor evidence', result['lessons'][0]['promotion_requires'])
        self.assertEqual(len(result['attestations']), 1)
        self.assertFalse(result['attestations'][0]['executed'])
        self.assertIsNotNone(pb.reservation(self.root))

    def test_finalization_without_or_with_failing_checks_is_not_success(self):
        awaiting = pb.finish(self.root, 'sample-project', 'evidence-task')
        self.assertEqual(awaiting['status'], 'awaiting_verification')
        self.assertFalse(awaiting['verified'])
        self.assertIsNotNone(pb.reservation(self.root))
        failed = pb.finish(self.root, 'sample-project', 'evidence-task',
                           verification=[{'command': ['python3', '-m', 'unittest'], 'exit_code': 1,
                                          'scope': 'unit tests'}])
        self.assertEqual(failed['status'], 'failed')
        self.assertFalse(failed['verified'])
        self.assertEqual(failed['failed_commands'], [['python3', '-m', 'unittest']])
        self.assertIsNone(pb.reservation(self.root))
        again = pb.finish(self.root, 'sample-project', 'evidence-task',
                          verification=[{'command': ['python3', '-m', 'unittest'], 'exit_code': 0,
                                         'scope': 'unit tests'}])
        self.assertEqual(again['status'], 'failed')
        self.assertFalse(again['relabelled'])
        self.assertTrue(again['idempotent'])
        self.assertEqual(len(pb.status(self.root)['tasks']), 1)

    def test_completed_task_reentry_keeps_evidence_and_reservation_state(self):
        pb.cancel(self.root, 'sample-project', 'evidence-task', 'fixture')
        self.run_workflow()
        pb.enter(self.root, 'sample-project', 'evidence-task', ROLE, seeds=['input.txt'])
        report = pb.finish(self.root, 'sample-project', 'evidence-task', ['input.txt'], [],
                           evidence=[{'workflow': 'evidence-flow', 'step': 'check',
                                      'scope': 'output.txt content'}])
        self.assertEqual(report['status'], 'complete')
        self.assertTrue(report['verified'])
        frozen = (self.root / '.crewloom' / 'context' / 'evidence-task.json').read_text()
        again = pb.enter(self.root, 'sample-project', 'evidence-task', ROLE, seeds=['input.txt'])
        self.assertTrue(again['reentered_complete'])
        self.assertEqual(again['status'], 'complete')
        self.assertTrue(again['verified'])
        self.assertIsNone(pb.reservation(self.root))
        self.assertEqual((self.root / '.crewloom' / 'context' / 'evidence-task.json').read_text(), frozen)

    def test_interrupted_task_is_marked_and_reconciled_on_next_entry(self):
        state = pb.task_state(self.root, 'evidence-task')
        state['status'] = 'active'
        pb.save_task_state(self.root, state)
        (self.root / pb.RESERVATION_RELATIVE).unlink()
        recovered = pb.enter(self.root, 'sample-project', 'next-task', ROLE, seeds=['input.txt'])
        self.assertEqual(recovered['interrupted_tasks'], ['evidence-task'])
        self.assertEqual(pb.status(self.root)['tasks'][0]['status'], 'interrupted')

    def test_cli_records_and_lists_lessons(self):
        import contextlib
        import io
        from project_lessons import main as lesson_main
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        code = lesson_main(['record', '--project', str(self.root), '--issue', 'CLI lesson',
                            '--remedy', 'CLI remedy', '--task-id', 'evidence-task'])
        self.assertEqual(code, 0)
        result_id = self.lesson('CLI lesson', 'CLI remedy')['id']
        listing = lesson_main(['list', '--project', str(self.root)])
        self.assertEqual(listing, 0)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            lesson_main(['verify', '--project', str(self.root),
                         '--evidence', json.dumps([{'command': ['python3'], 'exit_code': 0}])])
        forged = lesson_main(['verify', '--project', str(self.root), '--lesson-id', result_id,
                              '--evidence', json.dumps([{'command': ['python3'], 'exit_code': 0}])])
        self.assertEqual(forged, 2)


if __name__ == '__main__':
    unittest.main()