"""A crashed worker is persisted as a blocked task, never left running.

`_execute_task` explains the failures it can classify and returns an outcome record for them. An
unexpected exception escapes the worker future instead, and the batch loop has to record that
crash as a blocked task carrying its own error and the declared outputs the crashed worker never
reached. Before the fix the synthesized record missed `declared_outputs`, so the state update
raised `KeyError` out of the loop and the task stayed `running` in the persisted state.

The fixture is the real bound Git project from `test_task_coordinator.py`, so the batch, its
worktrees and the reservation are the real ones; only the worker body is replaced, by an exception
type the worker does not catch. No container, provider or network is involved.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))

import task_coordinator as tc
import test_task_coordinator as fixture

CRASH = 'worker raised an unexpected failure'


class WorkerCrashBoundaries(fixture.CoordinatorFixture):
    """One real batch whose two independent workers both die from an unclassified exception."""

    def crashing_worker(self, message=CRASH):
        """Replace the worker body with a failure `_execute_task` cannot convert to an outcome.

        `RuntimeError` is outside the classification that function applies to its own body, so the
        exception travels out of the future exactly as an unexpected executor fault would.
        """
        return mock.patch.object(tc, '_execute_task', side_effect=RuntimeError(message))

    def state_file(self):
        return self.root / '.crewloom/coordinators/feature-batch/state.json'

    def persisted(self):
        return json.loads(self.state_file().read_text(encoding='utf-8'))

    def events(self):
        path = self.root / '.crewloom/coordinators/feature-batch/events.jsonl'
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]

    def test_an_unexpected_worker_failure_is_recorded_as_blocked_with_its_own_error(self):
        with self.crashing_worker():
            report = self.call('run')

        self.assertEqual(report['status'], 'failed', report)
        tasks = {item['id']: item for item in report['tasks']}
        for ident in ('left', 'right'):
            self.assertEqual(tasks[ident]['status'], 'blocked', tasks[ident])
            self.assertEqual(tasks[ident]['error'], CRASH)
            self.assertEqual(tasks[ident]['declared_outputs'], [ident + '.txt'],
                             'a crash keeps the outputs the crashed worker was going to produce')
            self.assertIsNone(tasks[ident]['commit'])
            self.assertEqual(tasks[ident]['attempts'], 1)
        # The dependent task is blocked by whichever crashed ancestor finished first, and is
        # never dispatched on their behalf.
        self.assertEqual(tasks['combine']['status'], 'blocked')
        self.assertIn(tasks['combine']['error'], ('Blocked by left', 'Blocked by right'))
        self.assertEqual(tasks['combine']['attempts'], 0)

        # The blocked outcome is on disk, not only in the returned report: an operator who reads
        # the state file after the crash sees a finished task instead of one stuck as running.
        state = self.persisted()
        self.assertEqual(state['status'], 'failed')
        for ident, record in state['tasks'].items():
            self.assertNotEqual(record['status'], 'running',
                                'a crashed task may never stay running: ' + ident)
            self.assertEqual(record['status'], 'blocked')
        self.assertEqual(state['tasks']['left']['error'], CRASH)
        self.assertEqual(state['tasks']['right']['error'], CRASH)
        self.assertEqual(state['tasks']['combine']['error'], tasks['combine']['error'])
        self.assertEqual(state['tasks']['left']['declared_outputs'], ['left.txt'])
        self.assertEqual(state['tasks']['right']['declared_outputs'], ['right.txt'])

        crashed = [event for event in self.events() if event['event'] == 'task.crashed']
        self.assertEqual(sorted(event['task'] for event in crashed), ['left', 'right'])
        self.assertTrue(all(event['error'] == CRASH for event in crashed))
        self.assertFalse((self.root / '.crewloom/active_coordinator.json').exists(),
                         'a failed batch releases the root it reserved')

    def test_a_crash_with_no_recorded_declared_output_persists_an_empty_list(self):
        self.call('start')
        state = self.persisted()
        for record in state['tasks'].values():
            record.pop('declared_outputs')
        self.state_file().write_text(json.dumps(state), encoding='utf-8')

        with self.crashing_worker('the crash happened before anything was declared'):
            report = self.call('run')

        tasks = {item['id']: item for item in report['tasks']}
        for ident in ('left', 'right'):
            self.assertEqual(tasks[ident]['status'], 'blocked', tasks[ident])
            self.assertEqual(tasks[ident]['declared_outputs'], [])
            self.assertEqual(tasks[ident]['error'],
                             'the crash happened before anything was declared')
        self.assertEqual(self.persisted()['tasks']['left']['declared_outputs'], [])


if __name__ == '__main__':
    unittest.main()