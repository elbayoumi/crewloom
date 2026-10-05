"""Independent recovery checks: corrupt backups and unsafe process probes fail closed."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import execution_policy as broker
import workflow
import test_transaction_acceptance_boundaries as transaction_cases


class RecoveryIntegrityBoundaries(unittest.TestCase):
    def setUp(self):
        transaction_cases.GroupedPublicationBoundaries.setUp(self)

    def interrupted(self):
        transaction_cases.GroupedPublicationBoundaries.interrupted_group(self)
        folders = list((self.root / '.crewloom/transactions/pending').iterdir())
        self.assertEqual(len(folders), 1)
        return folders[0]

    def test_corrupt_backup_refuses_recovery_before_any_destination_write(self):
        folder = self.interrupted()
        (folder / 'backup/0.bin').write_bytes(b'corrupt backup, not original content\n')
        with self.assertRaises(ValueError):
            broker.recover(self.root)
        self.assertEqual((self.root / 'first.txt').read_bytes(), b'new first\n')
        self.assertEqual((self.root / 'second.txt').read_bytes(), b'original second\n')
        self.assertTrue((folder / 'journal.json').is_file())

    def test_missing_backup_refuses_recovery_with_journal_and_files_preserved(self):
        folder = self.interrupted()
        (folder / 'backup/0.bin').unlink()
        with self.assertRaises(ValueError):
            broker.recover(self.root)
        self.assertEqual((self.root / 'first.txt').read_bytes(), b'new first\n')
        self.assertTrue((folder / 'journal.json').is_file())

    def test_non_posix_lock_probe_never_sends_signal_zero(self):
        # Python documents os.kill(pid, 0) as TerminateProcess on Windows, so an
        # unverified platform must retain an uncertain owner without probing it.
        with patch.object(os, 'name', 'nt'), patch.object(os, 'kill') as probe:
            self.assertTrue(workflow._lock_owner({'pid': os.getpid() + 10000}))
            probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
