"""The isolation flags of every workflow container, checked without a Docker daemon."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import workflow as w


class DockerCommand(unittest.TestCase):
    def setUp(self):
        self.mock_uid = os.getuid() or 1000
        self.mock_gid = os.getgid() or 1000
        patch_uid = mock.patch('os.getuid', return_value=self.mock_uid)
        patch_gid = mock.patch('os.getgid', return_value=self.mock_gid)
        patch_uid.start()
        patch_gid.start()
        self.addCleanup(patch_uid.stop)
        self.addCleanup(patch_gid.stop)

        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        (self.root / 'out').mkdir()
        self.addCleanup(self.temp.cleanup)

    def build(self, writable=None, root=None):
        return w.docker_command(root or self.root, ['python3', 'probe.py'], 'sha256:image', 'crewloom-test', writable)

    def pairs(self, command):
        return {command[i]: command[i + 1] for i in range(len(command) - 1) if command[i].startswith('--')}

    def test_isolation_flags_are_always_present(self):
        command = self.build()
        self.assertIn('--read-only', command)
        pairs = self.pairs(command)
        self.assertEqual(pairs['--network'], 'none')
        self.assertEqual(pairs['--cap-drop'], 'ALL')
        self.assertEqual(pairs['--security-opt'], 'no-new-privileges')
        self.assertEqual(pairs['--user'], f'{self.mock_uid}:{self.mock_gid}')
        for flag in ('--pids-limit', '--memory', '--cpus', '--ulimit'):
            self.assertIn(flag, pairs)

    def test_root_user_is_refused(self):
        with mock.patch('os.getuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'refuse to run as root'):
                self.build()
        with mock.patch('os.getuid', return_value=0):
            with self.assertRaisesRegex(ValueError, 'refuse to run as root'):
                w.docker_user()

    def test_no_privilege_widening_options(self):
        command = self.build(['out'])
        for forbidden in ('--privileged', '--cap-add', '--pid', '--ipc', '--uts', '--device', '--volume', '-v'):
            self.assertNotIn(forbidden, command)
        self.assertFalse(any('docker.sock' in item for item in command))
        self.assertEqual(self.pairs(command)['--network'], 'none')

    def test_image_and_argv_follow_all_options(self):
        command = self.build()
        self.assertEqual(command[-3:], ['sha256:image', 'python3', 'probe.py'])
        self.assertTrue(all(not item.startswith('--') for item in command[-3:]))

    def test_project_is_the_only_mount_and_runtime_state_is_hidden(self):
        command = self.build()
        mounts = [command[i + 1] for i, item in enumerate(command) if item == '--mount']
        self.assertEqual(mounts, [f'type=bind,src={self.root},dst=/workspace'])
        self.assertIn('/workspace/.crewloom:ro,noexec,nosuid,size=1m', command)

    def test_writable_paths_make_the_project_read_only_with_narrow_mounts(self):
        command = self.build(['out'])
        mounts = [command[i + 1] for i, item in enumerate(command) if item == '--mount']
        self.assertEqual(mounts, [f'type=bind,src={self.root},dst=/workspace,readonly',
                                  f'type=bind,src={self.root / "out"},dst=/workspace/out'])

    def test_empty_writable_set_is_fully_read_only(self):
        command = self.build(())
        self.assertTrue(any(item.endswith(',readonly') for item in command))

    def test_comma_in_any_mount_path_is_refused(self):
        comma = self.root / 'a,b'
        comma.mkdir()
        with self.assertRaisesRegex(ValueError, 'commas'):
            self.build(root=comma)
        with self.assertRaisesRegex(ValueError, 'commas'):
            w.bind_mount('/tmp/x,readonly=false', '/workspace')

    def test_writable_path_cannot_escape_the_project(self):
        with self.assertRaises(ValueError):
            self.build(['../outside'])


if __name__ == '__main__':
    unittest.main()
