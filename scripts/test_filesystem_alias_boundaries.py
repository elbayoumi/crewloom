"""Independent control-path and physical filesystem alias publication boundaries."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import execution_policy as broker
import workflow


class FilesystemAliasBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-alias-acceptance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'input.txt').write_bytes(b'frozen input\n')
        self.expected = workflow.hashes(self.root, ['input.txt'])

    def require_case_insensitive_filesystem(self):
        if not (self.root / 'INPUT.TXT').exists():
            self.skipTest('Actual case-insensitive filesystem required; no simulated alias proof')

    def test_runtime_path_names_remain_reserved_under_case_variants(self):
        (self.root / '.crewloom').mkdir()
        protected = self.root / '.crewloom/protected.json'
        protected.write_bytes(b'protected runtime state\n')
        with self.assertRaises(ValueError):
            broker.publish(self.root, {'.CREWLOOM/protected.json': b'candidate overwrote state\n'}, self.expected)
        self.assertEqual(protected.read_bytes(), b'protected runtime state\n')

    def test_policy_filename_remains_reserved_under_case_variants(self):
        protected = self.root / 'crewloom.project.json'
        protected.write_bytes(b'{"policy":"enforced"}\n')
        with self.assertRaises(ValueError):
            broker.publish(self.root, {'CREWLOOM.PROJECT.JSON': b'{"policy":"disabled"}\n'}, self.expected)
        self.assertEqual(protected.read_bytes(), b'{"policy":"enforced"}\n')

    def test_existing_physical_destination_aliases_are_refused_before_writes(self):
        self.require_case_insensitive_filesystem()
        original = self.root / 'Result.txt'
        original.write_bytes(b'original output\n')
        self.assertTrue(original.samefile(self.root / 'result.txt'))
        with self.assertRaises(ValueError):
            broker.publish(self.root, {'Result.txt': b'first replacement\n',
                                      'result.txt': b'second replacement\n'}, self.expected)
        self.assertEqual(original.read_bytes(), b'original output\n')

    def test_new_case_aliases_are_refused_as_a_whole_group(self):
        self.require_case_insensitive_filesystem()
        with self.assertRaises(ValueError):
            broker.publish(self.root, {'New.txt': b'first new file\n',
                                      'new.txt': b'second new file\n'}, self.expected)
        self.assertFalse((self.root / 'New.txt').exists())
        self.assertFalse((self.root / 'new.txt').exists())

    def test_a_trusted_runtime_directory_cannot_be_reached_through_case_aliases(self):
        self.require_case_insensitive_filesystem()
        trusted = self.root / 'vendor'
        trusted.mkdir()
        runtime = trusted / 'runtime.py'
        runtime.write_bytes(b'trusted runtime\n')
        self.assertTrue(trusted.samefile(self.root / 'VENDOR'))
        with patch.object(broker, 'trusted_roots', return_value={trusted}), self.assertRaises(ValueError):
            broker.publish(self.root, {'VENDOR/runtime.py': b'candidate replaced runtime\n'}, self.expected)
        self.assertEqual(runtime.read_bytes(), b'trusted runtime\n')


if __name__ == '__main__':
    unittest.main()
