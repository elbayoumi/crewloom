"""Independent lock reclamation checks: a stale observation must not remove a new owner."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import repo_map
import workflow


class LockRecoveryBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name).resolve()
        self.lock = self.folder / 'lock'

    def test_a_new_live_owner_is_preserved_after_an_old_dead_owner_observation(self):
        child = subprocess.Popen([sys.executable, '-c', 'pass'], cwd=self.folder,
                                 env=repo_map.git_environment())
        child.wait(timeout=10)
        self.lock.write_text(json.dumps({'pid': child.pid, 'thread': 1, 'folder': str(self.folder)}))
        live = {'pid': os.getpid(), 'thread': 2, 'folder': str(self.folder)}
        kernel_probe = os.kill
        changed = [False]

        def probe(pid, signal):
            if pid == child.pid and signal == 0 and not changed[0]:
                # A competing reclaimer won and created its live lock after this caller read
                # the stale record. The caller must not unlink the winner using that record.
                self.lock.unlink()
                self.lock.write_text(json.dumps(live))
                changed[0] = True
                raise ProcessLookupError('Previous owner exited')
            return kernel_probe(pid, signal)

        with patch.object(os, 'kill', side_effect=probe), self.assertRaises(ValueError):
            with workflow.project_lock(self.folder):
                self.fail('Two managed callers acquired the same root from a stale observation')
        self.assertEqual(json.loads(self.lock.read_text()), live)

    def test_an_unknown_lock_record_is_preserved(self):
        original = 'not a valid ownership record'
        self.lock.write_text(original)
        with self.assertRaises(ValueError):
            with workflow.project_lock(self.folder):
                self.fail('Unknown lock ownership was accepted')
        self.assertEqual(self.lock.read_text(), original)

    @unittest.skipUnless(os.name == 'posix', 'POSIX symlink safety boundary')
    def test_a_symlinked_reclamation_directory_cannot_delete_foreign_files(self):
        child = subprocess.Popen([sys.executable, '-c', 'pass'], cwd=self.folder,
                                 env=repo_map.git_environment())
        child.wait(timeout=10)
        self.lock.write_text(json.dumps({'pid': child.pid, 'thread': 1, 'folder': str(self.folder)}))
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory).resolve()
            (foreign / 'owner.json').write_text(json.dumps({'pid': child.pid}))
            original = 'independent project file must remain intact'
            (foreign / 'keep.txt').write_text(original)
            (self.folder / '.reclaim').symlink_to(foreign, target_is_directory=True)
            with self.assertRaises((ValueError, OSError)):
                with workflow.project_lock(self.folder):
                    self.fail('A foreign reclamation directory was accepted')
            self.assertEqual((foreign / 'keep.txt').read_text(), original)
            self.assertEqual(json.loads((foreign / 'owner.json').read_text())['pid'], child.pid)


if __name__ == '__main__':
    unittest.main()
