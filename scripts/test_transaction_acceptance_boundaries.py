"""Independent grouped-publication acceptance; preserve supervisor assertions."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import execution_policy as broker
import workflow


class GroupedPublicationBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'input.txt').write_text('frozen input\n')
        self.expected = workflow.hashes(self.root, ['input.txt'])

    def failing_second_replace(self):
        original_replace = os.replace
        destination = self.root / 'second.txt'
        failed = [False]

        def replace(source, target, *args, **kwargs):
            if Path(target).resolve() == destination and not failed[0]:
                failed[0] = True
                raise OSError('Injected second output replacement failure')
            return original_replace(source, target, *args, **kwargs)

        return patch.object(os, 'replace', side_effect=replace)

    def test_failed_second_write_restores_first_file_and_original_permissions(self):
        first = self.root / 'first.txt'
        second = self.root / 'second.txt'
        first.write_bytes(b'original first\n')
        second.write_bytes(b'original second\n')
        first.chmod(0o640)
        with self.failing_second_replace(), self.assertRaises(OSError):
            broker.publish(self.root, {'first.txt': b'new first\n', 'second.txt': b'new second\n'}, self.expected)
        self.assertEqual(first.read_bytes(), b'original first\n')
        self.assertEqual(second.read_bytes(), b'original second\n')
        if os.name == 'posix':
            self.assertEqual(first.stat().st_mode & 0o777, 0o640)

    def test_failed_group_removes_only_the_new_first_output(self):
        with self.failing_second_replace(), self.assertRaises(OSError):
            broker.publish(self.root, {'first.txt': b'new first\n', 'second.txt': b'new second\n'}, self.expected)
        self.assertFalse((self.root / 'first.txt').exists())
        self.assertFalse((self.root / 'second.txt').exists())
        self.assertEqual((self.root / 'input.txt').read_text(), 'frozen input\n')

    def test_invalid_second_destination_is_refused_before_first_output_changes(self):
        first = self.root / 'first.txt'
        first.write_bytes(b'original first\n')
        (self.root / 'second.txt').mkdir()
        with self.assertRaises(ValueError):
            broker.publish(self.root, {'first.txt': b'new first\n', 'second.txt': b'new second\n'}, self.expected)
        self.assertEqual(first.read_bytes(), b'original first\n')

    def test_changed_input_refuses_entire_group_without_destination_writes(self):
        (self.root / 'input.txt').write_text('changed input\n')
        with self.assertRaises(ValueError):
            broker.publish(self.root, {'first.txt': b'new first\n', 'second.txt': b'new second\n'}, self.expected)
        self.assertFalse((self.root / 'first.txt').exists())
        self.assertFalse((self.root / 'second.txt').exists())

    def interrupted_group(self):
        """Terminate a real writer after the first destination replace, not a mock recovery."""
        first = self.root / 'first.txt'
        first.write_bytes(b'original first\n')
        first.chmod(0o640)
        (self.root / 'second.txt').write_bytes(b'original second\n')
        code = '''import os,pathlib,sys
sys.path.insert(0,sys.argv[2])
import execution_policy as broker,workflow
root=pathlib.Path(sys.argv[1]).resolve()
original=os.replace
def replace(source,target,*args,**kwargs):
 result=original(source,target,*args,**kwargs)
 if pathlib.Path(target).resolve()==root/'first.txt':os._exit(91)
 return result
os.replace=replace
broker.publish(root,{'first.txt':b'new first\\n','second.txt':b'new second\\n'},workflow.hashes(root,['input.txt']))
'''
        import repo_map
        result = subprocess.run([sys.executable, '-c', code, str(self.root),
                                 str(Path(__file__).resolve().parent)],
                                cwd=self.root, env=repo_map.git_environment(),
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 91, result.stderr.decode(errors='replace'))
        self.assertEqual(first.read_bytes(), b'new first\n')

    def test_next_managed_publication_recovers_a_process_interruption(self):
        self.interrupted_group()
        broker.publish(self.root, {'third.txt': b'next valid group\n'}, self.expected)
        self.assertEqual((self.root / 'first.txt').read_bytes(), b'original first\n')
        self.assertEqual((self.root / 'second.txt').read_bytes(), b'original second\n')
        self.assertEqual((self.root / 'third.txt').read_bytes(), b'next valid group\n')
        if os.name == 'posix':
            self.assertEqual((self.root / 'first.txt').stat().st_mode & 0o777, 0o640)

    def test_foreign_change_after_interruption_blocks_recovery_without_overwrite(self):
        self.interrupted_group()
        (self.root / 'first.txt').write_bytes(b'new independent user edit\n')
        with self.assertRaises(ValueError):
            broker.publish(self.root, {'third.txt': b'next valid group\n'}, self.expected)
        self.assertEqual((self.root / 'first.txt').read_bytes(), b'new independent user edit\n')
        self.assertEqual((self.root / 'second.txt').read_bytes(), b'original second\n')
        self.assertFalse((self.root / 'third.txt').exists())


if __name__ == '__main__':
    unittest.main()
