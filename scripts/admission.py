#!/usr/bin/env python3
"""Aggregate admission, budgets, queued dispatch and owned-process cancellation for a batch (W09).

The checkout request ceiling in the workflow ledger is per worktree. A coordinated batch runs
several worktrees at once, so this module keeps one persisted, atomically updated ledger in the
batch's coordinator folder. A request is reserved before dispatch and reconciled after it; a
reservation is idempotent by request id (a resume never double charges or hands out a
replacement slot); a dispatch whose owner died is `orphaned`, still charged and never
replayed. Token and cost figures stay `None` unless a provider reported them, and estimates
are always labelled apart from recorded usage. Processes and containers the batch itself
started are recorded with an identity, so cancellation stops exactly those and nothing else.
"""
import json
import os
import signal
import subprocess
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
              'max_input_bytes', 'max_output_tokens')
CHARGED = ('dispatched', 'succeeded', 'failed', 'orphaned')
_local = threading.local()


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


def process_start(pid):
    """An identity for a pid that survives pid reuse: its reported start time, or None if gone.

    A zombie (exited, not yet reaped) is gone for every purpose here."""
    try:
        result = subprocess.run(['ps', '-o', 'stat=,lstart=', '-p', str(int(pid))], capture_output=True,
                                text=True, timeout=10)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    text = result.stdout.strip()
    if not text:
        return None
    state, _, started = text.partition(' ')
    if state.startswith('Z'):
        return None
    return started.strip() or None


def pid_alive(pid, start=None):
    current = process_start(pid)
    return current is not None and (start is None or current == start)


@contextmanager
def _locked(folder):
    if fcntl is None:
        raise AdmissionError('Admission needs POSIX advisory locking')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / 'admission.lock'
    if lock.is_symlink():
        raise AdmissionError('Admission lock may not be a symlink')
    descriptor = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
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
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
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
    return sum(1 for entry in value['requests'].values() if entry['state'] in CHARGED) if key == 'requests' else \
        sum(entry['estimate'].get('input_bytes') or 0 for entry in value['requests'].values()
            if entry['state'] in CHARGED)


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
        if limits['max_output_tokens'] and estimate.get('output_tokens') is not None \
                and estimate['output_tokens'] > limits['max_output_tokens']:
            return {'decision': 'refused', 'reason': 'request output ceiling exceeds the batch limit'}
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
        reported = {k: usage.get(k) for k in ('input_tokens', 'output_tokens', 'total_tokens', 'cost_usd')
                    if isinstance(usage, dict) and isinstance(usage.get(k), (int, float))}
        entry.update(state=status, finished_at=now(), usage=reported or None)
        _save(folder, value)
        return entry


def _stop_container(name):
    try:
        result = subprocess.run(['docker', 'rm', '--force', name], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _stop_pid(pid, start, grace=3.0):
    """Stop exactly the recorded process: only when its start identity still matches."""
    if not pid_alive(pid, start):
        return 'gone'
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return 'gone'
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not pid_alive(pid, start):
            return 'terminated'
        time.sleep(0.05)
    if pid_alive(pid, start):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    return 'killed'


def track_process(folder, kind, ident, pid=None, task=None):
    """Record a process or container this batch started, with an identity to verify before stopping it."""
    if kind not in ('process', 'container'):
        raise AdmissionError('Tracked kind must be process or container')
    with _locked(folder):
        value = _load(folder)
        if value is None:
            return None
        key = kind + ':' + str(ident)
        value['processes'][key] = {'kind': kind, 'ident': str(ident), 'pid': pid,
                                   'pid_start': process_start(pid) if pid else None,
                                   'controller_pid': os.getpid(), 'controller_start': process_start(os.getpid()),
                                   'task': task, 'tracked_at': now()}
        _save(folder, value)
        return key


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
            if only_orphans and pid_alive(item['controller_pid'], item.get('controller_start')):
                continue
            if item['kind'] == 'container':
                result = 'removed' if _stop_container(item['ident']) else 'remove failed'
            elif item.get('pid'):
                result = _stop_pid(item['pid'], item.get('pid_start'))
            else:
                result = 'no pid recorded'
            outcomes.append({'key': key, 'task': item.get('task'), 'result': result})
            if result in ('removed', 'gone', 'terminated', 'killed'):
                del value['processes'][key]
        _save(folder, value)
    return outcomes


def recover(folder):
    """Restart reconciliation: dispatches whose owner died become `orphaned` (charged, never replayed)."""
    orphaned = []
    with _locked(folder):
        value = _load(folder)
        if value is None:
            return {'orphaned_requests': [], 'stopped': []}
        for request_id, entry in sorted(value['requests'].items()):
            owner = entry.get('owner') or {}
            if entry['state'] == 'dispatched' and not pid_alive(owner.get('pid'), owner.get('pid_start')):
                entry.update(state='orphaned', orphaned_at=now(),
                             note='owner process ended before the outcome was recorded; side effects unknown; not replayed')
                orphaned.append(request_id)
        _save(folder, value)
    return {'orphaned_requests': orphaned, 'stopped': terminate_owned(folder, only_orphans=True)}


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
    reported = [e['usage'] for e in value['requests'].values() if e.get('usage')]
    def total(key):
        values = [u[key] for u in reported if key in u]
        return sum(values) if values else None
    return {'limits': value['limits'], 'states': states,
            'charged_requests': _used(value, 'requests'),
            'estimated_input_bytes': _used(value, 'bytes'),
            'recorded_usage': {'input_tokens': total('input_tokens'), 'output_tokens': total('output_tokens'),
                               'cost_usd': total('cost_usd'),
                               'note': 'None means no provider reported it; estimates are separate fields'},
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


def track_current(kind, ident, pid=None):
    """No-op outside a batch; inside one, record this process/container as batch-owned."""
    active = current()
    if active:
        return track_process(active['folder'], kind, ident, pid, active.get('task'))
    return None


def untrack_current(kind, ident):
    active = current()
    if active:
        untrack_process(active['folder'], kind, ident)
