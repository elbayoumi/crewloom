"""Managed runner lifecycle: automatic enter, checkpoint, publication gate and finalization."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import crewloom
import model_host as h
import project_binding as pb
import project_context as pc
import project_lessons as pl
import repo_map
import workflow as w

ROLE = 'context-guardian'


class ManagedLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        self.installed, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'input.txt').write_text('input', encoding='utf-8')
        (self.root / 'module.py').write_text('def build():\n    return 1\n', encoding='utf-8')
        (self.root / 'criteria.md').write_text('- output.txt exists\n', encoding='utf-8')
        self.plan = {'schema_version': 1, 'id': 'managed-feature', 'criteria': 'criteria.md', 'steps': [
            {'id': 'build', 'role': ROLE, 'summary': 'Build verified output',
             'argv': ['python3', 'build.py'], 'inputs': ['input.txt'], 'outputs': ['output.txt']}]}

    def enable(self, mode='enforced'):
        config = pb.default_config('managed-project', mode)
        config['policy']['managed_lifecycle'] = True
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        return config

    def execute(self, root, argv, image, timeout, **kwargs):
        (root / 'output.txt').write_text('verified', encoding='utf-8')
        return {'exit_code': 0, 'output': '', 'image_id': image, 'duration_ms': 1}

    def run_plan(self):
        (self.root / 'workflow.json').write_text(json.dumps(self.plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        with patch.object(w, 'inspect_image', return_value='sha256:test'), \
                patch.object(w, 'docker_execute', side_effect=self.execute):
            return w.run(self.root, parsed, fingerprint, 'image')

    def test_enforced_project_runs_the_full_managed_lifecycle(self):
        self.enable('enforced')
        self.assertEqual(w.lifecycle_mode(self.root), 'enforced')
        result = self.run_plan()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['project_context']['status'], 'complete')
        self.assertEqual(result['project_context']['lifecycle'], 'managed-runner')
        self.assertTrue(result['project_context']['verified'])
        self.assertFalse(result['project_context']['host_callbacks_verified'])
        self.assertIsNone(w.active_workflow(self.root))
        self.assertIsNone(pb.reservation(self.root))
        task = pb.status(self.root, 'managed-project')['tasks'][0]
        self.assertEqual(task['task_id'], 'managed-feature')
        self.assertEqual(task['status'], 'complete')
        self.assertGreaterEqual(task['context']['generation'], 1)
        self.assertEqual(task['verification_runs'], 1)

    def test_managed_finalization_records_real_executor_evidence_only(self):
        self.enable('enforced')
        self.run_plan()
        task = pb.task_state(self.root, 'managed-feature')
        self.assertEqual(task['verification'][0]['command'], ['python3', 'build.py'])
        self.assertEqual(task['verification'][0]['exit_code'], 0)
        self.assertEqual(task['changed_files'], ['output.txt'])
        self.assertEqual(task['refresh']['navigation'], 'refreshed')
        self.assertGreater(task['refresh']['files'], 0)
        binding = pb.load_binding(self.root)
        candidate = self.lesson = pl.record(self.root, binding, 'A lesson worth verifying',
                                            'Promote only with executor evidence')['lesson']
        promoted = pl.verify(self.root, candidate['id'], [{'workflow': 'managed-feature', 'step': 'build'}])
        self.assertEqual(promoted['state'], 'verified')
        self.assertEqual(promoted['verification']['evidence'][0]['source'], 'project-executor-state')

    def test_failed_step_does_not_finalize_the_context_task_as_verified(self):
        self.enable('enforced')

        def fail(root, argv, image, timeout, **kwargs):
            return {'exit_code': 1, 'output': 'failure', 'image_id': image}

        (self.root / 'workflow.json').write_text(json.dumps(self.plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        with patch.object(w, 'inspect_image', return_value='sha256:test'), \
                patch.object(w, 'docker_execute', side_effect=fail):
            result = w.run(self.root, parsed, fingerprint, 'image')
        self.assertEqual(result['status'], 'failed')
        task = pb.status(self.root, 'managed-project')['tasks'][0]
        self.assertEqual(task['status'], 'failed')
        self.assertFalse(task['verified'])
        self.assertEqual(task['verification_runs'], 1)

    def test_checkpoint_rebuilds_the_generation_when_a_source_changes(self):
        self.enable('observe')
        self.assertEqual(self.run_plan()['status'], 'complete')
        stored = json.loads((self.root / '.crewloom' / 'context' / 'managed-feature.json').read_text())
        self.assertFalse(stored.get('invalidated'))
        self.plan['id'] = 'second-feature'
        self.plan['steps'][0]['outputs'] = ['second.txt']

        def write_second(root, argv, image, timeout, **kwargs):
            (root / 'second.txt').write_text('verified', encoding='utf-8')
            return {'exit_code': 0, 'output': '', 'image_id': image}

        (self.root / 'workflow.json').write_text(json.dumps(self.plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        binding = pb.load_binding(self.root)
        pb.enter(self.root, 'managed-project', 'second-feature', ROLE, seeds=['input.txt'],
                 sources=['input.txt'], criteria_path='criteria.md')
        fresh = pc.load(self.root, {'task_id': 'second-feature', 'project_id': binding['project_id'],
                                    'checkout_id': binding['checkout_id'], 'project_root': str(self.root)})
        (self.root / 'input.txt').write_text('changed input', encoding='utf-8')
        checkpoint = w.project_context_checkpoint(self.root, parsed, {'steps': {}}, parsed['steps'][0])
        self.assertTrue(checkpoint['stale'])
        rebuilt = pc.load(self.root, {'task_id': 'second-feature', 'project_id': binding['project_id'],
                                      'checkout_id': binding['checkout_id'], 'project_root': str(self.root)})
        self.assertGreater(rebuilt['generation'], fresh['generation'])
        self.assertIsNone(rebuilt.get('invalidated'))

    def test_publish_gate_blocks_stale_evidence_in_enforced_mode(self):
        self.enable('enforced')
        pb.enter(self.root, 'managed-project', 'model-step', ROLE, seeds=['input.txt'],
                 sources=['input.txt'], criteria_path='criteria.md')
        step = {'id': 'generate', 'role': ROLE, 'summary': 'Generate', 'kind': 'model', 'host': 'openai',
                'model': 'gpt-test', 'inputs': ['input.txt'], 'outputs': ['generated.py']}
        self.plan['id'] = 'model-step'
        self.assertIsNotNone(w.project_context_publish_gate(self.root, self.plan, step))
        (self.root / 'input.txt').write_text('changed after freeze', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'stale'):
            w.project_context_publish_gate(self.root, self.plan, step)
        self.assertIsNotNone(pb.load_binding(self.root))

    def test_checkpoint_refreshes_per_step_sources_without_any_byte_change(self):
        self.enable('observe')
        pb.enter(self.root, 'managed-project', 'refresh-feature', ROLE, seeds=['input.txt'],
                 sources=['input.txt'], criteria_path='criteria.md')
        stored = json.loads((self.root / '.crewloom' / 'context' / 'refresh-feature.json').read_text())
        self.assertEqual([item['path'] for item in stored['bodies']], ['input.txt'])
        # A later step declares a different source while every recorded byte is unchanged.
        (self.root / 'other.txt').write_text('other', encoding='utf-8')
        second = {'schema_version': 1, 'id': 'refresh-feature', 'steps': [
            {'id': 'second', 'role': ROLE, 'summary': 'Second declared source',
             'argv': ['python3', 'build.py'], 'inputs': ['other.txt'], 'outputs': ['second.txt']}]}
        self.assertEqual(w.project_context_checkpoint(self.root, second, {'steps': {}},
                                                     second['steps'][0])['stale'], True)
        refreshed = json.loads((self.root / '.crewloom' / 'context' / 'refresh-feature.json').read_text())
        self.assertEqual([item['path'] for item in refreshed['bodies']], ['other.txt'])
        self.assertGreater(refreshed['generation'], stored['generation'])
        self.assertEqual(json.loads(pc.history_path(self.root, 'refresh-feature',
                                                    stored['generation']).read_text())['semantic_sha256'],
                         stored['semantic_sha256'])

    def test_managed_prompt_carries_the_frozen_scope_and_verified_lessons(self):
        self.enable('enforced')
        self.assertEqual(self.run_plan()['status'], 'complete')
        binding = pb.load_binding(self.root)
        lesson = pl.record(self.root, binding, 'Navigation lesson for the prompt',
                           'frozen_scope_marker_in_the_prompt', conditions={'paths': ['input.txt']},
                           declared=['input.txt'])['lesson']
        pl.verify(self.root, lesson['id'], [{'workflow': 'managed-feature', 'step': 'build'}])
        pb.enter(self.root, 'managed-project', 'prompt-feature', ROLE, seeds=['input.txt'],
                 sources=['input.txt'], criteria_path='criteria.md')
        step = {'id': 'generate', 'role': ROLE, 'summary': 'Generate', 'kind': 'model', 'host': 'openai',
                'inputs': ['input.txt'], 'outputs': ['generated.py']}
        prompt = h.build_prompt(self.root, step, 'en', 'prompt-feature')
        payload = json.loads(prompt.split('\n', 1)[1])['project_context']
        self.assertEqual(payload['scope']['project_id'], binding['project_id'])
        self.assertEqual(payload['scope']['checkout_id'], binding['checkout_id'])
        frozen = pc.load(self.root, {'task_id': 'prompt-feature'})
        self.assertEqual(payload['semantic_sha256'], frozen['semantic_sha256'])
        self.assertEqual(payload['generation'], frozen['generation'])
        self.assertIn('frozen_scope_marker_in_the_prompt', prompt)
        self.assertEqual([item['remedy'] for item in payload['lessons']],
                         ['frozen_scope_marker_in_the_prompt'])
        self.assertEqual([item['path'] for item in payload['declared_sources']], ['input.txt'])
        self.assertTrue(payload['declared_sources'][0]['supplied_as_input'])
        self.assertEqual(payload['negative_evidence_count'], 0)
        with self.assertRaisesRegex(ValueError, 'carries the declared sources'):
            h.build_prompt(self.root, dict(step, inputs=['criteria.md']), 'en', 'prompt-feature')

    def test_projects_without_the_policy_keep_the_managed_runner_unchanged(self):
        self.assertIsNone(w.lifecycle_mode(self.root))
        result = self.run_plan()
        self.assertEqual(result['status'], 'complete')
        self.assertIsNone(result['project_context'])
        self.assertFalse((self.root / pb.CONFIG_NAME).exists())

    def test_managed_lifecycle_refuses_a_second_task_and_cancels_cleanly(self):
        self.enable('observe')
        self.plan['steps'][0]['kind'] = 'task'
        self.plan['steps'][0].pop('argv')
        (self.root / 'workflow.json').write_text(json.dumps(self.plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        self.assertEqual(w.run(self.root, parsed, fingerprint, 'image')['status'], 'awaiting_task')
        with self.assertRaisesRegex(ValueError, 'unfinished managed workflow|already has an active context task'):
            pb.enter(self.root, 'managed-project', 'other-task', ROLE, seeds=['input.txt'])
        self.assertEqual(w.cancel(self.root, parsed, fingerprint)['status'], 'cancelled')
        self.assertEqual(pb.status(self.root, 'managed-project')['tasks'][0]['status'], 'cancelled')

    def test_enforced_lifecycle_failure_blocks_the_run_result(self):
        self.enable('enforced')
        (self.root / 'workflow.json').write_text(json.dumps(self.plan), encoding='utf-8')
        parsed, fingerprint = w.read_plan(self.root, 'workflow.json')
        with patch.object(w, 'inspect_image', return_value='sha256:test'), \
                patch.object(w, 'docker_execute', side_effect=self.execute), \
                patch.object(w, 'project_context_finish', return_value='context finalization refused'):
            with self.assertRaisesRegex(ValueError, 'context finalization refused'):
                w.run(self.root, parsed, fingerprint, 'image')

    def interrupt(self, relative, original, applied):
        """Leave one interrupted publication exactly as a killed writer would."""
        import execution_policy as broker
        (self.root / relative).write_bytes(original)
        folder = broker._internal(self.root, 'pending', '0000000000001-killed')
        (folder / broker.BACKUP).mkdir(parents=True); (folder / broker.PAYLOAD).mkdir()
        (folder / broker.BACKUP / '0.bin').write_bytes(original)
        (folder / broker.PAYLOAD / '0.bin').write_bytes(applied)
        broker._write_record(folder / 'journal.json', {
            'schema_version': broker.JOURNAL_VERSION, 'transaction': '0000000000001-killed',
            'project_root': str(self.root), 'created_at': '2026-01-01T00:00:00Z', 'state': 'prepared',
            'inputs': {}, 'created_parents': [],
            'entries': [{'index': 0, 'path': relative, 'state': 'replacing', 'existed': True,
                         'mode': 0o644, 'bytes': len(applied), 'original_sha256': w.digest(original),
                         'new_sha256': w.digest(applied)}]})
        (self.root / relative).write_bytes(applied)
        return folder

    def test_an_interrupted_publication_is_reconciled_before_context_entry_freezes(self):
        self.enable('enforced')
        self.interrupt('output.txt', b'original output\n', b'half published\n')
        result = pb.enter(self.root, 'managed-project', 'recovered-feature', ROLE,
                          seeds=['input.txt'], sources=['input.txt'], criteria_path='criteria.md')
        self.assertEqual(result['recovered_publications'][0]['restored'], ['output.txt'])
        self.assertEqual((self.root / 'output.txt').read_bytes(), b'original output\n')
        self.assertFalse((self.root / '.crewloom' / 'transactions' / 'pending' /
                          '0000000000001-killed').exists())
        stored = pc.load(self.root, {'task_id': 'recovered-feature'})
        self.assertEqual([item['path'] for item in stored['bodies']], ['input.txt'])

    def test_a_foreign_edit_blocks_entry_before_any_context_is_written(self):
        self.enable('enforced')
        self.interrupt('output.txt', b'original output\n', b'half published\n')
        (self.root / 'output.txt').write_bytes(b'an independent user edit\n')
        with self.assertRaisesRegex(ValueError, 'Ambiguous interrupted publication'):
            pb.enter(self.root, 'managed-project', 'blocked-feature', ROLE,
                     seeds=['input.txt'], sources=['input.txt'], criteria_path='criteria.md')
        self.assertEqual((self.root / 'output.txt').read_bytes(), b'an independent user edit\n')
        self.assertIsNone(pb.task_state(self.root, 'blocked-feature'))
        self.assertIsNone(pb.reservation(self.root))
        self.assertFalse((self.root / '.crewloom' / 'context' / 'blocked-feature.json').exists())
        self.assertTrue((self.root / '.crewloom' / 'transactions' / 'pending' /
                         '0000000000001-killed').is_dir())

    def test_a_managed_run_reconciles_an_interrupted_publication_before_reserving(self):
        self.enable('observe')
        self.interrupt('output.txt', b'original output\n', b'half published\n')
        self.assertEqual(self.run_plan()['status'], 'complete')
        self.assertEqual((self.root / 'output.txt').read_text(), 'verified')
        self.assertEqual(json.loads((self.root / '.crewloom' / 'transactions' / 'receipts' /
                                     (sorted(item.name for item in (self.root / '.crewloom' /
                                      'transactions' / 'receipts').iterdir())[0])).read_text())['state'],
                         'committed')


if __name__ == '__main__':
    unittest.main()