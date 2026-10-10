"""Real process contention and queue isolation regressions; no provider calls."""
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import project_binding as pb
import task_queue as queue
import usage_budget as budget
from test_task_coordinator import CoordinatorFixture, ModelWorkflowFixture, _stand_in_provider
import model_host
import task_coordinator as tc
import workflow as w


class SharedAdmission(CoordinatorFixture):
    def setup_controls(self):
        self.manifest = 'coordinator.json'
        self.controls = tempfile.TemporaryDirectory(prefix='crewloom-controls-')
        self.addCleanup(self.controls.cleanup)
        self.folder = Path(self.controls.name).resolve()
        self.budget = self.folder / 'budget'
        self.queue = self.folder / 'queue'
        self.catalog = self.folder / 'catalog.json'
        binding = pb.load_binding(self.root)
        self.identity = {'project_root': str(self.root), 'project_id': binding['project_id'],
                         'checkout_id': binding['checkout_id'], 'workflow': 'fixture', 'step': 'model'}
        pb.catalog_update(self.catalog, 'add', self.root, binding['project_id'])

    def test_process_contention_admits_exactly_limit(self):
        self.setup_controls()
        budget.configure(self.budget, 3, 3, 1)
        code = "import json,sys,usage_budget as b; b.reserve(sys.argv[1],json.loads(sys.argv[2]))"
        def call(_):
            return subprocess.run([sys.executable, '-c', code, str(self.budget), json.dumps(self.identity)],
                                  cwd=Path(__file__).parent, capture_output=True).returncode
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(call, range(8)))
        self.assertEqual(results.count(0), 3)
        self.assertEqual(budget.summary(self.budget)['unknown_cost_calls'], 3)

    def test_unknown_failure_retains_dollar_allowance(self):
        self.setup_controls(); budget.configure(self.budget, 10, 1, 1)
        ident = budget.reserve(self.budget, self.identity)
        budget.settle(self.budget, ident)
        with self.assertRaisesRegex(ValueError, 'dollar'):
            budget.reserve(self.budget, self.identity)
        with self.assertRaises(ValueError): budget.settle(self.budget, ident, 0)

    def test_known_zero_releases_dollars_but_keeps_request(self):
        self.setup_controls(); budget.configure(self.budget, 2, 1, 1)
        ident = budget.reserve(self.budget, self.identity); budget.settle(self.budget, ident, 0)
        budget.reserve(self.budget, self.identity)
        self.assertEqual(budget.summary(self.budget)['requests'], 2)
        with self.assertRaisesRegex(ValueError, 'request'): budget.reserve(self.budget, self.identity)

    def test_reported_overrun_blocks_future_calls(self):
        self.setup_controls(); budget.configure(self.budget, 10, 1, 0.5)
        ident = budget.reserve(self.budget, self.identity); budget.settle(self.budget, ident, 2)
        self.assertTrue(budget.summary(self.budget)['over_allowance'])
        with self.assertRaises(ValueError): budget.reserve(self.budget, self.identity)

    def test_identity_and_symlink_refused(self):
        self.setup_controls(); budget.configure(self.budget, 3)
        with self.assertRaisesRegex(ValueError, 'identity'):
            budget.reserve(self.budget, dict(self.identity, project_id='foreign-project'))
        (self.folder / 'alias').symlink_to(self.budget, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'): budget.summary(self.folder / 'alias')
        (self.budget / 'budget.json').unlink()
        (self.budget / 'budget.json').symlink_to(self.folder / 'missing')
        with self.assertRaises(ValueError): budget.configure(self.budget, 3)

    def test_budget_cannot_be_reset(self):
        self.setup_controls(); budget.configure(self.budget, 3)
        with self.assertRaisesRegex(ValueError, 'already'): budget.configure(self.budget, 99)

    def test_queue_stale_manifest_refused_before_execution(self):
        self.setup_controls()
        job = queue.enqueue(self.queue, self.catalog, self.identity['project_id'], self.manifest)
        path = self.root / self.manifest
        path.write_text(path.read_text() + ' ')
        with patch.object(queue.coordinator, 'run') as run:
            result = queue.drain(self.queue)
        run.assert_not_called()
        self.assertEqual(result['jobs'][0]['status'], 'failed')

    def test_queue_duplicate_cancel_and_retry(self):
        self.setup_controls()
        job = queue.enqueue(self.queue, self.catalog, self.identity['project_id'], self.manifest)
        with self.assertRaisesRegex(ValueError, 'unfinished'):
            queue.enqueue(self.queue, self.catalog, self.identity['project_id'], self.manifest)
        queue.change(self.queue, job['id'], 'cancel')
        self.assertEqual(queue.status(self.queue)['jobs'][0]['status'], 'cancelled')
        with self.assertRaises(ValueError): queue.change(self.queue, job['id'], 'retry')

    def test_reserved_project_stays_queued_without_dispatch(self):
        self.setup_controls()
        other = dict(self.plan, id='second-batch')
        (self.root / 'second.json').write_text(json.dumps(other))
        self.git('add', 'second.json'); self.git('commit', '-qm', 'Second declared batch')
        tc.start(self.root, self.manifest, self.identity['project_id'])
        queue.enqueue(self.queue, self.catalog, self.identity['project_id'], 'second.json')
        with patch.object(queue, '_run') as run:
            result = queue.drain(self.queue)
        run.assert_not_called()
        self.assertEqual(result['jobs'][0]['status'], 'queued')
        self.assertIn('coordinator', result['jobs'][0]['waiting_for'])

    def test_changed_workflow_refused_before_dispatch(self):
        self.setup_controls()
        queue.enqueue(self.queue, self.catalog, self.identity['project_id'], self.manifest)
        path = self.root / 'workflows/left.json'
        plan = json.loads(path.read_text()); plan['steps'][0]['summary'] += ' Changed intent'
        path.write_text(json.dumps(plan))
        self.git('add', 'workflows/left.json'); self.git('commit', '-qm', 'Changed workflow bytes')
        with patch.object(queue.coordinator, 'run') as run:
            result = queue.drain(self.queue)
        run.assert_not_called()
        self.assertEqual(result['jobs'][0]['status'], 'failed')

    def test_shared_control_inside_project_is_refused(self):
        self.setup_controls()
        with self.assertRaisesRegex(ValueError, 'outside'):
            budget.configure(self.root / '.crewloom/budget', 3)

    def test_queue_priority_and_same_root_serialization(self):
        self.setup_controls()
        base = queue.enqueue(self.queue, self.catalog, self.identity['project_id'], self.manifest)
        state = queue.status(self.queue)
        state['jobs'] = [dict(base, id='low', priority=-1), dict(base, id='high', priority=50)]
        budget.write(self.queue / 'queue.json', state)
        seen = []; active = 0
        def run(job, image, opt):
            nonlocal active
            active += 1; self.assertEqual(active, 1)
            seen.append(job['id']); time.sleep(0.03); active -= 1
            return {'status': 'verified'}
        with patch.object(queue, '_run', side_effect=run): queue.drain(self.queue, 4)
        self.assertEqual(seen, ['high', 'low'])

    def test_crash_is_not_automatically_retried(self):
        self.setup_controls()
        job = queue.enqueue(self.queue, self.catalog, self.identity['project_id'], self.manifest)
        state = queue.status(self.queue); state['jobs'][0]['status'] = 'running'
        budget.write(self.queue / 'queue.json', state)
        with patch.object(queue, '_run') as run: queue.drain(self.queue)
        run.assert_not_called()
        self.assertEqual(queue.status(self.queue)['jobs'][0]['status'], 'interrupted')
        queue.change(self.queue, job['id'], 'retry')
        self.assertEqual(queue.status(self.queue)['jobs'][0]['status'], 'queued')


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS') == '1', 'requires actual Docker')
class DockerSharedBudget(ModelWorkflowFixture):
    def test_one_account_slot_is_shared_by_two_worktrees(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = str(Path(directory).resolve())
            budget.configure(directory, 1)
            requests = []
            image = w.inspect_image(w.DEFAULT_IMAGE)
            with patch.dict(os.environ, {'CREWLOOM_USAGE_BUDGET': directory}), patch.object(model_host, 'generate', _stand_in_provider(requests)):
                report = tc.run(self.root, 'coordinator.json', 'coordinator-fixture', image=image)
            self.assertEqual(len(requests), 1)
            statuses = [task['status'] for task in report['tasks']]
            self.assertIn('verified', statuses)
            self.assertIn('blocked', statuses)
            self.assertEqual(budget.summary(directory)['requests'], 1)


if __name__ == '__main__':
    unittest.main()
