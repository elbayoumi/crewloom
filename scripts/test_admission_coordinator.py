"""W09 at the coordinator: manifest budgets, and cancellation that stops owned in-flight work."""
import json
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

import admission as adm
import execution_policy
import task_coordinator as tc
import workflow as w
from test_task_coordinator import CoordinatorFixture


def commit_plan(case):
    case.write_plan()
    case.git('add', 'coordinator.json')
    case.git('commit', '-qm', 'budget manifest')


class ManifestBudget(CoordinatorFixture):
    def test_a_valid_budget_is_accepted_and_invalid_ones_are_refused_before_any_write(self):
        self.plan['budget'] = {'max_model_requests': 10, 'max_concurrent_requests': 2, 'max_elapsed_seconds': None}
        commit_plan(self)
        self.assertTrue(self.call('validate'))
        for bad in ({'max_model_requests': 0}, {'tokens': 5}, {'max_input_bytes': 'a lot'}, 'free'):
            with self.subTest(bad=bad):
                self.plan['budget'] = bad
                commit_plan(self)
                before = self.snapshot()
                with self.assertRaisesRegex(tc.CoordinatorError, 'Manifest budget'):
                    self.call('validate')
                self.assertEqual(self.snapshot(), before)


class CancellationStopsOwnedWork(CoordinatorFixture):
    def test_cancel_terminates_in_flight_owned_processes_and_nothing_else(self):
        self.plan['budget'] = {'max_model_requests': 5}
        commit_plan(self)
        owned, started = {}, threading.Event()
        unrelated = subprocess.Popen(['sleep', '60'])
        self.addCleanup(lambda: (unrelated.kill(), unrelated.wait()))

        def execute(root, step, image, timeout):
            child = subprocess.Popen(['sleep', '60'])
            owned[str(root)] = child
            w._track('process', child.pid, child.pid)      # what docker_execute does for its container client
            if len(owned) >= 2:
                started.set()
            child.wait()                                   # blocks until the batch stops it
            w._untrack('process', child.pid)
            return {'exit_code': 1, 'output': 'stopped', 'image_id': image, 'duration_ms': 1}

        result = {}

        def run():
            with patch.object(w, 'inspect_image', return_value='sha256:t'), \
                    patch.object(execution_policy, 'execute', side_effect=execute):
                result['report'] = self.call('run')
        thread = threading.Thread(target=run)
        thread.start()
        self.addCleanup(lambda: [c.kill() for c in owned.values() if c.poll() is None])
        self.assertTrue(started.wait(60), 'both independent tasks were in flight')
        cancelled = self.call('cancel', reason='test cancellation')
        thread.join(120)
        self.assertFalse(thread.is_alive(), 'the controller drained after cancellation')
        self.assertEqual(cancelled['status'], 'cancellation_requested')
        self.assertEqual(len(cancelled['stopped_owned']), 2)
        self.assertTrue(all(c.poll() is not None for c in owned.values()), 'every owned child was stopped')
        self.assertIsNone(unrelated.poll(), 'an unrelated process survived')
        report = result['report']
        self.assertEqual(report['status'], 'cancelled')
        self.assertEqual(report['admission']['tracked_processes'], [])
        self.assertEqual((self.root / 'left.txt').read_text(), 'base content\n', 'the root is unchanged')
        events = open(report['events']).read()
        self.assertIn('admission.cancelled', events)


if __name__ == '__main__':
    unittest.main()
