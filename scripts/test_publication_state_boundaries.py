"""Independent journal scope, aggregate budget, and private staging boundaries."""
import json
import os
import shutil
import unittest
from unittest.mock import patch

import execution_policy as broker
import test_transaction_acceptance_boundaries as transaction_cases


class PublicationStateBoundaries(unittest.TestCase):
    def setUp(self):
        transaction_cases.GroupedPublicationBoundaries.setUp(self)

    def interrupted(self):
        transaction_cases.GroupedPublicationBoundaries.interrupted_group(self)
        return next((self.root / '.crewloom/transactions/pending').iterdir())

    def test_canonical_destination_aliases_refuse_recovery_before_writes(self):
        folder = self.interrupted()
        journal = folder / 'journal.json'
        state = json.loads(journal.read_text())
        alias = dict(state['entries'][0], index=1, path='./first.txt')
        state['entries'] = [state['entries'][0], alias]
        shutil.copyfile(folder / 'backup/0.bin', folder / 'backup/1.bin')
        journal.write_text(json.dumps(state))
        with self.assertRaises(ValueError):
            broker.recover(self.root)
        self.assertEqual((self.root / 'first.txt').read_bytes(), b'new first\n')
        self.assertTrue(journal.is_file())

    def test_aggregate_recovery_backup_budget_is_checked_before_restore(self):
        folder = self.interrupted()
        journal = folder / 'journal.json'
        state = json.loads(journal.read_text())
        state['entries'][1]['state'] = 'replaced'
        (self.root / 'second.txt').write_bytes(b'new second\n')
        journal.write_text(json.dumps(state))
        # Each original is below20 bytes, but together they exceed that group cap.
        with patch.object(broker, 'MAX_BACKUP_BYTES', 20), self.assertRaises(ValueError):
            broker.recover(self.root)
        self.assertEqual((self.root / 'first.txt').read_bytes(), b'new first\n')
        self.assertEqual((self.root / 'second.txt').read_bytes(), b'new second\n')
        self.assertTrue(journal.is_file())

    @unittest.skipUnless(os.name == 'posix', 'POSIX private staging permissions')
    def test_staged_copies_do_not_expose_more_than_owner_only_originals(self):
        folder = self.interrupted()
        for item in [folder, folder / 'backup', folder / 'payload',
                     folder / 'backup/0.bin', folder / 'payload/0.bin']:
            with self.subTest(path=str(item.relative_to(self.root))):
                self.assertEqual(item.stat().st_mode & 0o077, 0,
                                 'Private staged content must be inaccessible to group/others')


if __name__ == '__main__':
    unittest.main()
