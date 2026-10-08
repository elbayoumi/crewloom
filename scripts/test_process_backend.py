"""Internal native-Windows acceptance: real handles, process trees, locking and controller crash.

Runs against Windows only in the dedicated CI job. Local skips are not Windows evidence.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import admission as a
import process_backend as backend


class PlatformContract(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'non-Windows refusal')
    def test_unavailable_backend_refuses_before_any_native_call(self):
        with self.assertRaisesRegex(backend.ProcessBackendError, 'unavailable'):
            backend.OwnedJob()


@unittest.skipUnless(os.name == 'nt', 'real Windows process acceptance requires Windows CI')
class WindowsOwnership(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crewloom-win-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / 'batch'
        a.configure(self.folder, 'windows-batch', {})
        self.addCleanup(lambda: a.terminate_owned(self.folder))

    def launch(self, code):
        with a.context(self.folder, 'windows-task'):
            return a.launch_owned([sys.executable, '-c', code], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)

    def test_handle_creation_identity_and_reused_identity_refusal(self):
        state, started = a.observe_process(os.getpid())
        self.assertEqual(state, 'present')
        self.assertTrue(started.startswith('windows-filetime:'))
        self.assertEqual(a.pid_state(os.getpid(), started)[0], 'alive')
        self.assertEqual(a.pid_state(os.getpid(), 'different-creation-time')[0], 'dead')
        self.assertEqual(backend.observe(-1)[0], 'unknown')
        self.assertEqual(backend.observe(2**40)[0], 'unknown')

    def test_job_cancels_parent_and_child_and_preserves_a_bystander(self):
        bystander = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(120)'])
        self.addCleanup(lambda: bystander.poll() is None and (bystander.kill(), bystander.wait()))
        code = 'import subprocess,sys,time;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"]);print(p.pid,flush=True);time.sleep(120)'
        parent = self.launch(code)
        child = int(parent.stdout.readline().strip())
        self.assertEqual(a.observe_process(child)[0], 'present', 'negative precondition: real live child')
        outcomes = a.terminate_owned(self.folder)
        parent.wait(timeout=10)
        self.assertEqual(outcomes[0]['result'], 'killed')
        self.assertEqual(a.observe_process(child)[0], 'absent')
        self.assertIsNone(bystander.poll())
        for stream in (parent.stdin, parent.stdout, parent.stderr): stream.close()

    def test_assignment_failure_cannot_release_the_target(self):
        marker = self.root / 'must-not-exist'
        code = 'import sys;open(sys.argv[1],"w").write("bad")'
        with a.context(self.folder, 'refused-task'), patch.object(backend.OwnedJob, 'assign', side_effect=backend.ProcessBackendError('fixture assignment failure')):
            with self.assertRaisesRegex(backend.ProcessBackendError, 'assignment failure'):
                a.launch_owned([sys.executable, '-c', code, str(marker)], stdin=subprocess.PIPE, text=True)
        self.assertFalse(marker.exists())

    def test_actual_controller_crash_closes_job_and_stops_the_child(self):
        record = self.root / 'child.txt'
        controller_code = ('import admission as a,sys,subprocess,os; '
            'a.configure(sys.argv[1],"crash-batch",{});c=a.context(sys.argv[1],"crash-task");c.__enter__();'
            'p=a.launch_owned([sys.executable,"-c",sys.argv[3]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);'
            'open(sys.argv[2],"w").write(p.stdout.readline().strip());os._exit(73)')
        target_code = 'import subprocess,sys,time;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"]);print(p.pid,flush=True);time.sleep(120)'
        crash_folder = self.root / 'crash'
        result = subprocess.run([sys.executable, '-c', controller_code, str(crash_folder), str(record), target_code],
            env={**os.environ, 'PYTHONPATH': str(Path(a.__file__).parent)}, timeout=20)
        self.assertEqual(result.returncode, 73)
        child = int(record.read_text())
        deadline = time.monotonic() + 10
        while a.observe_process(child)[0] == 'present' and time.monotonic() < deadline: time.sleep(.05)
        self.assertEqual(a.observe_process(child)[0], 'absent')
        recovered = a.recover(crash_folder)
        self.assertTrue(recovered['stopped'])
        self.assertTrue(all(item['result'] == 'gone' for item in recovered['stopped']), recovered)

    def test_parallel_admission_has_a_real_cross_process_windows_lock(self):
        worker = ('import admission as a,sys,json; '
                  'r=a.admit(sys.argv[1],sys.argv[2],{"input_bytes":10});print(json.dumps(r))')
        a.configure(self.folder, 'windows-batch', {'max_model_requests': 1})
        env = {**os.environ, 'PYTHONPATH': str(Path(a.__file__).parent)}
        processes = [subprocess.Popen([sys.executable, '-c', worker, str(self.folder), 'request-%d' % i],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env) for i in range(2)]
        results = [p.communicate(timeout=20) for p in processes]
        self.assertTrue(all(p.returncode == 0 for p in processes), results)
        value = json.loads((self.folder / 'admission.json').read_text())
        self.assertEqual(sum(item['state'] == 'dispatched' for item in value['requests'].values()), 1)


if __name__ == '__main__':
    unittest.main()
