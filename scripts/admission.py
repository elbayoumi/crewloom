#!/usr/bin/env python3
"""Aggregate admission, budgets, queued dispatch and owned-process cancellation for a batch (W09).

The checkout request ceiling in the workflow ledger is per worktree. A coordinated batch runs
several worktrees at once, so this module keeps one persisted, atomically updated ledger in the
batch's coordinator folder. A request is reserved before dispatch and reconciled after it; a
reservation is idempotent by request id (a resume never double charges or hands out a
replacement slot); a dispatch whose owner died is `orphaned`, still charged and never
replayed. Token and cost figures stay `None` unless a provider reported them, and estimates
are always labelled apart from recorded usage. Processes and containers the batch itself
started are recorded with an identity, so cancellation stops exactly those and nothing else:
a process is recorded with its start time and process group and is stopped as a verified tree (group
members plus descendants); a container is recorded with its immutable ID and ownership labels and is
removed by that ID only after inspection shows the same ID and labels. Tracking inside a batch is
required: a failure to record raises instead of letting an unowned resource run.

Limit contracts (each is a distinct promise, not a synonym):
  max_output_tokens              aggregate reservation: the sum of the output ceilings of every charged
                                 request (its reserved ceiling, replaced by provider-reported output
                                 once settled) never exceeds this. A request whose ceiling is unknown or
                                 that its host cannot enforce is refused while this is set.
  max_output_tokens_per_request  the ceiling each request is told to honor; it never exceeds this.
  max_elapsed_seconds            an admission deadline: new requests are refused after it, work already
                                 in flight is not stopped by it.
  max_input_bytes                an estimate of prompt bytes, not provider-billed tokens.
Provider-reported usage and cost are accounting, never enforcement: there is no cost cap because no
price table exists here, and activity outside the managed controller is neither counted nor capped.
"""
import json
import math
import os
import re
import signal
import subprocess
import sys
import uuid
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None

SCHEMA_VERSION = 1
LIMIT_KEYS = ('max_model_requests', 'max_concurrent_requests', 'max_elapsed_seconds',
              'max_input_bytes', 'max_output_tokens', 'max_output_tokens_per_request')
USAGE_TOKEN_KEYS = ('input_tokens', 'output_tokens', 'total_tokens')
USAGE_KEYS = USAGE_TOKEN_KEYS + ('cost_usd',)
CHARGED = ('dispatched', 'succeeded', 'failed', 'orphaned')
_local = threading.local()
_windows_jobs = {}
_jobs_lock = threading.Lock()


class AdmissionError(ValueError):
    pass


def now():
    return time.time()


def validate_limits(limits):
    """Every limit is a positive integer or an explicit null (reported as unbounded)."""
    if limits is None:
        limits = {}
    if not isinstance(limits, dict) or set(limits) - set(LIMIT_KEYS):
        raise AdmissionError('Budget fields must be a subset of: ' + ', '.join(LIMIT_KEYS))
    for key, value in limits.items():
        if value is not None and (type(value) is not int or value < 1):
            raise AdmissionError(key + ' must be a positive integer or null')
    return {key: limits.get(key) for key in LIMIT_KEYS}


class ProcessObservationError(AdmissionError):
    """The process table could not be read completely; presence and absence are both unknown."""


LSTART = re.compile(r'[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4}')


def _run_ps(argv):
    """(completed process, problem). A problem means ps itself did not give an answer."""
    try:
        return subprocess.run(['ps', *argv], capture_output=True, text=True, timeout=10), None
    except OSError as exc:
        return None, 'ps is unavailable (%s)' % exc.__class__.__name__
    except subprocess.SubprocessError as exc:
        return None, 'ps did not complete (%s)' % exc.__class__.__name__


def observe_process(pid):
    """('present', start) | ('absent', None) | ('unknown', reason): what ps proves about one pid.

    Absence is only what ps says when it answered cleanly that no such process exists. A missing ps, a timeout,
    an unexpected exit status or unreadable output is `unknown`, never `absent`. A zombie (exited, not yet
    reaped) is absent for every purpose here."""
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return 'unknown', 'the recorded pid is not an integer'
    if os.name == 'nt':
        from process_backend import observe
        return observe(number)
    result, problem = _run_ps(['-o', 'stat=,lstart=', '-p', str(number)])
    if problem:
        return 'unknown', problem
    text = result.stdout.strip()
    if result.returncode == 0 and text:
        state, _, started = text.partition(' ')
        started = ' '.join(started.split())
        if not state or not LSTART.fullmatch(started):
            return 'unknown', 'ps output for pid %d is unreadable' % number
        return ('absent', None) if state.startswith('Z') else ('present', started)
    complaint = result.stderr.strip().lower()
    if result.returncode == 1 and not text and (not complaint or re.search(r'too large|out of range', complaint)):
        return 'absent', None  # no such process, or an id beyond the kernel's range: either way nothing runs under it
    return 'unknown', 'ps exited %d for pid %d%s' % (result.returncode, number,
                                                    (': ' + result.stderr.strip()[:80]) if result.stderr.strip() else '')


