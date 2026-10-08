"""W09: cancellation owns the whole process tree and verifies an immutable container identity.

Process tests use real disposable processes that this file creates and reaps. Container tests run in two
tiers: a simulated daemon (every identity branch, no Docker needed) and, only when CREWLOOM_DOCKER_TESTS=1
and an already-present image is named, real containers that carry a unique run label so nothing else is
ever touched."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

import admission as adm
import workflow as w

POSIX = os.name == 'posix'
HAS_PS = POSIX and shutil.which('ps') is not None  # process identity is read from `ps`; without it nothing here is provable
CHILDREN = ("import subprocess, sys, time\n"
            "grand = subprocess.Popen(['sleep', '120'])\n"
            "child = subprocess.Popen([sys.executable, '-c', "
            "\"import subprocess, sys, time; g = subprocess.Popen(['sleep', '120']); "
            "open(sys.argv[1], 'a').write('grandchild %d\\\\n' % g.pid); time.sleep(120)\", sys.argv[1]])\n"
            "open(sys.argv[1], 'a').write('child %d\\nsibling %d\\n' % (child.pid, grand.pid))\n"
            "{tail}")


def alive(pid):
    return adm.pid_alive(pid)


@unittest.skipUnless(HAS_PS, 'process groups need POSIX and ps')
class OwnedProcessTree(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-tree-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.folder = self.base / 'batch'
        adm.configure(self.folder, 'batch-one', {})
        self.spawned = []
        self.addCleanup(self.reap)

    def reap(self):
        for pid in self.spawned:
            if alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass

    def launch(self, tail='time.sleep(120)', new_session=True):
        """A parent that starts a child, which starts a grandchild, plus a sibling of the child."""
        record = self.base / ('pids-%s.txt' % uuid.uuid4().hex)
        parent = subprocess.Popen([sys.executable, '-c', CHILDREN.format(tail=tail), str(record)],
                                  start_new_session=new_session)
        self.spawned.append(parent.pid)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            names = dict(line.split() for line in record.read_text().splitlines()) if record.exists() else {}
            if {'child', 'sibling', 'grandchild'} <= set(names):
                break
            time.sleep(0.05)
        pids = {name: int(value) for name, value in names.items()}
        self.spawned.extend(pids.values())
        self.assertEqual(set(pids), {'child', 'sibling', 'grandchild'}, 'the disposable tree started')
        return parent, pids

    def unrelated(self):
        child = subprocess.Popen(['sleep', '120'])
        self.spawned.append(child.pid)
        self.addCleanup(lambda: child.poll() is None and (child.kill(), child.wait()))
        return child

    def assert_gone(self, pids):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(alive(p) for p in pids):
            time.sleep(0.05)
        self.assertEqual([p for p in pids if alive(p)], [])

    def test_parent_child_and_grandchild_all_terminate_and_an_unrelated_process_does_not(self):
        parent, pids = self.launch()
        bystander = self.unrelated()
        adm.track_process(self.folder, 'process', parent.pid, parent.pid, 'task-a')
        entry = json.loads((self.folder / 'admission.json').read_text())['processes']['process:%d' % parent.pid]
        self.assertTrue(entry['own_group'])
        result = adm.terminate_owned(self.folder)
        parent.wait(timeout=10)
        self.assertIn(result[0]['result'], ('terminated', 'killed'))
        self.assert_gone(list(pids.values()))
        self.assertIsNone(bystander.poll(), 'an unrelated process is untouched')
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], [])

    def test_a_tree_that_shares_the_controllers_group_is_stopped_through_its_descendants_only(self):
        parent, pids = self.launch(new_session=False)
        bystander = self.unrelated()
        adm.track_process(self.folder, 'process', parent.pid, parent.pid, 'shared-group')
        entry = json.loads((self.folder / 'admission.json').read_text())['processes']['process:%d' % parent.pid]
        self.assertFalse(entry['own_group'], 'the controller group is never signalled as a group')
        adm.terminate_owned(self.folder)
        parent.wait(timeout=10)
        self.assert_gone(list(pids.values()))
        self.assertIsNone(bystander.poll())

    def test_a_parent_that_exits_first_does_not_orphan_descendants_outside_recovery(self):
        parent, pids = self.launch(tail='import os\nwhile not os.path.exists(sys.argv[1] + ".go"): time.sleep(0.05)')
        adm.track_process(self.folder, 'process', parent.pid, parent.pid, 'orphaning')
        Path(str(next(self.base.glob('pids-*.txt'))) + '.go').write_text('go')   # only now may the parent exit
        parent.wait(timeout=10)
        self.assertFalse(alive(parent.pid))
        self.assertTrue(all(alive(p) for p in pids.values()), 'descendants outlive their parent')
        bystander = self.unrelated()
        result = adm.terminate_owned(self.folder)
        self.assertIn(result[0]['result'], ('terminated', 'killed'))
        self.assert_gone(list(pids.values()))
        self.assertIsNone(bystander.poll())

    def test_graceful_termination_escalates_to_a_bounded_kill(self):
        stubborn = ("import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                    "while True: time.sleep(1)")
        parent, pids = self.launch(tail=stubborn)
        adm.track_process(self.folder, 'process', parent.pid, parent.pid, 'stubborn')
        entry = json.loads((self.folder / 'admission.json').read_text())
        started = time.monotonic()
        with patch.object(adm.signal, 'SIGTERM', signal.SIGTERM):
            result = adm.terminate_owned(self.folder)
        parent.wait(timeout=10)
        self.assertEqual(result[0]['result'], 'killed')
        self.assertLess(time.monotonic() - started, 15)
        self.assert_gone(list(pids.values()))

    def test_a_reused_group_id_or_pid_is_never_signalled(self):
        leader = subprocess.Popen(['sleep', '120'], start_new_session=True)  # a different process, own group
        self.spawned.append(leader.pid)
        adm.track_process(self.folder, 'process', leader.pid, leader.pid, 'recorded-identity')
        path = self.folder / 'admission.json'
        record = json.loads(path.read_text())
        record['processes']['process:%d' % leader.pid]['pid_start'] = 'Thu Jan  1 00:00:00 1970'
        path.write_text(json.dumps(record))
        result = adm.terminate_owned(self.folder)
        self.assertTrue(result[0]['result'].startswith('unverifiable'), result)
        self.assertIsNone(leader.poll(), 'the process that now owns the id is protected')
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], ['process:%d' % leader.pid],
                         'the refusal stays visible instead of being forgotten')
        leader.kill()
        leader.wait()

    def test_controller_crash_recovery_uses_the_same_tree_ownership(self):
        parent, pids = self.launch()
        adm.track_process(self.folder, 'process', parent.pid, parent.pid, 'dead-controller')
        path = self.folder / 'admission.json'
        record = json.loads(path.read_text())
        record['processes']['process:%d' % parent.pid].update(controller_pid=2 ** 22 + 4242, controller_start='gone')
        path.write_text(json.dumps(record))
        report = adm.recover(self.folder)
        parent.wait(timeout=10)
        self.assertIn(report['stopped'][0]['result'], ('terminated', 'killed'))
        self.assert_gone(list(pids.values()))

    def test_reap_group_stops_what_a_finished_parent_left_behind(self):
        parent, pids = self.launch(tail='')
        parent.wait(timeout=10)
        self.assertEqual(adm.reap_group(parent.pid, time.time() - 60), [])
        self.assert_gone(list(pids.values()))
        self.assertEqual(adm.reap_group(os.getpgrp()), [], 'the controller group is never reaped')
        self.assertEqual(adm.reap_group(1), [])

    def test_a_group_that_predates_the_launch_is_never_reaped(self):
        parent, pids = self.launch()
        self.assertEqual(adm.reap_group(parent.pid, time.time() + 3600), [], 'older than the claimed launch: not ours')
        self.assertTrue(all(alive(p) for p in pids.values()))
        os.killpg(parent.pid, signal.SIGKILL)
        parent.wait(timeout=10)

    def test_a_negative_control_a_single_pid_signal_would_leave_descendants(self):
        parent, pids = self.launch()
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=10)
        self.assertTrue(all(alive(p) for p in pids.values()), 'the old behavior orphaned the tree')
        os.killpg(parent.pid, signal.SIGKILL)

    def test_required_tracking_fails_visibly_inside_a_batch_and_is_a_noop_outside(self):
        self.assertIsNone(w._track('process', 1, 1))
        missing = self.base / 'unconfigured'
        with adm.context(missing, 'task'):
            with self.assertRaisesRegex(adm.AdmissionError, 'cannot be tracked'):
                w._track('process', 1, 1)
        import model_host
        with adm.context(missing, 'task'):
            with self.assertRaises(adm.AdmissionError):
                model_host._track_owned('process', 1, 1)


class FakeDaemon:
    """An in-memory Docker daemon that answers exactly the calls admission makes."""
    def __init__(self):
        self.containers = {}
        self.broken = False
        self.removed = []

    def add(self, name, labels, ident=None):
        ident = ident or uuid.uuid4().hex + uuid.uuid4().hex
        self.containers[ident] = {'name': name, 'labels': dict(labels)}
        return ident

    def __call__(self, *argv):
        if self.broken:
            return 1, '', 'Cannot connect to the Docker daemon'
        if argv[:2] == ('container', 'inspect'):
            reference = argv[-1]
            for ident, item in self.containers.items():
                if reference in (ident, item['name']):
                    return 0, json.dumps(ident) + '|' + json.dumps(item['labels']) + '\n', ''
            return 1, '', 'Error: No such container: ' + reference
        if argv[:2] == ('rm', '--force'):
            self.removed.append(argv[2])
            return (0, argv[2], '') if self.containers.pop(argv[2], None) else (1, '', 'No such container')
        return 1, '', 'unsupported'


class ContainerIdentity(unittest.TestCase):
    OWNED = {'crewloom.owner': 'crewloom', 'crewloom.run': 'run-1'}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-container-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name) / 'batch'
        adm.configure(self.folder, 'batch-one', {})
        self.daemon = FakeDaemon()
        patcher = patch.object(adm, '_docker', side_effect=self.daemon)
        patcher.start()
        self.addCleanup(patcher.stop)

    def track(self, ident, name='crewloom-x', labels=None):
        adm.track_process(self.folder, 'container', name, 1, 'task', {'id': ident, 'labels': labels or self.OWNED})

    def test_interrupted_container_launch_resolves_labels_then_removes_only_the_owned_id(self):
        name = 'crewloom-' + 'a' * 32
        with adm.context(self.folder, 'intent-task'):
            adm.track_container_intent(name, self.OWNED)
        owned = self.daemon.add(name, self.OWNED)
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'removed')
        self.assertEqual(self.daemon.removed, [owned])
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], [])

    def test_reused_name_after_interrupted_container_launch_is_preserved(self):
        name = 'crewloom-' + 'b' * 32
        with adm.context(self.folder, 'intent-task'):
            adm.track_container_intent(name, self.OWNED)
        stranger = self.daemon.add(name, {'app': 'unrelated'})
        self.assertTrue(adm.terminate_owned(self.folder)[0]['result'].startswith('preserved'))
        self.assertEqual(self.daemon.removed, [])
        self.assertIn(stranger, self.daemon.containers)

    def test_an_owned_container_is_removed_by_its_immutable_id(self):
        ident = self.daemon.add('crewloom-x', self.OWNED)
        other = self.daemon.add('unrelated-service', {'app': 'db'})
        self.track(ident)
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'removed')
        self.assertEqual(self.daemon.removed, [ident], 'removal addressed the id, never the name')
        self.assertIn(other, self.daemon.containers)
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], [])

    def test_a_reused_name_belonging_to_another_container_is_preserved(self):
        ident = self.daemon.add('crewloom-x', self.OWNED)
        self.track(ident)
        del self.daemon.containers[ident]                        # ours exited and was auto-removed
        stranger = self.daemon.add('crewloom-x', {'app': 'prod'})  # the same name now means something else
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'gone')
        self.assertEqual(self.daemon.removed, [])
        self.assertIn(stranger, self.daemon.containers)

    def test_the_same_id_with_changed_ownership_labels_is_preserved_and_the_mismatch_is_visible(self):
        ident = self.daemon.add('crewloom-x', {'crewloom.owner': 'crewloom', 'crewloom.run': 'someone-else'})
        self.track(ident)
        result = adm.terminate_owned(self.folder)[0]['result']
        self.assertTrue(result.startswith('preserved'), result)
        self.assertEqual(self.daemon.removed, [])

    def test_unverifiable_ownership_is_not_acted_on_and_stays_tracked(self):
        ident = self.daemon.add('crewloom-x', self.OWNED)
        self.track(ident)
        self.daemon.broken = True
        self.assertTrue(adm.terminate_owned(self.folder)[0]['result'].startswith('unverifiable'))
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], ['container:crewloom-x'])
        self.daemon.broken = False
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'removed')  # a later retry succeeds

    def test_a_legacy_name_only_record_is_refused_not_trusted(self):
        ident = self.daemon.add('crewloom-legacy', self.OWNED)
        path = self.folder / 'admission.json'
        record = json.loads(path.read_text())
        record['processes']['container:crewloom-legacy'] = {
            'kind': 'container', 'ident': 'crewloom-legacy', 'pid': None, 'pid_start': None,
            'controller_pid': os.getpid(), 'controller_start': adm.process_start(os.getpid()), 'task': 't', 'tracked_at': 0}
        path.write_text(json.dumps(record))
        result = adm.terminate_owned(self.folder)[0]['result']
        self.assertTrue(result.startswith('unverifiable'), result)
        self.assertIn(ident, self.daemon.containers)

    def test_a_container_cannot_be_tracked_by_name_alone(self):
        for bad in (None, {'id': 'short', 'labels': self.OWNED}, {'id': 'a' * 64, 'labels': {}}):
            with self.assertRaisesRegex(adm.AdmissionError, 'immutable id'):
                adm.track_process(self.folder, 'container', 'crewloom-x', 1, 't', bad)

    def test_restart_recovery_repeats_the_same_identity_checks(self):
        ident = self.daemon.add('crewloom-x', self.OWNED)
        stranger = self.daemon.add('crewloom-y', {'app': 'prod'})
        self.track(ident)
        self.track(stranger, 'crewloom-y', {'crewloom.owner': 'crewloom', 'crewloom.run': 'run-2'})
        path = self.folder / 'admission.json'
        record = json.loads(path.read_text())
        for entry in record['processes'].values():
            entry.update(controller_pid=2 ** 22 + 99, controller_start='gone')
        path.write_text(json.dumps(record))
        results = {item['key']: item['result'] for item in adm.recover(self.folder)['stopped']}
        self.assertEqual(results['container:crewloom-x'], 'removed')
        self.assertTrue(results['container:crewloom-y'].startswith('preserved'))
        self.assertIn(stranger, self.daemon.containers)

    def test_a_negative_control_removal_by_name_would_have_deleted_the_stranger(self):
        stranger = self.daemon.add('crewloom-x', {'app': 'prod'})
        self.assertEqual(self.daemon('rm', '--force', stranger)[0], 0)  # what `docker rm --force <name>` allowed


class DockerExecuteUsesTheIdentity(unittest.TestCase):
    """docker_execute against a shim `docker` that behaves like a daemon: exercises the real call sequence."""
    SHIM = r'''#!/usr/bin/env python3
import json, os, sys, time
state = os.environ['SHIM_STATE']
data = json.load(open(state)) if os.path.exists(state) else {}
argv = sys.argv[1:]
def save(): json.dump(data, open(state, 'w'))
if argv[:1] == ['run']:
    labels = {a.split('=', 1)[0]: a.split('=', 1)[1] for i, a in enumerate(argv) if i and argv[i - 1] == '--label'}
    name = argv[argv.index('--name') + 1]
    ident = os.environ.get('SHIM_ID', 'c' * 64)
    open(argv[argv.index('--cidfile') + 1], 'w').write(ident)
    data[ident] = {'name': name, 'labels': labels}
    if os.environ.get('SHIM_STEAL_NAME'):
        data['d' * 64] = {'name': name, 'labels': {'app': 'prod'}}; del data[ident]
    save(); print('ran'); sys.exit(int(os.environ.get('SHIM_EXIT', '0')))
if argv[:2] == ['container', 'inspect']:
    ref = argv[-1]
    for ident, item in data.items():
        if ref in (ident, item['name']):
            print(json.dumps(ident) + '|' + json.dumps(item['labels'])); sys.exit(0)
    sys.stderr.write('Error: No such container: ' + ref); sys.exit(1)
if argv[:2] == ['rm', '--force']:
    removed = data.pop(argv[2], None); save(); sys.exit(0 if removed else 1)
sys.exit(1)
'''

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-shim-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        bin_dir = self.base / 'bin'
        bin_dir.mkdir()
        shim = bin_dir / 'docker'
        shim.write_text(self.SHIM)
        shim.chmod(0o755)
        self.state = self.base / 'daemon.json'
        self.project = self.base / 'project'
        self.project.mkdir()
        environment = patch.dict(os.environ, {'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
                                              'SHIM_STATE': str(self.state)})
        environment.start()
        self.addCleanup(environment.stop)

    def daemon(self):
        return json.loads(self.state.read_text()) if self.state.exists() else {}

    @unittest.skipUnless(POSIX, 'shim needs POSIX')
    def test_the_container_is_created_with_labels_tracked_by_id_and_removed_by_id(self):
        folder = self.base / 'batch'
        adm.configure(folder, 'b', {})
        with adm.context(folder, 'task-1'):
            result = w.docker_execute(self.project, ['true'], 'sha256:img', 20)
        self.assertEqual(result['container_id'], 'c' * 64)
        self.assertEqual(result['container_cleanup'], 'removed')
        self.assertEqual(self.daemon(), {})
        self.assertEqual(adm.summary(folder)['tracked_processes'], [])

    @unittest.skipUnless(POSIX, 'shim needs POSIX')
    def test_a_stolen_name_is_never_removed_by_name(self):
        folder = self.base / 'batch'
        adm.configure(folder, 'b', {})
        with patch.dict(os.environ, {'SHIM_STEAL_NAME': '1'}), adm.context(folder, 'task-1'):
            result = w.docker_execute(self.project, ['true'], 'sha256:img', 20)
        self.assertEqual(result['container_cleanup'], 'gone')
        self.assertEqual(list(self.daemon()), ['d' * 64], 'the container that reused the name survives')

    @unittest.skipUnless(POSIX, 'shim needs POSIX')
    def test_inside_a_batch_an_unknown_identity_refuses_to_run_untracked(self):
        folder = self.base / 'batch'
        adm.configure(folder, 'b', {})
        with patch.dict(os.environ, {'SHIM_ID': 'not-an-id'}), adm.context(folder, 'task-1'):
            with self.assertRaisesRegex(ValueError, 'identity could not be established'):
                w.docker_execute(self.project, ['true'], 'sha256:img', 20)


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS') == '1' and os.environ.get('CREWLOOM_DOCKER_IMAGE'),
                     'real-container acceptance needs CREWLOOM_DOCKER_TESTS=1 and CREWLOOM_DOCKER_IMAGE (a local image)')
class RealContainerOwnership(unittest.TestCase):
    """Real disposable containers, each carrying a unique run label; only those ids are ever removed."""

    def setUp(self):
        self.image = os.environ['CREWLOOM_DOCKER_IMAGE']
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-real-container-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name) / 'batch'
        adm.configure(self.folder, 'real', {})
        self.created = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for ident in self.created:
            subprocess.run(['docker', 'rm', '--force', ident], capture_output=True, timeout=30)

    def start(self, name, labels):
        argv = ['docker', 'run', '-d', '--name', name, '--network', 'none']
        for key, value in labels.items():
            argv += ['--label', key + '=' + value]
        out = subprocess.run(argv + [self.image, 'sleep', '120'], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        ident = out.stdout.strip()
        self.created.append(ident)
        return ident

    def exists(self, ident):
        return subprocess.run(['docker', 'container', 'inspect', ident], capture_output=True, timeout=30).returncode == 0

    def test_owned_is_removed_and_a_reused_name_is_preserved(self):
        run = uuid.uuid4().hex
        labels = {'crewloom.owner': 'crewloom', 'crewloom.run': run}
        name = 'crewloom-test-' + run[:12]
        ident = self.start(name, labels)
        adm.track_process(self.folder, 'container', name, None, 'task', {'id': ident, 'labels': labels})
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'removed')
        self.assertFalse(self.exists(ident))
        stranger = self.start(name, {'owner': 'someone-else'})           # same name, different container
        adm.track_process(self.folder, 'container', name, None, 'task', {'id': ident, 'labels': labels})
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'gone')
        self.assertTrue(self.exists(stranger), 'a reused name must never remove the other container')

    def test_docker_execute_records_the_id_and_cancellation_removes_the_running_container(self):
        import threading
        project = Path(tempfile.mkdtemp(prefix='crewloom-real-project-'))
        self.addCleanup(lambda: __import__('shutil').rmtree(project, ignore_errors=True))
        outcome = {}

        def run():
            with adm.context(self.folder, 'cancel-task'):
                try:
                    outcome['result'] = w.docker_execute(project, ['python3', '-c', 'import time; time.sleep(60)'],
                                                         self.image, 90)
                except Exception as exc:  # reported through the assertions below
                    outcome['error'] = exc
        worker = threading.Thread(target=run)
        worker.start()
        deadline = time.monotonic() + 30
        tracked = {}
        while time.monotonic() < deadline and not tracked:
            tracked = {key: entry for key, entry in json.loads((self.folder / 'admission.json').read_text())['processes'].items()
                       if entry.get('kind') == 'container'}
            time.sleep(0.1)
        self.assertEqual(len(tracked), 1, 'the running container was recorded before it could be cancelled')
        entry = next(iter(tracked.values()))
        self.created.append(entry['container_id'])
        self.assertRegex(entry['container_id'], '^[0-9a-f]{64}$')
        self.assertTrue(self.exists(entry['container_id']))
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'removed')
        worker.join(60)
        self.assertFalse(self.exists(entry['container_id']))
        self.assertNotIn('error', outcome, outcome.get('error'))
        self.assertNotEqual(outcome['result']['exit_code'], 0, 'the cancelled command did not report success')


REAL_RUN = subprocess.run


class LaunchCandidateBounds(unittest.TestCase):
    def test_only_proven_older_environments_are_excluded_unknown_bounds_stay_unknown(self):
        clock = time.time(); token = uuid.uuid4().hex
        pid = os.getpid() + 100000
        timestamp = lambda value: time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(value))
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory); (proc / str(pid)).mkdir()
            denied = proc / str(pid) / 'environ'
            real_path = Path
            def path(value): return proc if value == '/proc' else real_path(value)
            with patch.object(adm.sys, 'platform', 'linux'), patch.object(adm, 'Path', side_effect=path), \
                    patch.object(real_path, 'open', side_effect=PermissionError('fixture protected environment')) as opening:
                table = {pid: {'start': timestamp(clock - 60)}}
                self.assertEqual(adm._launch_members(token, table, clock), {})
                opening.assert_not_called()
                for start, bound in ((timestamp(clock), clock), ('unknown', clock), (timestamp(clock - 60), None)):
                    with self.subTest(start=start, bound=bound), self.assertRaises(adm.ProcessObservationError):
                        adm._launch_members(token, {pid: {'start': start}}, bound)

    def test_kernel_proven_vanished_environment_is_absent_not_a_permission_failure(self):
        token = uuid.uuid4().hex; pid = os.getpid() + 100000
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory); (proc / str(pid)).mkdir(); real_path = Path
            with patch.object(adm.sys, 'platform', 'linux'), \
                    patch.object(adm, 'Path', side_effect=lambda value: proc if value == '/proc' else real_path(value)):
                for error in (FileNotFoundError(), ProcessLookupError()):
                    with self.subTest(error=type(error).__name__), patch.object(real_path, 'open', side_effect=error):
                        self.assertEqual(adm._launch_members(token, {pid: {'start': 'unknown'}}), {})

    @unittest.skipUnless(sys.platform.startswith('linux'), 'real protected /proc environment requires Linux')
    def test_real_preexisting_nondumpable_bystander_does_not_block_managed_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            code = 'import ctypes,time;assert ctypes.CDLL(None).prctl(4,0)==0;print("protected",flush=True);time.sleep(120)'
            bystander = subprocess.Popen([sys.executable, '-c', code], cwd=root, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(bystander.stdout.readline().strip(), 'protected')
                try:
                    with (Path('/proc') / str(bystander.pid) / 'environ').open('rb') as stream: stream.read(1)
                except PermissionError: pass
                else: self.skipTest('this host permits nondumpable environment inspection; negative precondition absent')
                with self.assertRaises(adm.ProcessObservationError):
                    adm._launch_members(uuid.uuid4().hex, adm._process_table())
                time.sleep(2.2)  # ps has second precision; establish the real pre-existing condition.
                folder = root / 'admission'; adm.configure(folder, 'linux-fixture', {})
                with adm.context(folder, 'fixture'):
                    target = adm.launch_owned([sys.executable, '-c', 'print("accepted")'], cwd=root,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
                    out, err = target.communicate(timeout=10)
                    self.assertEqual(target.returncode, 0, err); self.assertEqual(out.strip(), 'accepted')
                    self.assertIn(adm.settle_current_process(target.pid), ('gone', 'terminated', 'killed'))
                self.assertEqual(adm.summary(folder)['tracked_processes'], [])
                self.assertIsNone(bystander.poll(), 'unrelated protected process survives')
            finally:
                if bystander.poll() is None: bystander.kill()
                bystander.wait(timeout=10); bystander.stdout.close()


def failing_ps(mode):
    """A subprocess.run replacement that makes `ps` fail in one named way and leaves everything else real."""
    def run(argv, *args, **kwargs):
        if argv and argv[0] == 'ps':
            table = '-axo' in argv
            if mode == 'missing':
                raise FileNotFoundError('ps')
            if mode == 'timeout':
                raise subprocess.TimeoutExpired(argv, 10)
            if mode == 'nonzero':
                return subprocess.CompletedProcess(argv, 2, '', 'ps: internal failure')
            if mode == 'malformed':
                return subprocess.CompletedProcess(argv, 0, 'not a process table\n' if table else 'garbage\n', '')
            if mode == 'partial':  # a readable table that does not even list this process
                return subprocess.CompletedProcess(argv, 0, '999999 0 999999 Ss Thu Jan  1 00:00:00 2026\n' if table else '', '')
            if mode == 'empty':
                return subprocess.CompletedProcess(argv, 0, '', '')
        return REAL_RUN(argv, *args, **kwargs)
    return run


MODES = ('missing', 'timeout', 'nonzero', 'malformed', 'partial', 'empty')


@unittest.skipUnless(HAS_PS, 'process groups need POSIX and ps')
class ProcessInspectionFailure(unittest.TestCase):
    """Failing to look at a process is not evidence that it is gone (W09)."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-inspect-')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name) / 'batch'
        adm.configure(self.folder, 'batch-inspect', {})
        self.created = []
        self.addCleanup(self.reap)

    def reap(self):
        for process in self.created:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)

    def sleeper(self):
        process = subprocess.Popen(['sleep', '120'], start_new_session=True)
        self.created.append(process)
        return process

    def tracked(self, process, task='inspected'):
        adm.track_process(self.folder, 'process', process.pid, process.pid, task)
        return 'process:%d' % process.pid

    def test_each_inspection_failure_keeps_the_live_resource_tracked_and_unsignalled(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                process = self.sleeper()
                key = self.tracked(process)
                with patch.object(adm.subprocess, 'run', side_effect=failing_ps(mode)):
                    outcome = adm.terminate_owned(self.folder)
                self.assertEqual([o['key'] for o in outcome], [key])
                self.assertTrue(outcome[0]['result'].startswith('unverifiable: process inspection failed'), outcome)
                self.assertIsNone(process.poll(), 'the process was not signalled on an unverified observation')
                self.assertEqual(adm.summary(self.folder)['tracked_processes'], [key], 'the entry stays visible')
                healthy = adm.terminate_owned(self.folder)  # the next healthy attempt settles it
                self.assertIn(healthy[0]['result'], ('terminated', 'killed'))
                process.wait(timeout=10)
                self.assertEqual(adm.summary(self.folder)['tracked_processes'], [])

    def test_a_genuinely_exited_resource_settles_as_gone(self):
        process = self.sleeper()
        key = self.tracked(process)
        process.kill()
        process.wait(timeout=10)
        outcome = adm.terminate_owned(self.folder)
        self.assertEqual((outcome[0]['key'], outcome[0]['result']), (key, 'gone'))
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], [])

    def test_the_observation_distinguishes_present_absent_and_unknown(self):
        process = self.sleeper()
        state, start = adm.observe_process(process.pid)
        self.assertEqual(state, 'present')
        self.assertTrue(start)
        self.assertEqual(adm.pid_state(process.pid, start)[0], 'alive')
        self.assertEqual(adm.pid_state(process.pid, 'Thu Jan  1 00:00:00 1970')[0], 'dead', 'a different start is a different process')
        process.kill()
        process.wait(timeout=10)
        self.assertEqual(adm.observe_process(process.pid), ('absent', None))
        self.assertEqual(adm.pid_state(process.pid, start)[0], 'dead')
        for mode in MODES[:4]:
            with patch.object(adm.subprocess, 'run', side_effect=failing_ps(mode)):
                self.assertEqual(adm.observe_process(os.getpid())[0], 'unknown', mode)
                self.assertEqual(adm.pid_state(os.getpid())[0], 'unknown', mode)
                self.assertFalse(adm.pid_alive(os.getpid()), 'unknown is not claimed alive either')
                self.assertIsNone(adm.process_start(os.getpid()))
        with patch.object(adm.subprocess, 'run', side_effect=failing_ps('empty')):
            self.assertEqual(adm.observe_process(os.getpid())[0], 'unknown', 'silence with exit 0 proves nothing')
        self.assertEqual(adm.observe_process('not-a-pid')[0], 'unknown')

    def test_a_process_whose_identity_cannot_be_read_is_not_tracked_at_all(self):
        process = self.sleeper()
        for mode in MODES:
            with self.subTest(mode=mode), patch.object(adm.subprocess, 'run', side_effect=failing_ps(mode)):
                with self.assertRaisesRegex(adm.AdmissionError, 'cannot be verified'):
                    adm.track_process(self.folder, 'process', process.pid, process.pid, 'unreadable')
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], [])
        self.assertIsNone(process.poll())

    def test_a_process_that_exited_before_tracking_is_tracked_without_an_identity_and_never_matches_a_reused_pid(self):
        process = self.sleeper()
        process.kill()
        process.wait(timeout=10)
        key = self.tracked(process, 'already-gone')
        entry = json.loads((self.folder / 'admission.json').read_text())['processes'][key]
        self.assertIsNone(entry['pid_start'])
        reused = self.sleeper()
        record = json.loads((self.folder / 'admission.json').read_text())
        record['processes'][key]['pid'] = reused.pid  # a different live process now holds the recorded pid
        (self.folder / 'admission.json').write_text(json.dumps(record))
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'gone')
        self.assertIsNone(reused.poll(), 'a process with no recorded identity is never assumed to be ours')

    def test_restart_recovery_with_an_unreadable_controller_preserves_the_entry(self):
        process = self.sleeper()
        key = self.tracked(process, 'orphan-candidate')
        record = json.loads((self.folder / 'admission.json').read_text())
        record['processes'][key].update(controller_pid=2 ** 22 + 4242, controller_start='gone')
        (self.folder / 'admission.json').write_text(json.dumps(record))
        with patch.object(adm.subprocess, 'run', side_effect=failing_ps('nonzero')):
            report = adm.recover(self.folder)
        self.assertTrue(report['stopped'][0]['result'].startswith('unverifiable'), report)
        self.assertIsNone(process.poll())
        self.assertEqual(adm.summary(self.folder)['tracked_processes'], [key])
        healthy = adm.recover(self.folder)
        self.assertIn(healthy['stopped'][0]['result'], ('terminated', 'killed'))
        process.wait(timeout=10)

    def test_an_owner_that_cannot_be_checked_is_not_orphaned_on_a_guess(self):
        self.assertEqual(adm.admit(self.folder, 'req-1', {})['decision'], 'admitted')
        path = self.folder / 'admission.json'
        record = json.loads(path.read_text())
        record['requests']['req-1']['owner'].update(pid=2 ** 22 + 4242, pid_start='gone')  # an owner that is not running
        path.write_text(json.dumps(record))
        with patch.object(adm.subprocess, 'run', side_effect=failing_ps('timeout')):
            report = adm.recover(self.folder)
        self.assertEqual(report['orphaned_requests'], [])
        self.assertEqual([u['request'] for u in report['unverified_owners']], ['req-1'])
        self.assertEqual(json.loads(path.read_text())['requests']['req-1']['state'], 'dispatched')
        report = adm.recover(self.folder)  # a healthy observation proves the owner is not running
        self.assertEqual(report['orphaned_requests'], ['req-1'])
        self.assertEqual(report['unverified_owners'], [])

    def test_reaping_a_group_never_claims_a_clean_result_it_could_not_observe(self):
        process = self.sleeper()
        with patch.object(adm.subprocess, 'run', side_effect=failing_ps('missing')):
            survivors = adm.reap_group(process.pid, time.time() - 60, grace=0.2)
        self.assertTrue(survivors and str(survivors[0]).startswith('unverified'), survivors)
        self.assertIsNone(process.poll())
        self.assertEqual(adm.reap_group(process.pid, time.time() - 60), [])
        process.wait(timeout=10)



