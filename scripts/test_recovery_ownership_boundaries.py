"""Independent recovery ownership: unexpected state and new hardlinks are preserved."""
import os
from pathlib import Path
import tempfile
import unittest

import execution_policy as broker
import test_transaction_acceptance_boundaries as transaction_cases


class RecoveryOwnershipBoundaries(unittest.TestCase):
    def setUp(self):
        transaction_cases.GroupedPublicationBoundaries.setUp(self)

    def interrupted(self):
        transaction_cases.GroupedPublicationBoundaries.interrupted_group(self)
        return next((self.root / '.crewloom/transactions/pending').iterdir())

    def test_unrecognised_payload_file_is_reported_and_never_deleted(self):
        folder = self.interrupted()
        foreign = folder / 'payload/manual-investigation.txt'
        foreign.write_text('independent notes, never staged by this transaction\n')
        with self.assertRaises(ValueError):
            broker.recover(self.root)
        self.assertEqual(foreign.read_text(), 'independent notes, never staged by this transaction\n')
        self.assertTrue((folder / 'journal.json').is_file())

    @unittest.skipUnless(os.name == 'posix', 'POSIX hardlink ownership')
    def test_destination_hardlinked_after_interruption_blocks_recovery(self):
        folder = self.interrupted()
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory).resolve() / 'independent.txt'
            os.link(self.root / 'first.txt', foreign)
            with self.assertRaises(ValueError):
                broker.recover(self.root)
            self.assertEqual((self.root / 'first.txt').read_bytes(), b'new first\n')
            self.assertEqual(foreign.read_bytes(), b'new first\n')
            self.assertTrue((folder / 'journal.json').is_file())


if __name__ == '__main__':
    unittest.main()
