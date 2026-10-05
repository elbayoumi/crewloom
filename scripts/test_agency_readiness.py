"""Read-only agency rollout readiness: registration, evidence freshness and no mutation.

Every fixture is a synthetic public agency workspace. The private client inventory is never
read here, and the suite proves the reporter's central claim by comparing a full filesystem
snapshot of every path, kind, mode, size, mtime and content digest before and after a run.
"""
import contextlib
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import agency_readiness as readiness
import project_binding as pb
import repo_map

ROLE = 'context-guardian'
PROJECT_ID = 'readiness-client'
REGISTRY_RELATIVE = '.agents/project-control/registry.json'
SNAPSHOT = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)


def snapshot(root):
    """Every path under one root with its kind, mode, size, mtime and content digest."""
    state = {}
    for path in sorted(root.rglob('*')):
        relative = str(path.relative_to(root))
        info = path.lstat()
        kind = 'link' if path.is_symlink() else ('dir' if path.is_dir() else 'file')
        entry = {'kind': kind, 'mode': oct(info.st_mode), 'size': info.st_size,
                 'mtime_ns': info.st_mtime_ns}
        if kind == 'file':
            entry['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        state[relative] = entry
    return state


class AgencyReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crewloom-readiness-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.agency = self.base / 'agency'
        self.project = self.agency / 'clients' / 'active' / PROJECT_ID
        self.project.mkdir(parents=True)
        for base in (self.agency, self.project):
            self.install_role(base)
        (self.project / 'context-snapshot.md').write_text('# snapshot\n', encoding='utf-8')
        self.evidence = self.project / 'state-evidence.md'
        self.evidence.write_text('# observed state\n', encoding='utf-8')
        self.registry = self.agency / REGISTRY_RELATIVE
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        self.write_registry()
        self.enroll()

    def install_role(self, base):
        folder = base / '.agents' / 'skills' / ROLE
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'SKILL.md').write_text('# ' + ROLE + '\n', encoding='utf-8')

    def entry(self, status='in_progress', observed=SNAPSHOT - timedelta(minutes=5), evidence=True, **changes):
        """One exact ledger entry: the fixture uses the same schema the adapter validates."""
        entry = {'id': PROJECT_ID,
                 'active_dir': str(self.project.relative_to(self.agency)),
                 'context_snapshot': str((self.project / 'context-snapshot.md').relative_to(self.agency)),
                 'delivery_owner': ROLE, 'control_status': status,
                 'last_verified_at': None if status in pb.AGENCY_EVIDENCE_ONLY
                 else observed.isoformat(timespec='seconds'),
                 'next_action': {'owner': ROLE, 'output': 'handoff.md',
                                 'acceptance': 'state evidence recorded and unchanged'}}
        if evidence and status not in pb.AGENCY_EVIDENCE_ONLY:
            entry['state_evidence'] = {'path': str(self.evidence.relative_to(self.agency)),
                                       'sha256': pb.file_digest(self.evidence),
                                       'source_type': 'staging_observation',
                                       'observed_at': observed.isoformat(timespec='seconds')}
        entry.update(changes)
        return entry

    def write_registry(self, entries=None, schema_version=1):
        data = {'schema_version': schema_version, 'projects': [self.entry()] if entries is None else entries}
        self.registry.write_text(json.dumps(data, indent=2), encoding='utf-8')
        return data

    def current_registry(self):
        """The same entry recorded against the real UTC clock, for runs that inject no clock."""
        self.write_registry([self.entry(observed=datetime.now(timezone.utc) - timedelta(minutes=5))])

    def enroll(self, project_id=PROJECT_ID):
        """A bound project fixture; the reporter reads this state and never creates it."""
        (self.project / pb.CONFIG_NAME).write_text(json.dumps(pb.default_config(project_id), indent=2),
                                                  encoding='utf-8')
        runtime = self.project / '.crewloom'
        runtime.mkdir(exist_ok=True)
        (runtime / 'binding.json').write_text(json.dumps(
            {'schema_version': pb.SCHEMA_VERSION, 'project_id': project_id, 'checkout_id': 'a1' * 16,
             'project_root': str(self.project), 'config_path': pb.CONFIG_NAME, 'relocations': []},
            indent=2), encoding='utf-8')

    def report(self, project_id=PROJECT_ID, root=None, now=SNAPSHOT, limit=86400, **changes):
        return readiness.report(project_id, self.project if root is None else root, self.agency,
                                 self.registry, max_evidence_age_seconds=limit, now=now, **changes)

    def cli(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = readiness.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def base_arguments(self, project_id=PROJECT_ID, root=None):
        return ['--project-id', project_id, '--project-root', str(self.project if root is None else root),
                '--agency-root', str(self.agency), '--registry', str(self.registry)]

    def details(self, payload):
        return ' | '.join(item['detail'] for item in payload['problems'])

    def test_ready_project_reports_registration_and_current_evidence(self):
        payload = self.report()
        self.assertEqual(payload['outcome'], 'ready')
        self.assertTrue(payload['ready'])
        self.assertEqual(payload['exit_code'], readiness.EXIT_READY)
        self.assertEqual(payload['problems'], [])
        self.assertEqual(payload['control_status'], 'in_progress')
        self.assertFalse(payload['evidence_only'])
        self.assertEqual(payload['registry']['matched_entries'], 1)
        self.assertEqual(payload['registry']['matched_ids'], [PROJECT_ID])
        self.assertEqual(payload['registry']['sha256'], pb.file_digest(self.registry))
        self.assertTrue(payload['current_evidence']['digest_matches'])
        self.assertEqual(payload['current_evidence']['current_sha256'], pb.file_digest(self.evidence))
        self.assertEqual(payload['timestamps']['last_verified_at']['age_seconds'], 300.0)
        self.assertTrue(payload['timestamps']['last_verified_at']['within_limit'])
        self.assertTrue(payload['setup']['enrolled'])
        self.assertEqual(payload['ownership']['delivery_owner'], ROLE)
        self.assertEqual(payload['mode'], 'read-only')
        self.assertIn(payload['outcome'], readiness.OUTCOMES)
        scope = ' '.join(payload['scope'])
        self.assertIn('whose current digest still equals the recorded digest', scope)
        limitations = ' '.join(payload['limitations'])
        for honest in ('delivery', 'host configuration', 'not verified'):
            self.assertIn(honest, limitations)

    def test_needs_reconciliation_is_reported_and_never_improved(self):
        self.write_registry([self.entry(status='needs_reconciliation', evidence=False)])
        before = snapshot(self.base)
        payload = self.report()
        self.assertEqual(payload['outcome'], 'needs_reconciliation')
        self.assertFalse(payload['ready'])
        self.assertEqual(payload['exit_code'], readiness.EXIT_NOT_READY)
        self.assertTrue(payload['evidence_only'])
        self.assertIn('control_status', [item['field'] for item in payload['problems']])
        self.assertIn('never reconciled', self.details(payload))
        self.assertEqual(snapshot(self.base), before)

    def test_missing_explicit_identity_is_refused_and_never_inferred(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            readiness.main(['--project-root', str(self.project), '--agency-root', str(self.agency),
                            '--registry', str(self.registry)])
        self.assertEqual(error.exception.code, 2)
        code, out, _ = self.cli(self.base_arguments(project_id='other-client'))
        payload = json.loads(out)
        self.assertEqual(code, readiness.EXIT_NOT_READY)
        self.assertEqual(payload['outcome'], 'not_ready')
        self.assertIn('identity', [item['kind'] for item in payload['problems']])
        self.assertEqual(payload['registry']['matched_entries'], 1)

    def test_current_evidence_must_match_the_real_file_not_only_a_stored_digest(self):
        self.evidence.write_text('# changed after observation\n', encoding='utf-8')
        payload = self.report()
        self.assertEqual(payload['outcome'], 'not_ready')
        self.assertIn('hash', [item['kind'] for item in payload['problems']])
        self.assertNotEqual(payload['current_evidence']['current_sha256'],
                            payload['current_evidence']['recorded_sha256'])
        self.assertFalse(payload['current_evidence']['digest_matches'])
        self.evidence.write_text('# observed state\n', encoding='utf-8')
        self.assertEqual(self.report()['outcome'], 'ready')

    def test_empty_missing_and_foreign_state_evidence_are_reported(self):
        self.evidence.write_text('', encoding='utf-8')
        self.write_registry([self.entry()])
        self.assertIn('state_evidence.path', self.details(self.report()))
        self.evidence.unlink()
        empty = self.report()
        self.assertIn('does not exist', self.details(empty))
        self.evidence.write_text('# observed state\n', encoding='utf-8')
        entry = self.entry()
        entry['state_evidence'] = {'path': '../outside.md', 'sha256': 'a' * 64,
                                   'source_type': 'staging_observation',
                                   'observed_at': (SNAPSHOT - timedelta(minutes=5)).isoformat()}
        self.write_registry([entry])
        self.assertIn('escapes', self.details(self.report()))

    def test_non_iso_and_naive_timestamps_are_refused_separately(self):
        for value, expected in (('not-a-date', 'not a parseable ISO-8601'),
                                ('2026-10-04T11:55:00', 'no timezone offset')):
            with self.subTest(value=value):
                self.write_registry([self.entry(last_verified_at=value)])
                payload = self.report()
                self.assertEqual(payload['outcome'], 'not_ready')
                self.assertIn(expected, self.details(payload))
        entry = self.entry()
        entry['state_evidence']['observed_at'] = '2026-10-04T11:55:00'
        self.write_registry([entry])
        self.assertIn('no timezone offset', self.details(self.report()))

    def test_evidence_older_than_the_explicit_limit_is_stale(self):
        self.assertEqual(self.report(now=SNAPSHOT + timedelta(seconds=3300), limit=3600)['outcome'],
                         'ready')
        stale = self.report(now=SNAPSHOT + timedelta(hours=2), limit=3600)
        self.assertEqual(stale['outcome'], 'not_ready')
        self.assertEqual(stale['timestamps']['last_verified_at']['within_limit'], False)
        self.assertEqual(stale['timestamps']['state_evidence.observed_at']['within_limit'], False)
        self.assertEqual([item['kind'] for item in stale['problems']], ['stale', 'stale'])
        self.assertIn('explicit evidence age limit', self.details(stale))
        self.assertEqual(self.report(now=SNAPSHOT + timedelta(hours=2), limit=7500)['outcome'], 'ready')
        future = self.report(now=SNAPSHOT - timedelta(hours=2), limit=86400)
        self.assertIn('in the future', self.details(future))

    def test_duplicate_unknown_and_unregistered_entries_block_readiness(self):
        self.write_registry([self.entry(), dict(self.entry(active_dir='clients/active/other-client'))])
        duplicate = self.report()
        self.assertNotEqual(duplicate['outcome'], 'ready')
        self.assertIn('unique lowercase identifier', self.details(duplicate))
        self.write_registry([self.entry(unexpected_field=True)])
        self.assertIn('unknown fields', self.details(self.report()))
        other = self.base / 'elsewhere'
        other.mkdir()
        payload = self.report(root=other)
        self.assertEqual(payload['outcome'], 'not_ready')
        self.assertIn('No registered entry resolves', self.details(payload))
        self.assertEqual(payload['registry']['matched_entries'], 0)

    def test_uninstalled_owner_role_is_reported_as_an_ownership_problem(self):
        self.write_registry([self.entry(delivery_owner='unknown-role')])
        payload = self.report()
        self.assertNotEqual(payload['outcome'], 'ready')
        self.assertIn('ownership', [item['kind'] for item in payload['problems']])
        self.assertIn('installed role', self.details(payload))

    def test_every_registry_problem_is_reported_rather_than_one_joined_message(self):
        broken = [self.entry(control_status='active', delivery_owner='unknown-role'),
                  self.entry(id='second-client', active_dir='clients/active/second-client')]
        self.write_registry(broken)
        payload = self.report()
        kinds = [item['kind'] for item in payload['problems']]
        self.assertEqual(set(kinds), set(kinds) & set(readiness.PROBLEM_KINDS))
        self.assertGreaterEqual(payload['problem_count'], 4)
        self.assertEqual(set(kinds), {'status', 'ownership', 'path'})
        self.assertEqual(payload['control_status'], 'active')
        self.assertIn('control_status', self.details(payload))
        self.assertIn('delivery_owner', self.details(payload))
        self.assertIn('projects[1]', self.details(payload))

    def test_unenrolled_project_reports_required_setup_without_bootstrapping(self):
        (self.project / pb.CONFIG_NAME).unlink()
        (self.project / pb.BINDING_RELATIVE).unlink()
        (self.project / '.crewloom').rmdir()
        before = snapshot(self.base)
        payload = self.report()
        self.assertNotEqual(payload['outcome'], 'ready')
        self.assertIn('Required setup', self.details(payload))
        self.assertFalse(payload['setup']['enrolled'])
        self.assertEqual(sorted(payload['missing_fields']), [pb.BINDING_RELATIVE, pb.CONFIG_NAME])
        self.assertEqual(snapshot(self.base), before)
        self.assertFalse((self.project / '.crewloom').exists())
        self.assertFalse((self.project / 'AGENTS.md').exists())

    def test_default_invocation_writes_no_file_and_no_metadata(self):
        (self.project / pb.CONFIG_NAME).unlink()
        (self.project / pb.BINDING_RELATIVE).unlink()
        (self.project / '.crewloom').rmdir()
        self.current_registry()
        git = shutil.which('git')
        if git:
            subprocess.run([git, 'init', '-q', str(self.agency)], check=True, capture_output=True,
                           env=repo_map.git_environment())
        before = snapshot(self.base)
        self.assertIn('.git', ''.join(before))
        code, out, _ = self.cli(self.base_arguments())
        payload = json.loads(out)
        self.assertEqual(payload['write']['status'], 'not_requested')
        self.assertEqual(code, readiness.EXIT_NOT_READY)
        self.assertEqual(snapshot(self.base), before)
        self.assertFalse((self.project / '.crewloom').exists())
        self.assertFalse([name for name in snapshot(self.base) if '__pycache__' in name])
        self.enroll()
        enrolled = snapshot(self.base)
        ready_payload = json.loads(self.cli(self.base_arguments())[1])
        self.assertEqual(ready_payload['outcome'], 'ready')
        self.assertEqual(ready_payload['exit_code'], readiness.EXIT_READY)
        self.assertEqual(snapshot(self.base), enrolled)

    def test_symlinked_hardlinked_and_foreign_registry_paths_fail_before_any_write(self):
        target = self.base / 'outside-registry.json'
        target.write_text(json.dumps(self.write_registry()), encoding='utf-8')
        linked = self.agency / 'linked-registry.json'
        linked.symlink_to(target)
        hard = self.agency / 'hard-registry.json'
        os.link(self.registry, hard)
        before = snapshot(self.base)
        for registry, expected in ((linked, 'symlinked'), (target, 'escapes'), (hard, 'hardlink')):
            with self.subTest(registry=registry.name):
                argv = self.base_arguments()
                argv[argv.index('--registry') + 1] = str(registry)
                payload = json.loads(self.cli(argv)[1])
                self.assertEqual(payload['outcome'], 'blocked')
                self.assertIn(expected, self.details(payload))
                self.assertEqual(snapshot(self.base), before)

    def test_hardlinked_state_evidence_is_an_ownership_problem(self):
        foreign = self.base / 'foreign-evidence.md'
        foreign.write_bytes(self.evidence.read_bytes())
        os.remove(self.evidence)
        os.link(foreign, self.evidence)
        payload = self.report()
        self.assertNotEqual(payload['outcome'], 'ready')
        self.assertIn('ownership', [item['kind'] for item in payload['problems']])
        self.assertIn('hardlink', self.details(payload))
        self.assertEqual(payload['current_evidence']['hardlinks'], 2)

    def test_explicit_report_write_is_owner_only_and_inside_the_project_runtime(self):
        self.current_registry()
        runtime = self.project / '.crewloom' / 'readiness'
        runtime.mkdir(parents=True)
        destination = '.crewloom/readiness/report.json'
        code, out, _ = self.cli(self.base_arguments() + ['--report-out', destination])
        payload = json.loads(out)
        self.assertEqual(code, readiness.EXIT_READY)
        self.assertEqual(payload['write']['status'], 'written')
        stored = self.project / destination
        self.assertEqual(stored.read_text(encoding='utf-8'), out)
        self.assertEqual(oct(stored.stat().st_mode & 0o777), oct(0o600))
        self.assertEqual(json.loads(stored.read_text(encoding='utf-8'))['outcome'], 'ready')
        self.assertEqual([name for name in snapshot(self.project / '.crewloom') if name.endswith('.tmp')], [])

    def test_report_destinations_outside_the_selected_project_runtime_are_refused(self):
        self.current_registry()
        runtime = self.project / '.crewloom' / 'readiness'
        runtime.mkdir(parents=True)
        foreign = self.base / 'other-project'
        (foreign / '.crewloom').mkdir(parents=True)
        outside = (foreign / '.crewloom' / 'report.json')
        linked = runtime / 'linked.json'
        linked.symlink_to(outside)
        hard = runtime / 'hard.json'
        hard.write_text('{}\n', encoding='utf-8')
        os.link(hard, runtime / 'hard-alias.json')
        cases = [('report.json', 'only be written inside'),
                 ('../other-project/.crewloom/report.json', 'escapes selected project'),
                 ('.git/readiness.json', 'Git state'),
                 ('.crewloom/readiness/linked.json', 'linked.json'),
                 ('.crewloom/readiness/hard.json', 'hardlink'),
                 ('.crewloom/readiness/absent/report.json', 'Create the owned readiness directory'),
                 ('.crewloom/binding.json', 'only be written inside'),
                 ('.crewloom/reviewers.json', 'only be written inside'),
                 ('.crewloom/active_task.json', 'only be written inside'),
                 ('.crewloom/coordinators/batch/state.json', 'only be written inside'),
                 ('.crewloom/readiness/../binding.json', 'must stay inside')]
        before = snapshot(self.base)
        for destination, expected in cases:
            with self.subTest(destination=destination):
                code, out, err = self.cli(self.base_arguments() + ['--report-out', destination])
                payload = json.loads(out)
                self.assertEqual(code, readiness.EXIT_NOT_READY)
                self.assertEqual(payload['write']['status'], 'refused')
                self.assertIn(expected, err)
                self.assertIn(expected, payload['write']['error'])
        self.assertFalse(outside.exists())
        self.assertEqual(hard.read_text(encoding='utf-8'), '{}\n')
        self.assertEqual(snapshot(self.base), before)

    def test_a_report_is_never_stored_for_an_unregistered_project(self):
        runtime = self.project / '.crewloom' / 'readiness'
        runtime.mkdir(parents=True)
        other = self.base / 'elsewhere'
        other.mkdir()
        payload = self.report(root=other)
        with self.assertRaisesRegex(ValueError, 'not stored'):
            readiness.store_report(payload, None, '.crewloom/readiness/report.json')
        ready = self.report()
        with self.assertRaisesRegex(ValueError, 'produced by this reporter'):
            readiness.store_report({'tool': 'other', 'mode': 'read-only'}, self.project,
                                  '.crewloom/readiness/report.json')
        with self.assertRaisesRegex(ValueError, 'same canonical project'):
            readiness.store_report(ready, other, '.crewloom/readiness/report.json')
        self.assertFalse((other / '.crewloom').exists())

    def test_report_is_deterministic_for_one_fixed_clock(self):
        first = json.dumps(self.report(), sort_keys=True)
        second = json.dumps(self.report(), sort_keys=True)
        self.assertEqual(first, second)
        self.assertNotEqual(json.dumps(self.report(now=SNAPSHOT + timedelta(days=1)), sort_keys=True), first)

    def test_malformed_input_and_broken_ledger_are_reported_without_a_traceback(self):
        self.registry.write_text('{not json', encoding='utf-8')
        code, out, err = self.cli(self.base_arguments())
        self.assertEqual(code, readiness.EXIT_NOT_READY)
        self.assertEqual(json.loads(out)['outcome'], 'not_ready')
        self.assertIn('unreadable', err + out)
        argv = self.base_arguments() + ['--max-evidence-age-seconds', '99999999']
        self.registry.write_text(json.dumps(self.write_registry()), encoding='utf-8')
        code, out, err = self.cli(argv)
        self.assertEqual(code, readiness.EXIT_NOT_READY)
        self.assertEqual(json.loads(out)['outcome'], 'error')
        self.assertIn('Evidence age limit', err)
        self.registry.write_text(json.dumps(self.write_registry()), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Explicit registered project ID'):
            readiness.report('Not A Project', self.project, self.agency, self.registry)
        self.assertEqual(readiness.report(PROJECT_ID, self.base / 'absent', self.agency, self.registry,
                                          max_evidence_age_seconds=86400, now=SNAPSHOT)['outcome'],
                         'blocked')

    def test_the_mutating_external_agency_validator_is_never_run(self):
        validator = self.agency / 'agency-validator.py'
        validator.write_text('raise SystemExit(3)\n', encoding='utf-8')
        self.current_registry()
        (self.project / '.crewloom' / 'readiness').mkdir(parents=True)
        with patch.object(pb, 'run_agency_validator', side_effect=AssertionError('validator ran')) as run:
            payload = self.report(now=datetime.now(timezone.utc))
            code, out, _ = self.cli(self.base_arguments() + ['--report-out', '.crewloom/readiness/r.json'])
        self.assertEqual(payload['outcome'], 'ready')
        self.assertEqual(json.loads(out)['write']['status'], 'written')
        self.assertEqual(code, readiness.EXIT_READY)
        self.assertEqual(run.call_count, 0)
        self.assertEqual(validator.read_text(encoding='utf-8'), 'raise SystemExit(3)\n')

    def test_the_reporter_runs_no_process_network_or_host_command(self):
        source = (Path(readiness.__file__).resolve()).read_text(encoding='utf-8')
        for forbidden in ('import subprocess', 'import socket', 'import urllib', 'import http',
                          'os.system', 'os.popen', 'os.exec', 'eval(', 'exec(', 'shutil.rmtree'):
            self.assertNotIn(forbidden, source)
        for allowed in ('import project_binding as pb', 'import workflow as w',
                        'pb.validate_agency_registry', 'pb.agency_registry', 'datetime.now(timezone.utc)'):
            self.assertIn(allowed, source)

    def test_arabic_labels_never_change_the_machine_keys(self):
        english = self.report()
        arabic = self.report(language='ar')
        self.assertNotEqual(english['labels'], arabic['labels'])
        for key in ('outcome', 'ready', 'control_status', 'problems', 'missing_fields', 'exit_code'):
            self.assertEqual(english[key], arabic[key])
        self.assertEqual(sorted(english['scope']), sorted(arabic['scope']))


if __name__ == '__main__':
    unittest.main()