@unittest.skipUnless(HAS_PS, 'acknowledged launch requires POSIX and process inspection')
class AcknowledgedLaunch(unittest.TestCase):
    setUp = OwnedProcessTree.setUp
    reap = OwnedProcessTree.reap
    unrelated = OwnedProcessTree.unrelated
    assert_gone = OwnedProcessTree.assert_gone

    def test_tracking_failure_never_runs_the_target_and_keeps_the_intent(self):
        target = self.base / 'side-effect'
        with adm.context(self.folder, 'launch-task'), patch.object(adm, 'track_process', side_effect=adm.AdmissionError('disk unavailable')):
            with self.assertRaisesRegex(adm.AdmissionError, 'disk unavailable'):
                adm.launch_owned([sys.executable, '-c', 'open(__import__("sys").argv[1],"w").write("bad")', str(target)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.assertFalse(target.exists())
        self.assertTrue(any(key.startswith('launch:') for key in adm.summary(self.folder)['tracked_processes']))
        self.assertEqual(adm.terminate_owned(self.folder)[0]['result'], 'gone')

    def test_acknowledgement_does_not_consume_the_target_prompt(self):
        with adm.context(self.folder, 'payload-task'):
            process = adm.launch_owned([sys.executable, '-c', 'import sys;print(sys.stdin.read())'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            output, error = process.communicate('prompt with Arabic: مرحبا', timeout=10)
        self.assertEqual(process.returncode, 0, error)
        self.assertEqual(output.strip(), 'prompt with Arabic: مرحبا')
        record = json.loads((self.folder / 'admission.json').read_text())
        self.assertIn('launch_token', record['processes']['process:%d' % process.pid])
        self.assertFalse(any(key.startswith('launch:') for key in record['processes']))
        adm.terminate_owned(self.folder)

    def test_escaped_child_after_leader_exit_is_stopped_and_bystander_survives(self):
        bystander = self.unrelated()
        code = 'import subprocess,sys; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(120)"],start_new_session=True);print(p.pid,flush=True)'
        with adm.context(self.folder, 'escape-task'):
            parent = adm.launch_owned([sys.executable, '-c', code], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            # The child inherits output descriptors, so read one line rather than communicate.
            child = int(parent.stdout.readline().strip())
            self.spawned.append(child)
            parent.wait(timeout=10)
        self.assertTrue(alive(child), 'the negative precondition is a real escaped surviving child')
        result = adm.terminate_owned(self.folder)
        self.assertIn(result[0]['result'], ('terminated', 'killed'))
        self.assert_gone([child])
        self.assertIsNone(bystander.poll(), 'an unrelated process is never selected by launch ownership')
        parent.stdin.close(); parent.stdout.close(); parent.stderr.close()

    def test_controller_death_before_identity_commit_never_releases_target(self):
        target = self.base / 'unreleased-target'
        target_code = 'import sys;open(sys.argv[1],"w").write("bad")'
        code = ('import admission as a,subprocess,sys,os; '
                'a.configure(sys.argv[1],"crash-test",{}); '
                'a.track_process=lambda *args,**kwargs: os._exit(73); '
                'c=a.context(sys.argv[1],"crash-task");c.__enter__(); '
                'a.launch_owned([sys.executable,"-c",' + repr(target_code) + ',sys.argv[2]],stdin=subprocess.PIPE,text=True,start_new_session=True)')
        folder = self.base / 'crash-ledger'
        controller = subprocess.run([sys.executable, '-c', code, str(folder), str(target)],
            env={**os.environ, 'PYTHONPATH': str(Path(adm.__file__).parent)}, timeout=10, capture_output=True, text=True)
        self.assertEqual(controller.returncode, 73, controller.stderr)
        self.assertFalse(target.exists())
        report = adm.recover(folder)
        self.assertTrue(report['stopped'])
        self.assertTrue(all(item['result'] in ('gone', 'terminated', 'killed') for item in report['stopped']), report)
        self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
