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
    return ' '.join(started.split()) or None


def pid_alive(pid, start=None):
    current = process_start(pid)
    return current is not None and (start is None or current == ' '.join(str(start).split()))


def _process_table():
    """Every live process as {pid: {ppid, pgid, start}}; zombies are not live."""
    try:
        result = subprocess.run(['ps', '-axo', 'pid=,ppid=,pgid=,stat=,lstart='], capture_output=True,
                                text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return {}
    table = {}
    for line in result.stdout.splitlines():
        match = re.match(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.+?)\s*$', line)
        if match and not match.group(4).startswith('Z'):
            table[int(match.group(1))] = {'ppid': int(match.group(2)), 'pgid': int(match.group(3)),
                                          'start': ' '.join(match.group(5).split())}
    return table


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


def _same(pid, start):
    return process_start(pid) == ' '.join(str(start).split())


def _alive_targets(targets):
    return [pid for pid, start in targets.items() if _same(pid, start)]


def _signal(pid, number):
    try:
        os.kill(pid, number)
    except OSError:
        pass


def _group_valid(pgid):
    return isinstance(pgid, int) and pgid > 1 and pgid != os.getpgrp()


def _collect_tree(item, table):
    """(targets {pid: start}, problem). Targets are only processes proven to belong to the recorded one.

    A recorded leader that is still the same process contributes its group and every descendant. A leader
    that already exited contributes its group's remaining members, but only while no live process owns the
    group id itself: the kernel never reuses a pid while a group with that id has members, so such members
    are descendants, while a process whose pid equals the id is a different one and ends the search."""
    pid, start, pgid = item.get('pid'), item.get('pid_start'), item.get('pgid')
    own = bool(item.get('own_group')) and _group_valid(pgid)
    leader = pid is not None and pid in table and (start is None or table[pid]['start'] == ' '.join(str(start).split()))
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
    targets.pop(os.getpid(), None)
    return targets, None


def _stop_pid(item, grace=3.0):
    """Stop the recorded process and everything it owns, escalating from SIGTERM to SIGKILL.

    Every signal is preceded by an identity check of that process, so a reused pid is never signalled."""
    targets, problem = _collect_tree(item, _process_table())
    if problem:
        return problem
    if not targets:
        return 'gone'
    pgid = item.get('pgid') if item.get('own_group') and _group_valid(item.get('pgid')) else None

    def deliver(number):
        if pgid is not None:
            try:
                os.killpg(pgid, number)
            except OSError:
                pass
        for pid in _alive_targets(targets):
            if pgid is None or _process_table().get(pid, {}).get('pgid') != pgid:
                _signal(pid, number)
    deliver(signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and _alive_targets(targets):
        time.sleep(0.05)
    if not _alive_targets(targets):
        return 'terminated'
    deliver(signal.SIGKILL)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and _alive_targets(targets):
        time.sleep(0.05)
    survivors = _alive_targets(targets)
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


def track_process(folder, kind, ident, pid=None, task=None, container=None):
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
        pgid = own_group = None
        if pid and kind == 'process':
            try:
                pgid = os.getpgid(pid)
                own_group = pgid == pid and _group_valid(pgid)
            except OSError:
                pass
        entry = {'kind': kind, 'ident': str(ident), 'pid': pid,
                 'pid_start': process_start(pid) if pid else None, 'pgid': pgid, 'own_group': own_group,
                 'controller_pid': os.getpid(), 'controller_start': process_start(os.getpid()),
                 'task': task, 'tracked_at': now()}
        if container:
            entry.update(container_id=container['id'], labels=dict(container['labels']))
        value['processes'][key] = entry
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
                result = remove_container(item)
            elif item.get('pid'):
                result = _stop_pid(item)
            else:
                result = 'no pid recorded'
            outcomes.append({'key': key, 'task': item.get('task'), 'result': result})
            # Settled or provably not ours: stop tracking. Unverifiable or surviving resources stay visible.
            if result in ('removed', 'gone', 'terminated', 'killed') or result.startswith('preserved'):
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