def process_start(pid):
    """An identity for a pid that survives pid reuse: its reported start time, or None if not proven present."""
    state, value = observe_process(pid)
    return value if state == 'present' else None


def pid_state(pid, start=None):
    """('alive' | 'dead' | 'unknown', reason): `dead` means proven absent or proven a different process."""
    state, value = observe_process(pid)
    if state == 'unknown':
        return 'unknown', value
    if state == 'absent' or (start is not None and value != ' '.join(str(start).split())):
        return 'dead', None
    return 'alive', None


def pid_alive(pid, start=None):
    """True only when the recorded process is proven present; unknown is not alive and not dead."""
    return pid_state(pid, start)[0] == 'alive'


def _process_table():
    """Every live process as {pid: {ppid, pgid, start}}; zombies are not live.

    Raises ProcessObservationError unless the whole table was read: a missing ps, a timeout, a nonzero exit,
    an unparseable row or a table that does not list this process is a partial observation and proves nothing."""
    result, problem = _run_ps(['-axo', 'pid=,ppid=,pgid=,stat=,lstart='])
    if problem:
        raise ProcessObservationError(problem)
    if result.returncode != 0:
        raise ProcessObservationError('ps exited %d' % result.returncode)
    table = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        match = re.match(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.+?)\s*$', line)
        if not match or not LSTART.fullmatch(' '.join(match.group(5).split())):
            raise ProcessObservationError('ps returned an unreadable row')
        if not match.group(4).startswith('Z'):
            table[int(match.group(1))] = {'ppid': int(match.group(2)), 'pgid': int(match.group(3)),
                                          'start': ' '.join(match.group(5).split())}
    if os.getpid() not in table:
        raise ProcessObservationError('the process table does not list this process')
    return table


