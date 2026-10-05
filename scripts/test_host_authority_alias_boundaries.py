"""Resolved file aliases cannot make native host policy an ordinary output."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import workflow

class HostAuthorityAliasBoundaries(unittest.TestCase):
    def test_symlink_to_host_policy_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'opencode.json').write_text('{}')
            (root/'ordinary.json').symlink_to(root/'opencode.json')
            with self.assertRaises(ValueError):workflow.declared_path(root,'ordinary.json')

    def test_hardlinked_host_policy_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve();(root/'opencode.json').write_text('{}')
            os.link(root/'opencode.json',root/'ordinary.json')
            with self.assertRaises(ValueError):workflow.declared_path(root,'ordinary.json')

if __name__=='__main__':unittest.main()