@contextmanager
def _locked(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / 'admission.lock'
    if lock.is_symlink():
        raise AdmissionError('Admission lock may not be a symlink')
    descriptor = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        elif os.name == 'nt':
            import msvcrt
            if os.fstat(descriptor).st_size == 0: os.write(descriptor, b'0')
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            raise AdmissionError('No verified admission locking backend on this platform')
        yield
    finally:
        os.close(descriptor)


def _load(folder):
    path = Path(folder) / 'admission.json'
    if path.is_symlink():
        raise AdmissionError('Admission record may not be a symlink')
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA_VERSION:
        raise AdmissionError('Malformed admission record')
    return value


def _save(folder, value):
    path = Path(folder) / 'admission.json'
    descriptor, temporary = tempfile.mkstemp(dir=str(folder), prefix='.tmp-')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        if os.name == 'posix':
            directory = os.open(str(folder), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(folder, batch, limits):
    """Set the batch limits once. A resume may keep or tighten them, never loosen or reset them."""
    wanted = validate_limits(limits)
    with _locked(folder):
        value = _load(folder)
        if value is None:
            value = {'schema_version': SCHEMA_VERSION, 'batch': batch, 'limits': wanted,
                     'started_at': now(), 'requests': {}, 'processes': {}}
        else:
            if value['batch'] != batch:
                raise AdmissionError('Admission record belongs to another batch')
            merged = {}
            for key in LIMIT_KEYS:
                old, new = value['limits'].get(key), wanted[key]
                merged[key] = old if new is None else new if old is None else min(old, new)
            value['limits'] = merged
        _save(folder, value)
        return value['limits']


def _used(value, key):
    if key == 'requests':
        return sum(1 for entry in value['requests'].values() if entry['state'] in CHARGED)
    if key == 'output':
        return sum(_output_committed(entry) for entry in value['requests'].values() if entry['state'] in CHARGED)
    return sum(entry['estimate'].get('input_bytes') or 0 for entry in value['requests'].values()
               if entry['state'] in CHARGED)


def _output_committed(entry):
    """Output tokens this charged request holds against the aggregate ceiling.

    In flight, failed or orphaned: its reserved ceiling (conservative; an unknown outcome is never
    refunded). Settled with a valid provider-reported output: that figure, but never less than zero and
    never hiding an overrun, because a provider that exceeded its ceiling really consumed that much."""
    reserved = entry['estimate'].get('output_tokens') or 0
    reported = (entry.get('usage') or {}).get('output_tokens')
    if entry['state'] == 'succeeded' and isinstance(reported, int):
        return reported
    return max(reserved, reported) if isinstance(reported, int) else reserved


def output_ceiling(folder, adapter_ceiling):
    """The output ceiling a request should be dispatched with: the tighter of the adapter's own bound and
    the batch's per-request limit; None when the adapter reports no enforceable bound."""
    value = _load(folder) if Path(folder).exists() else None
    per_request = (value or {}).get('limits', {}).get('max_output_tokens_per_request')
    if adapter_ceiling is None:
        return None
    return min(adapter_ceiling, per_request) if per_request else adapter_ceiling


def clean_usage(usage):
    """Valid provider-reported figures only. Booleans, negatives, NaN/inf and fractional token counts are
    rejected (named in the second result) instead of being summed into the accounts."""
    accepted, rejected = {}, []
    if not isinstance(usage, dict):
        return accepted, rejected
    for key in USAGE_KEYS:
        if key not in usage or usage[key] is None:
            continue
        number = usage[key]
        valid = type(number) in (int, float) and math.isfinite(number) and number >= 0
        if valid and key in USAGE_TOKEN_KEYS and (type(number) is float and number != int(number)):
            valid = False
        if valid:
            accepted[key] = int(number) if key in USAGE_TOKEN_KEYS else number
        else:
            rejected.append(key)
    return accepted, rejected


def admit(folder, request_id, estimate, owner=None):
    """Reserve one model request. Returns {decision: admitted|queued|refused|existing, ...}.

    `existing` means this request id already holds a reservation (a resume); it is returned
    unchanged and charges nothing. `queued` holds no budget and may be asked again.
    """
    estimate = dict(estimate or {})
    for key in ('input_bytes', 'output_tokens', 'timeout_seconds'):
        if estimate.get(key) is not None and (type(estimate[key]) is not int or estimate[key] < 0):
            raise AdmissionError('Estimate ' + key + ' must be a non-negative integer or null')
    with _locked(folder):
        value = _load(folder)
        if value is None:
            raise AdmissionError('Admission is not configured for this batch')
        limits = value['limits']
        entry = value['requests'].get(request_id)
        if entry is not None and entry['state'] != 'queued':
            return {'decision': 'existing', 'state': entry['state'], 'entry': entry}
        if limits['max_elapsed_seconds'] and now() - value['started_at'] > limits['max_elapsed_seconds']:
            return {'decision': 'refused', 'reason': 'batch elapsed-time budget exhausted'}
        if limits['max_model_requests'] and _used(value, 'requests') >= limits['max_model_requests']:
            return {'decision': 'refused', 'reason': 'batch model request budget exhausted'}
        if limits['max_input_bytes'] and _used(value, 'bytes') + (estimate.get('input_bytes') or 0) > limits['max_input_bytes']:
            return {'decision': 'refused', 'reason': 'batch input byte budget would be exceeded'}
        ceiling = estimate.get('output_tokens')
        if limits['max_output_tokens_per_request'] and (ceiling is None or ceiling > limits['max_output_tokens_per_request']):
            return {'decision': 'refused', 'reason': 'request output ceiling is unknown or exceeds the per-request limit'}
        if limits['max_output_tokens']:
            if ceiling is None:
                return {'decision': 'refused', 'reason': 'request has no enforceable output ceiling; '
                        'the aggregate output limit cannot be guaranteed for it'}
            if _used(value, 'output') + ceiling > limits['max_output_tokens']:
                return {'decision': 'refused', 'reason': 'aggregate output reservation would exceed the batch limit'}
        running = sum(1 for e in value['requests'].values() if e['state'] == 'dispatched')
        record = {'state': 'queued', 'estimate': estimate, 'usage': None, 'owner': owner,
                  'queued_at': (entry or {}).get('queued_at', now())}
        if limits['max_concurrent_requests'] and running >= limits['max_concurrent_requests']:
            value['requests'][request_id] = record
            _save(folder, value)
            return {'decision': 'queued', 'reason': 'concurrent request limit reached', 'entry': record}
        pid = os.getpid()
        record.update(state='dispatched', dispatched_at=now(),
                      owner=dict(owner or {}, pid=pid, pid_start=process_start(pid)))
        value['requests'][request_id] = record
        _save(folder, value)
        return {'decision': 'admitted', 'entry': record}


def finish(folder, request_id, status, usage=None):
    """Reconcile a dispatched request: record the outcome and any provider-reported usage."""
    if status not in ('succeeded', 'failed'):
        raise AdmissionError('Finish status must be succeeded or failed')
    with _locked(folder):
        value = _load(folder)
        entry = (value or {}).get('requests', {}).get(request_id)
        if entry is None or entry['state'] not in ('dispatched', 'orphaned'):
            return None
        reported, rejected = clean_usage(usage)
        entry.update(state=status, finished_at=now(), usage=reported or None)
        if rejected:
            entry['usage_rejected'] = rejected  # kept visible; the reservation is not reduced by invalid figures
        _save(folder, value)
        return entry


def _docker(*argv):
    """One docker invocation; (returncode, stdout, stderr) or None when the client cannot run."""
    try:
        result = subprocess.run(['docker', *argv], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode, result.stdout, result.stderr


CONTAINER_ID = re.compile(r'[0-9a-f]{64}')
OWNER_LABEL = 'crewloom.owner'
RUN_LABEL = 'crewloom.run'


def inspect_container(reference):
    """('ok', {id, labels}) | ('missing', None) | ('error', reason). The daemon's answer, never a guess."""
    answer = _docker('container', 'inspect', '--format', '{{json .Id}}|{{json .Config.Labels}}', reference)
    if answer is None:
        return 'error', 'docker is unavailable'
    code, out, err = answer
    if code != 0:
        # Only the daemon's explicit "no such object" is absence; any other failure is an unknown.
        return ('missing', None) if 'no such' in err.lower() else ('error', 'inspect failed: ' + err.strip()[:120])
    try:
        ident, _, labels = out.strip().partition('|')
        return 'ok', {'id': json.loads(ident), 'labels': json.loads(labels) or {}}
    except ValueError:
        return 'error', 'unreadable inspect output'


def remove_container(record):
    """Remove the recorded container only when the daemon still reports its immutable ID and run label.

    A name alone is never trusted: a name can be reused by a different container after ours exits. The
    removal itself addresses the ID, not the name."""
    ident, labels = record.get('container_id'), record.get('labels') or {}
    if not ident or not CONTAINER_ID.fullmatch(str(ident)) or not labels.get(RUN_LABEL):
        return 'unverifiable: no immutable container id and run label were recorded'
    status, found = inspect_container(ident)
    if status == 'missing':
        return 'gone'
    if status == 'error':
        return 'unverifiable: ' + str(found)
    live = found['labels']
    if found['id'] != ident or live.get(OWNER_LABEL) != labels.get(OWNER_LABEL) or live.get(RUN_LABEL) != labels[RUN_LABEL]:
        return 'preserved: the container no longer matches the recorded identity'
    answer = _docker('rm', '--force', ident)
    if answer is not None and answer[0] == 0:
        return 'removed'
    return 'unverifiable: removal was refused or failed'


def _survivors(targets):
    """[pid] of recorded targets still present (same start time); ProcessObservationError if unobservable."""
    table = _process_table()
    return [pid for pid, start in targets.items() if pid in table and table[pid]['start'] == ' '.join(str(start).split())]


def _signal(pid, number):
    try:
        os.kill(pid, number)
    except OSError:
        pass


def _group_valid(pgid):
    return os.name == 'posix' and isinstance(pgid, int) and pgid > 1 and pgid != os.getpgrp()



def _launch_members(token, table):
    """Find cooperating descendants by their inherited random launch marker.

    Environment bytes are inspected in memory only, never logged or persisted. This
    is recovery ownership, not protection from a same-user process forging/stripping
    the marker. An unreadable observation remains unknown and retains the receipt.
    """
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
        raise ProcessObservationError('invalid launch marker')
    marker = ('CREWLOOM_LAUNCH_TOKEN=' + token).encode()
    found = {}
    if sys.platform.startswith('linux'):
        for pid, row in table.items():
            base = Path('/proc') / str(pid)
            try:
                if base.stat().st_uid != os.getuid():
                    continue
                with (base / 'environ').open('rb') as stream:
                    raw = stream.read(262145)
                if len(raw) > 262144:
                    raise ProcessObservationError('process environment exceeds inspection limit')
                if marker in raw.split(b'\0'):
                    found[pid] = row['start']
            except FileNotFoundError:
                continue
            except PermissionError as exc:
                raise ProcessObservationError('owned-user process environment is unreadable') from exc
    elif sys.platform == 'darwin':
        result, problem = _run_ps(['eww', '-axo', 'pid=,uid=,command='])
        if problem or result.returncode != 0 or len(result.stdout.encode()) > 8388608:
            raise ProcessObservationError('process environment observation failed or exceeded limit')
        pattern = re.compile(r'(?:^|\s)' + re.escape(marker.decode()) + r'(?:\s|$)')
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) != 3 or not parts[0].isdigit() or not re.fullmatch(r'-?\d+', parts[1]):
                raise ProcessObservationError('process environment row is unreadable')
            pid = int(parts[0])
            if int(parts[1]) == os.getuid() and pid in table and pattern.search(parts[2]):
                found[pid] = table[pid]['start']
    else:
        raise ProcessObservationError('inherited launch ownership is unsupported on this platform')
    found.pop(os.getpid(), None)
    return found


def _collect_tree(item, table):
    """(targets {pid: start}, problem). Targets are only processes proven to belong to the recorded one.

    A recorded leader that is still the same process contributes its group and every descendant. A leader
    that already exited contributes its group's remaining members, but only while no live process owns the
    group id itself: the kernel never reuses a pid while a group with that id has members, so such members
    are descendants, while a process whose pid equals the id is a different one and ends the search."""
    pid, start, pgid = item.get('pid'), item.get('pid_start'), item.get('pgid')
    own = bool(item.get('own_group')) and _group_valid(pgid)
    leader = pid is not None and start is not None and pid in table \
        and table[pid]['start'] == ' '.join(str(start).split())
    targets = {}
    if own:
        members = {p: r['start'] for p, r in table.items() if r['pgid'] == pgid}
        if not leader and pgid in members:
            return {}, 'unverifiable: the group id now belongs to a different process'
        targets.update(members)
    if leader:
        targets[pid] = table[pid]['start']
        frontier = [pid]
        while frontier:
            parent = frontier.pop()
            for child, row in table.items():
                if row['ppid'] == parent and child not in targets:
                    targets[child] = row['start']
                    frontier.append(child)
    if item.get('launch_token'):
        targets.update(_launch_members(item['launch_token'], table))
    targets.pop(os.getpid(), None)
    return targets, None


def _stop_pid(item, grace=3.0):
    """Stop the recorded process and everything it owns, escalating from SIGTERM to SIGKILL.

    Every signal is preceded by an identity check of that process, so a reused pid is never signalled.
    `gone` is returned only when a complete process table proved the tree absent; if the table cannot be read
    at any point the result is `unverifiable: ...` (never `gone`) and the resource stays tracked."""
    if os.name == 'nt':
        from process_backend import ProcessBackendError
        token = item.get('launch_token')
        with _jobs_lock:
            job = _windows_jobs.get(token)
        if job is not None:
            try:
                result = job.stop()
                with _jobs_lock: _windows_jobs.pop(token, None)
                return result
            except ProcessBackendError as exc:
                return 'unverifiable: ' + str(exc)
        if item.get('windows_job') and pid_state(item['controller_pid'], item.get('controller_start'))[0] == 'dead':
            # KILL_ON_JOB_CLOSE closes with the verified dead controller; before job
            # assignment the worker sees pipe EOF and cannot execute the target.
            return 'gone'
        if item.get('pid') and pid_state(item['pid'], item.get('pid_start'))[0] == 'dead':
            return 'gone'
        return 'unverifiable: Windows job handle is unavailable; resource remains tracked'
    try:
        targets, problem = _collect_tree(item, _process_table())
    except ProcessObservationError as exc:
        return 'unverifiable: process inspection failed (%s); the resource was not signalled' % exc
    if problem:
        return problem
    if not targets:
        return 'gone'
    pgid = item.get('pgid') if item.get('own_group') and _group_valid(item.get('pgid')) else None

    def deliver(number):
        table = _process_table()  # identity is re-verified from a complete table before every round of signals
        if pgid is not None:
            try:
                os.killpg(pgid, number)
            except OSError:
                pass
        for pid in _survivors(targets):
            if pgid is None or table.get(pid, {}).get('pgid') != pgid:
                _signal(pid, number)

    def wait(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and _survivors(targets):
            time.sleep(0.05)
        return _survivors(targets)
    try:
        deliver(signal.SIGTERM)
        if not wait(grace):
            return 'terminated'
        deliver(signal.SIGKILL)
        survivors = wait(2.0)
    except ProcessObservationError as exc:
        return 'unverifiable: process inspection failed (%s); termination could not be confirmed' % exc
    return 'killed' if not survivors else 'survivors: ' + ', '.join(str(p) for p in sorted(survivors))


def _started_at(text):
    try:
        return time.mktime(time.strptime(text, '%a %b %d %H:%M:%S %Y'))
    except (ValueError, OverflowError):
        return None


def reap_group(pgid, not_before=None, grace=2.0):
    """Stop what is left in a process group this caller launched and already waited on.

    Used after a one-shot child exits first: its descendants must not outlive it unrecorded. Only members
    that started at or after `not_before` (the caller's launch time) are touched, so a group id that
    collides with an older, unrelated group is left alone. Returns the pids that survived even SIGKILL."""
    if not _group_valid(pgid):
        return []
    try:
        os.killpg(pgid, 0)  # an empty group needs no process table; a group we cannot signal is not ours
    except ProcessLookupError:
        return []
    except OSError:
        return []

    def ours():
        return sorted(p for p, r in _process_table().items() if r['pgid'] == pgid and p != os.getpid()
                      and (not_before is None or (_started_at(r['start']) or 0) >= not_before - 2))
    try:
        deadline = time.monotonic() + grace
        for number in (signal.SIGTERM, signal.SIGKILL):
            members = ours()
            if not members:
                return []
            for pid in members:
                _signal(pid, number)
            while time.monotonic() < deadline and ours():
                time.sleep(0.05)
            deadline = time.monotonic() + grace
        return ours()
    except ProcessObservationError as exc:
        # An unreadable process table cannot show that nothing survived: report it so tracking is kept.
        return ['unverified (process inspection failed: %s)' % exc]


def track_process(folder, kind, ident, pid=None, task=None, container=None, launch_token=None):
    """Record a process or container this batch started, with an identity to verify before stopping it.

    A batch that cannot record the resource raises: running it untracked would make cancellation and
    restart recovery silently incomplete. `container` is {'id': 64-hex, 'labels': {...}}."""
    if kind not in ('process', 'container'):
        raise AdmissionError('Tracked kind must be process or container')
    if kind == 'container' and (not isinstance(container, dict) or not CONTAINER_ID.fullmatch(str(container.get('id', '')))
                                or not (container.get('labels') or {}).get(RUN_LABEL)):
        raise AdmissionError('A container is tracked by its immutable id and run label, not by name')
    with _locked(folder):
        value = _load(folder)
        if value is None:
            raise AdmissionError('Admission is not configured for this batch; the resource cannot be tracked')
        key = kind + ':' + str(ident)
        pgid = own_group = pid_start = None
        if pid and kind == 'process':
            observed, detail = observe_process(pid)
            if observed == 'unknown':
                # Tracking a pid whose identity cannot be established would let cancellation later mistake a
                # reused pid for ours, or report a live process gone. The caller stops the launch instead.
                raise AdmissionError('The process identity cannot be verified (%s); the process is not tracked' % detail)
            pid_start = detail if observed == 'present' else None
            try:
                pgid = os.getpgid(pid) if os.name == 'posix' else None
                own_group = pgid == pid and _group_valid(pgid)
            except OSError:
                pass
        controller_state, controller_start = observe_process(os.getpid())
        if controller_state != 'present':
            raise AdmissionError('The controller identity cannot be verified (%s); nothing is tracked' % controller_start)
        entry = {'kind': kind, 'ident': str(ident), 'pid': pid, 'pid_start': pid_start, 'pgid': pgid,
                 'own_group': own_group, 'controller_pid': os.getpid(), 'controller_start': controller_start,
                 'task': task, 'tracked_at': now()}
        if launch_token:
            entry['launch_token'] = launch_token
            if os.name == 'nt': entry['windows_job'] = True
        if container:
            entry.update(container_id=container['id'], labels=dict(container['labels']))
        value['processes'][key] = entry
        _save(folder, value)
        return key



# The wrapper consumes exactly one byte from stdin. Target stdin remains untouched.
# EOF before acknowledgement exits without executing the target. It has no imports
# from mutable consumer projects and accepts only the controller's argv, never code.
_LAUNCH_WORKER = "import os,sys,json,subprocess; a=os.read(0,1); sys.exit(125) if a!=b'1' else (sys.exit(subprocess.Popen(json.loads(sys.argv[2]),stdin=sys.stdin).wait()) if os.name=='nt' else os.execvpe(sys.argv[1],json.loads(sys.argv[2]),os.environ))"


def launch_owned(argv, **kwargs):
    """Durably register a launch intent and process identity before releasing target execution.

    Requires PIPE stdin; the caller may communicate its actual payload after this returns.
    Outside a batch the same handshake guards tracking failure, but no recovery ledger
    exists. POSIX exec preserves PID; Windows assigns an acknowledged worker and its
    descendants to a kill-on-close job before acknowledgement.
    No arbitrary CLI sandbox is implied by ownership tracking.
    """
    if os.name not in ('posix', 'nt'):
        raise AdmissionError('Managed acknowledged launch has no backend on this platform')
    if not argv or kwargs.get('stdin') != subprocess.PIPE:
        raise AdmissionError('Acknowledged launch needs argv and PIPE stdin')
    token = uuid.uuid4().hex
    active = current()
    intent = 'launch:' + token
    env = dict(kwargs.get('env', os.environ))
    env['CREWLOOM_LAUNCH_TOKEN'] = token
    kwargs['env'] = env
    if active:
        with _locked(active['folder']):
            value = _load(active['folder'])
            if value is None:
                raise AdmissionError('Launch needs configured admission before dispatch')
            state, started = observe_process(os.getpid())
            if state != 'present':
                raise AdmissionError('Launch controller identity is unknown')
            value['processes'][intent] = {'kind': 'launch', 'ident': token,
                'controller_pid': os.getpid(), 'controller_start': started,
                'task': active.get('task'), 'tracked_at': now(), 'launch_token': token,
                'windows_job': os.name == 'nt',
                'note': 'target awaits acknowledgement; interrupted acknowledgement is uncertain, never replay'}
            _save(active['folder'], value)
    process = None
    job = None
    try:
        if os.name == 'nt':
            from process_backend import OwnedJob
            job = OwnedJob()
            kwargs.pop('start_new_session', None)
        process = subprocess.Popen([sys.executable, '-c', _LAUNCH_WORKER, str(argv[0]), json.dumps(list(argv))], **kwargs)
        if job is not None:
            job.assign(process)
            job.pid = process.pid
            with _jobs_lock: _windows_jobs[token] = job
            process._crewloom_launch_token = token
        if active:
            track_process(active['folder'], 'process', process.pid, process.pid,
                          active.get('task'), launch_token=token)
        process.stdin.write('1' if (kwargs.get('text') or kwargs.get('universal_newlines') or kwargs.get('encoding')) else b'1')
        process.stdin.flush()
        if active:
            untrack_process(active['folder'], 'launch', token)
        return process
    except BaseException:
        if process is not None:
            # Closing the release pipe prevents target execution before acknowledgement.
            try:
                process.stdin.close()
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                process.kill(); process.wait(timeout=5)
            finally:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
        if job is not None:
            job.close()
            with _jobs_lock: _windows_jobs.pop(token, None)
        # Keep the intent: a failure after acknowledgement has uncertain side effects.
        raise




def register_guarded_process(process):
    """Register a spawn worker while its separate release pipe still blocks all external effects."""
    token = None
    job = None
    try:
        if os.name == 'nt':
            from process_backend import OwnedJob
            token = uuid.uuid4().hex
            job = OwnedJob(); job.assign(process); job.pid = process.pid
            with _jobs_lock: _windows_jobs[token] = job
        active = current()
        if active:
            track_process(active['folder'], 'process', process.pid, process.pid, active.get('task'), launch_token=token)
        return token
    except BaseException:
        if job is not None:
            job.close()
            with _jobs_lock: _windows_jobs.pop(token, None)
        raise


def track_container_intent(name, labels):
    """Persist labeled container ownership before Docker can create it or execute its command."""
    active = current()
    if not active:
        return None
    if not isinstance(name, str) or not re.fullmatch(r'crewloom-[a-f0-9]{32}', name) or not labels.get(RUN_LABEL):
        raise AdmissionError('Container launch intent needs a generated name and ownership label')
    with _locked(active['folder']):
        value = _load(active['folder'])
        if value is None:
            raise AdmissionError('Container launch needs configured admission')
        state, started = observe_process(os.getpid())
        if state != 'present':
            raise AdmissionError('Container launch controller identity is unknown')
        key = 'container-launch:' + name
        value['processes'][key] = {'kind': 'container-launch', 'ident': name,
            'labels': dict(labels), 'controller_pid': os.getpid(), 'controller_start': started,
            'task': active.get('task'), 'tracked_at': now(),
            'note': 'creation/dispatch uncertain until immutable id is registered; never replay automatically'}
        _save(active['folder'], value)
    return key


def reconcile_container_intent(item):
    """Resolve an interrupted launch by name plus labels, then act only on inspected immutable ID."""
    status, found = inspect_container(item['ident'])
    if status == 'missing':
        return 'gone'
    if status != 'ok':
        return 'unverifiable: container launch could not be inspected'
    return remove_container({'container_id': found['id'], 'labels': item['labels']})


def untrack_process(folder, kind, ident):
    with _locked(folder):
        value = _load(folder)
        if value and value['processes'].pop(kind + ':' + str(ident), None) is not None:
            _save(folder, value)


def terminate_owned(folder, only_orphans=False):
    """Stop the processes/containers this batch recorded; never anything else.

    With `only_orphans`, only entries whose controller process is gone are stopped (restart
    reconciliation). The result lists what happened to each, so nothing is silently skipped."""
    outcomes = []
    with _locked(folder):
        value = _load(folder)
        if value is None:
            return outcomes
        for key, item in sorted(value['processes'].items()):
            if only_orphans:
                controller, detail = pid_state(item['controller_pid'], item.get('controller_start'))
                if controller == 'alive':
                    continue
                if controller == 'unknown':
                    outcomes.append({'key': key, 'task': item.get('task'),
                                     'result': 'unverifiable: the controller could not be checked (%s)' % detail})
                    continue
            if item['kind'] == 'container-launch':
                result = reconcile_container_intent(item)
            elif item['kind'] == 'container':
                result = remove_container(item)
            elif item.get('pid') or item.get('launch_token'):
                result = _stop_pid(item)
            else:
                result = 'no pid recorded'
            outcomes.append({'key': key, 'task': item.get('task'), 'result': result})
            # Settled or provably not ours: stop tracking. Unverifiable or surviving resources stay visible.
            if result in ('removed', 'gone', 'terminated', 'killed') or result.startswith('preserved'):
                del value['processes'][key]
        _save(folder, value)
    return outcomes



def settle_current_process(ident):
    """Stop one managed launch's remaining descendants and retain unverifiable ownership."""
    active = current()
    if not active:
        if os.name != 'nt': return None
        with _jobs_lock:
            matching = [(token, job) for token, job in _windows_jobs.items() if getattr(job, 'pid', None) == ident]
        if len(matching) != 1:
            return 'unverifiable: Windows launch ownership is missing or ambiguous'
        token, job = matching[0]
        try:
            outcome = job.stop()
            with _jobs_lock: _windows_jobs.pop(token, None)
            return outcome
        except ValueError as exc:
            return 'unverifiable: ' + str(exc)
    with _locked(active['folder']):
        value = _load(active['folder'])
        item = (value or {}).get('processes', {}).get('process:' + str(ident))
    if item is None:
        return None
    result = _stop_pid(item)
    if result in ('gone', 'terminated', 'killed'):
        untrack_process(active['folder'], 'process', ident)
    return result


def recover(folder):
    """Restart reconciliation: dispatches whose owner died become `orphaned` (charged, never replayed)."""
    orphaned, unverified = [], []
    with _locked(folder):
        value = _load(folder)
        if value is None:
            return {'orphaned_requests': [], 'unverified_owners': [], 'stopped': []}
        for request_id, entry in sorted(value['requests'].items()):
            owner = entry.get('owner') or {}
            if entry['state'] != 'dispatched':
                continue
            state, detail = pid_state(owner.get('pid'), owner.get('pid_start'))
            if state == 'unknown':
                unverified.append({'request': request_id, 'reason': detail})  # not proven dead: never orphaned on a guess
            elif state == 'dead':
                entry.update(state='orphaned', orphaned_at=now(),
                             note='owner process ended before the outcome was recorded; side effects unknown; not replayed')
                orphaned.append(request_id)
        _save(folder, value)
    return {'orphaned_requests': orphaned, 'unverified_owners': unverified,
            'stopped': terminate_owned(folder, only_orphans=True)}


def cancel_queued(folder):
    with _locked(folder):
        value = _load(folder)
        changed = [rid for rid, e in (value or {}).get('requests', {}).items() if e['state'] == 'queued']
        for rid in changed:
            value['requests'][rid]['state'] = 'cancelled'
        if changed:
            _save(folder, value)
    return changed


def summary(folder):
    value = _load(folder) if Path(folder).exists() else None
    if value is None:
        return None
    states = {}
    for entry in value['requests'].values():
        states[entry['state']] = states.get(entry['state'], 0) + 1
    settled = [e for e in value['requests'].values() if e['state'] in ('succeeded', 'failed', 'orphaned')]
    def total(key):
        values = [e['usage'][key] for e in settled if e.get('usage') and key in e['usage']]
        return sum(values) if values else None
    coverage = {key: {'reporting_requests': sum(1 for e in settled if e.get('usage') and key in e['usage']),
                      'settled_requests': len(settled)} for key in USAGE_KEYS}
    for item in coverage.values():
        item['complete'] = item['reporting_requests'] == item['settled_requests'] and bool(item['settled_requests'])
    return {'limits': value['limits'], 'states': states,
            'charged_requests': _used(value, 'requests'),
            'estimated_input_bytes': _used(value, 'bytes'),
            'reserved_output_tokens': _used(value, 'output'),
            'recorded_usage': {'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
                               'cost_usd': total('cost_usd'), 'coverage': coverage,
                               'note': 'None means no provider reported it; a total with complete=false covers '
                                       'only the reporting requests; estimates are separate fields'},
            'enforcement': {'cost_cap': 'not supported: cost_usd is accounting only, no price table or cap exists',
                            'elapsed': 'admission deadline: refuses new requests, does not stop work in flight',
                            'output_tokens': 'aggregate reservation of enforceable ceilings; requests without one '
                                             'are refused while the limit is set',
                            'unmanaged_activity': 'native CLI use outside the controller is not counted or capped'},
            'tracked_processes': sorted(value['processes']),
            'unbounded': sorted(k for k, v in value['limits'].items() if v is None)}


# Thread-local batch context so a worker thread's workflow can find its batch without globals.
@contextmanager
def context(folder, task=None):
    previous = getattr(_local, 'context', None)
    _local.context = {'folder': str(folder), 'task': task}
    try:
        yield
    finally:
        _local.context = previous


def current():
    return getattr(_local, 'context', None)


def track_current(kind, ident, pid=None, container=None):
    """No-op outside a batch; inside one, record this process/container as batch-owned (a failure raises)."""
    active = current()
    if active:
        return track_process(active['folder'], kind, ident, pid, active.get('task'), container)
    return None


def untrack_current(kind, ident):
    active = current()
    if active:
        untrack_process(active['folder'], kind, ident)
