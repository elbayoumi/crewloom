#!/usr/bin/env python3
"""Durable, controller-owned continuation records for moving a task between agents (N02).

A checkpoint is written by the controller at workflow boundaries from state it already owns
(workflow state, attempt ledger, binding, Git), never by asking an exhausted model for a
summary. A receiver validates identity, integrity, drift, ownership and its own capabilities
before taking the single writable owner slot. Nothing here transfers credentials, resets an
attempt counter, replays an operation whose side effects are uncertain, or steals a live owner.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import workflow as w

SCHEMA_VERSION = 1
KIND = 'crewloom-continuation'
MAX_PACKET_BYTES = 256 * 1024
MAX_DIRTY = 200
MAX_HASH_BYTES = 8 * 1024 * 1024
OWNER_STATES = ('active', 'interrupted', 'released')
TOKEN_ENVIRONMENT = 'CREWLOOM_OWNER_TOKEN'


class CheckpointError(OSError):
    """A checkpoint that must exist before a side effect could not be committed."""


class OwnershipError(RuntimeError):
    """The caller does not hold the single writable owner slot of this workflow."""


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def folder(root, workflow):
    if not isinstance(workflow, str) or not w.ID.fullmatch(workflow):
        raise ValueError('Workflow ID is invalid')
    return w.safe_path(root, '.crewloom/handoffs/' + workflow, internal=True)


def _private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Continuation record path may not be a symlink')
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.tmp-')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())  # the bytes are on disk before the name can point at them
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _sync_directory(directory):
    """Make a rename durable where the platform allows opening a directory; elsewhere a no-op."""
    if os.name != 'posix':
        return
    descriptor = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _git(root, *argv):
    import repo_map
    result = subprocess.run(['git', '-C', str(root), *argv], env=repo_map.git_environment(),
                            capture_output=True, timeout=30)
    return result.stdout if result.returncode == 0 else None


def dirty_fingerprints(root):
    """Uncommitted paths with content hashes, so a receiver can tell what changed since the checkpoint."""
    raw = _git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    if raw is None:
        return {'available': False, 'entries': {}, 'omitted': 0}
    entries, omitted = {}, 0
    parts = raw.decode('utf-8', 'surrogateescape').split('\0')
    index = 0
    while index < len(parts):
        item = parts[index]
        index += 1
        if len(item) < 4:
            continue
        status, name = item[:2], item[3:]
        if status[0] in 'RC':
            index += 1  # the original path of a rename/copy follows as its own field
        if name == '.crewloom' or name.startswith('.crewloom/'):
            continue
        if len(entries) >= MAX_DIRTY:
            omitted += 1
            continue
        path = Path(root) / name
        if path.is_symlink():
            entries[name] = {'status': status.strip(), 'sha256': 'symlink'}
        elif path.is_file():
            entries[name] = {'status': status.strip(),
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()
                             if path.stat().st_size <= MAX_HASH_BYTES else 'oversize'}
        else:
            entries[name] = {'status': status.strip(), 'sha256': None}
    return {'available': True, 'entries': entries, 'omitted': omitted}


def _policy_sha(root):
    path = Path(root) / 'crewloom.project.json'
    return w.digest(path.read_bytes()) if path.is_file() else None


def _ledger(root):
    path = w.safe_path(root, '.crewloom/attempts.json', internal=True)
    return json.loads(path.read_text()) if path.exists() else {'attempts': []}


def build_packet(root, plan, state, ledger, boundary, step_id=None, interruption=None, producer=None,
                 plan_file=None, sequence=0, previous=None):
    import project_binding as pb
    binding = pb.load_binding(root)
    plan_file = plan_file or state.get('plan_file')  # the path the workflow was run from, recorded in its state
    attempts = [{'step': a.get('step'), 'kind': a.get('kind', 'command'), 'status': a.get('status'),
                 'signature': a.get('signature'), 'uncertain_side_effects': bool(a.get('uncertain_side_effects'))}
                for a in ledger['attempts'] if a.get('workflow') == plan['id']]
    completed, unverified, pending = {}, [], []
    for step in plan['steps']:
        record = state['steps'].get(step['id'], {})
        if record.get('status') == 'complete':
            completed[step['id']] = {'inputs': record.get('inputs', {}), 'outputs': record.get('outputs', {})}
            try:
                if w.hashes(root, step['outputs']) != record.get('outputs'):
                    unverified.append(step['id'])
            except ValueError:
                unverified.append(step['id'])
        else:
            pending.append({'step': step['id'], 'status': record.get('status', 'pending'),
                            'error': record.get('error'), 'failure': record.get('failure')})
    in_flight = [a for a in attempts if a['status'] == 'running']
    exhausted = sorted({a['step'] for a in attempts if a['step'] and sum(
        b['signature'] == a['signature'] and b['status'] != 'succeeded' for b in attempts) >= 2})
    if in_flight:
        action = 'reconcile in-flight attempt(s) first: side effects are uncertain; do not replay'
    elif exhausted:
        action = 'blocked: two attempts exhausted for ' + ', '.join(exhausted) + '; change the hypothesis or input'
    elif unverified:
        action = 're-verify steps whose outputs changed: ' + ', '.join(unverified)
    elif pending:
        action = 'resume at step ' + pending[0]['step'] + ' after the receiver validates this packet'
    else:
        action = 'workflow complete; nothing to continue'
    try:
        from provider_gateway import MAX_PROJECT_MODEL_REQUESTS as model_limit
    except ImportError:
        model_limit = None
    context = None
    try:
        context = w.project_context_status(root, plan['id'])
    except (ValueError, OSError):
        context = None
    packet = {'schema_version': SCHEMA_VERSION, 'kind': KIND, 'created_at': now(), 'sequence': sequence,
              'previous_sha256': previous, 'boundary': boundary, 'step': step_id,
              'identity': {'project_id': binding['project_id'], 'project_root': str(root),
                           'checkout_id': binding['checkout_id'], 'task_id': plan['id']},
              'workflow': {'id': plan['id'], 'plan_sha256': w.digest(json.dumps(plan, sort_keys=True).encode()),
                           'plan_file': plan_file, 'status': state.get('status'),
                           'criteria': plan.get('criteria')},
              'policy_sha256': _policy_sha(root),
              'source': {'base_revision': (_git(root, 'rev-parse', 'HEAD') or b'').decode().strip() or None,
                         'dirty': dirty_fingerprints(root)},
              'context': context,
              'completed_steps': completed, 'unverified_steps': unverified, 'pending_steps': pending,
              'attempts': attempts, 'in_flight': in_flight, 'exhausted': exhausted,
              'budgets': {'model_requests_consumed': sum(1 for a in ledger['attempts'] if a.get('kind') == 'model'),
                          'model_request_limit': model_limit,
                          'tokens': None, 'cost': None, 'note': 'token and cost telemetry unknown unless a host reported it'},
              'producer': producer or {'host': None, 'model': None, 'profile_fingerprint': None},
              'interruption': interruption,
              'next_safe_action': action,
              'limits': ['A transferred packet carries references and hashes, not credentials or a vendor session.',
                         'Uncommitted edits are retained in place; nothing is stashed, reset or committed.']}
    packet['packet_sha256'] = sha(packet)
    if len(canonical(packet).encode()) > MAX_PACKET_BYTES:
        raise ValueError('Continuation packet exceeds its byte budget')
    return packet


def summary(packet):
    """A compact human summary derived from the record, never the source of truth."""
    identity = packet['identity']
    lines = ['# Handoff — ' + identity['task_id'],
             'Project %s, checkout %s, root %s.' % (identity['project_id'], identity['checkout_id'][:8], identity['project_root']),
             'Boundary: %s (step %s), checkpoint %d at %s.' % (packet['boundary'], packet['step'] or '-', packet['sequence'], packet['created_at']),
             'Completed: ' + (', '.join(packet['completed_steps']) or 'none') + '.',
             'Pending: ' + (', '.join(p['step'] + ' [' + p['status'] + ']' for p in packet['pending_steps']) or 'none') + '.',
             'Unverified: ' + (', '.join(packet['unverified_steps']) or 'none') + '. In flight: ' + str(len(packet['in_flight'])) + '.',
             'Dirty paths kept in place: %d.' % len(packet['source']['dirty']['entries']),
             'Attempts: %d recorded; exhausted: %s.' % (len(packet['attempts']), ', '.join(packet['exhausted']) or 'none'),
             'Interruption: ' + (json.dumps(packet['interruption'], ensure_ascii=False) if packet['interruption'] else 'none recorded') + '.',
             'Next safe action: ' + packet['next_safe_action'],
             'Full record: .crewloom/handoffs/%s/latest.json (sha256 %s).' % (identity['task_id'], packet['packet_sha256'][:16])]
    return '\n'.join(lines) + '\n'


def write_checkpoint(root, plan, state, ledger, boundary, step_id=None, interruption=None, producer=None,
                     plan_file=None):
    root = Path(root).resolve()
    target = folder(root, plan['id'])
    latest = target / 'latest.json'
    previous, sequence = None, 0
    if latest.is_file():
        last = json.loads(latest.read_text())
        previous, sequence = last.get('packet_sha256'), int(last.get('sequence', 0)) + 1
    packet = build_packet(root, plan, state, ledger, boundary, step_id, interruption, producer, plan_file,
                          sequence, previous)
    text = json.dumps(packet, ensure_ascii=False, indent=2) + '\n'
    # Commit order: the immutable sequence record first, then latest.json (the commit point, one atomic
    # rename), and only then the derived display file. A crash between steps leaves the previous
    # latest.json intact; `committed_latest` rejects a latest.json with no matching sequence record.
    _private_write(target / sequence_name(sequence, boundary), text)
    _private_write(latest, text)
    if json.loads(latest.read_text(encoding='utf-8')).get('packet_sha256') != packet['packet_sha256']:
        raise CheckpointError('Checkpoint read-back does not match the packet that was written')
    try:
        _private_write(target / 'HANDOFF.md', summary(packet))
    except OSError as exc:  # a display file is not recovery state
        _note_error(root, plan, boundary + ' (display file): ' + str(exc))
    return packet


def sequence_name(sequence, boundary):
    return '%06d-%s.json' % (sequence, re.sub(r'[^a-z_]', '', boundary))


def committed_latest(root, workflow):
    """The latest packet only when it is intact and backed by its immutable sequence record, else None."""
    target = folder(root, workflow)
    latest = target / 'latest.json'
    try:
        text = latest.read_text(encoding='utf-8')
        packet = json.loads(text)
        body = {k: v for k, v in packet.items() if k != 'packet_sha256'}
        record = target / sequence_name(int(packet['sequence']), packet['boundary'])
        if packet.get('packet_sha256') != sha(body) or record.is_symlink() or record.read_text(encoding='utf-8') != text:
            return None
        return packet
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _note_error(root, plan, message):
    try:
        _private_write(folder(Path(root).resolve(), plan['id']) / 'checkpoint-error.txt', now() + ' ' + message[:300] + '\n')
    except Exception:
        pass


def required_checkpoint(root, plan, state, ledger, boundary, step_id=None):
    """A checkpoint the caller may not proceed without: failure raises before any side effect.

    A project with no binding has no identity a receiver could validate, so no recovery point exists to
    require and an ordinary workflow stays compatible (returns None). A binding that is present but
    unreadable, moved or invalid fails closed like any other write failure."""
    import project_binding as pb
    try:
        if pb.load_binding(Path(root).resolve(), required=False) is None:
            return None
    except (ValueError, OSError) as exc:
        _note_error(root, plan, boundary + ': ' + str(exc))
        raise CheckpointError('Required checkpoint %r cannot be built: %s' % (boundary, exc)) from exc
    try:
        packet = write_checkpoint(root, plan, state, ledger, boundary, step_id)
    except Exception as exc:
        _note_error(root, plan, boundary + ': ' + str(exc))
        raise CheckpointError('Required checkpoint %r could not be committed: %s' % (boundary, exc)) from exc
    if committed_latest(Path(root).resolve(), plan['id']) is None:
        raise CheckpointError('Required checkpoint %r is not a committed recovery point' % boundary)
    return packet


def best_effort_checkpoint(root, plan, state, ledger, boundary, step_id=None):
    """Optional boundaries (display and telemetry): a failure is recorded visibly and the run continues."""
    try:
        return write_checkpoint(root, plan, state, ledger, boundary, step_id)
    except Exception as exc:  # optional telemetry/display boundaries never break an otherwise safe run
        _note_error(root, plan, boundary + ': ' + str(exc))
        return None


def read_owner(root, workflow):
    path = folder(root, workflow) / 'owner.json'
    if not path.is_file():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get('state') not in OWNER_STATES:
        raise ValueError('Malformed continuation owner record')
    return value


def _project_lock(root, reentrant):
    return w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=reentrant)


def _token_sha(token):
    return hashlib.sha256(str(token).encode('utf-8')).hexdigest()


def claim_from(owner_id, epoch, environ=None):
    """The claim a receiver presents: its id, its epoch and the secret returned once by `accept`."""
    token = (environ if environ is not None else os.environ).get(TOKEN_ENVIRONMENT)
    if owner_id is None and epoch is None and not token:
        return None
    return {'owner': owner_id, 'epoch': epoch, 'token': token}


def fence(root, workflow, claim=None):
    """Raise OwnershipError unless this caller may mutate the workflow (dispatch, publish, reconcile).

    No owner record means an ordinary workflow, which stays compatible. An active owner needs the id,
    the epoch and the token that only `accept` ever returned, so a copied id/epoch alone is not enough;
    an interrupted slot admits nobody until a receiver accepts; a released one reverts to ordinary use."""
    root = Path(root).resolve()
    owner = read_owner(root, workflow)
    if owner is None:
        if claim:
            raise OwnershipError('Workflow has no accepted continuation owner; the presented claim is invalid')
        return None
    if owner['state'] == 'released':
        if claim:
            raise OwnershipError('The presented owner was released')
        return owner
    if owner['state'] == 'interrupted':
        raise OwnershipError('Owner %s was interrupted; a receiver must accept the latest checkpoint before dispatch'
                             % owner.get('owner'))
    token_hash = owner.get('token_sha256')
    if not claim or not token_hash or not claim.get('token'):
        raise OwnershipError('Owner %s holds the writable slot; present its id, epoch and token' % owner.get('owner'))
    if claim.get('owner') != owner.get('owner') or str(claim.get('epoch')) != str(owner.get('epoch')) \
            or not hmac.compare_digest(_token_sha(claim['token']), token_hash):
        raise OwnershipError('Stale epoch or foreign identity: the presented claim does not match the live owner')
    if owner.get('project_root') != str(root) or owner.get('policy_sha256') != _policy_sha(root):
        raise OwnershipError('Project root or policy changed since this owner was accepted; accept again')
    return owner


def interrupt(root, workflow, failure=None, reason=''):
    """Stop new dispatch to the current owner and keep its state resumable; records the cause."""
    root = Path(root).resolve()
    with _project_lock(root, reentrant=True):
        owner = read_owner(root, workflow) or {'epoch': 0, 'owner': None, 'lineage': []}
        owner.update(state='interrupted', interrupted_at=now(), failure=failure, reason=str(reason)[:300])
        _private_write(folder(root, workflow) / 'owner.json', json.dumps(owner, indent=2, ensure_ascii=False) + '\n')
        return owner


def release(root, workflow):
    root = Path(root).resolve()
    with _project_lock(root, reentrant=True):
        owner = read_owner(root, workflow)
        if owner is None:
            raise ValueError('No owner to release')
        owner.update(state='released', released_at=now())
        _private_write(folder(root, workflow) / 'owner.json', json.dumps(owner, indent=2) + '\n')
        return owner


def reconcile(root, workflow, claim=None):
    """Mark still-running attempts as failed with uncertain side effects; never replays them.

    The failure counter is preserved (a failed attempt still counts toward the two-attempt limit).
    Runs under the project lock and, while a receiver holds the slot, only for that receiver."""
    root = Path(root).resolve()
    with _project_lock(root, reentrant=True):
        owner = read_owner(root, workflow)
        if owner is not None and owner['state'] == 'active':
            fence(root, workflow, claim)
        ledger = _ledger(root)
        changed = []
        for attempt in ledger['attempts']:
            if attempt.get('workflow') == workflow and attempt.get('status') == 'running':
                attempt.update(status='failed', uncertain_side_effects=True,
                               reconciled_at=now(), note='outcome unknown after interruption; not replayed')
                changed.append({'step': attempt.get('step'), 'signature': attempt.get('signature')})
        if changed:
            w.save_ledger(root, ledger)
        return changed


def _load_packet(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PACKET_BYTES:
        raise ValueError('Continuation packet is missing, linked or over budget')
    return json.loads(path.read_text(encoding='utf-8'))


def validate(root, packet_path, receiver, plan_file=None, plan=None):
    """Advisory, lock-free validation for a receiver; only `accept` can take the owner slot.

    The decision here can be stale a moment later, which is why `accept` repeats it inside the
    project lock instead of trusting a caller's earlier result.

    The plan is always verified. It comes from the project-relative path the checkpoint recorded; `plan_file`
    names a different file for the same plan, and `plan` supplies a programmatic plan object when the
    checkpoint recorded no path. Both are held to the recorded identity and fingerprint, never to less."""
    return _validate(root, packet_path, receiver, plan_file, plan)


def _plan_problem(root, packet, plan_file, plan):
    """None when the plan on offer is the checkpoint's plan, otherwise the reason it cannot be accepted."""
    recorded = packet['workflow'].get('plan_file')
    try:
        if plan is not None and plan_file:
            raise ValueError('supply a plan file or an in-memory plan, not both')
        if plan is not None:
            current, fingerprint = w.validate_plan(root, plan, recorded)
        else:
            relative = plan_file or recorded
            if not relative:
                raise ValueError('the checkpoint recorded no plan path; supply the project-relative plan file or the '
                                 'plan object, or create the checkpoint from a plan file')
            w.plan_source(root, relative)
            walk = root
            for part in Path(relative).parts:  # the spelled path, not its resolved target
                walk = walk / part
                if walk.is_symlink():
                    raise ValueError('the plan path may not use symlinks')
            if not w.plan_source(root, relative).is_file():
                raise ValueError('the plan file is missing')
            current, fingerprint = w.read_plan(root, relative)
    except (ValueError, OSError) as exc:
        return 'workflow plan cannot be verified: ' + str(exc)[:200]
    if current['id'] != packet['identity']['task_id']:
        return 'workflow plan identity differs from the checkpoint'
    if fingerprint != packet['workflow']['plan_sha256']:
        return 'workflow plan changed since the checkpoint'
    return None


def _packet_shape_problem(packet):
    """Validate fields consumed by continuation before dereferencing an incoming packet.

    The checksum proves byte integrity, not schema validity or provenance. Keep
    optional telemetry extensible; malformed operational references fail closed.
    """
    if type(packet.get('schema_version')) is not int:
        return 'schema_version must be an integer'
    for name in ('identity', 'workflow', 'source', 'completed_steps'):
        if not isinstance(packet.get(name), dict): return name + ' must be an object'
    identity = packet['identity']
    for name in ('project_id', 'checkout_id', 'project_root', 'task_id'):
        if not isinstance(identity.get(name), str) or not identity[name]:
            return 'identity.' + name + ' must be a nonempty string'
    if not w.ID.fullmatch(identity['task_id']): return 'identity.task_id is invalid'
    workflow = packet['workflow']
    if not isinstance(workflow.get('plan_sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', workflow['plan_sha256']):
        return 'workflow.plan_sha256 must be a SHA256 digest'
    if workflow.get('plan_file') is not None and not isinstance(workflow['plan_file'], str):
        return 'workflow.plan_file must be a string or null'
    if not isinstance(packet.get('policy_sha256'), str) or not re.fullmatch(r'[a-f0-9]{64}', packet['policy_sha256']):
        return 'policy_sha256 must be a SHA256 digest'
    source = packet['source']
    if 'base_revision' not in source or source['base_revision'] is not None and not isinstance(source['base_revision'], str):
        return 'source.base_revision must be a string or null'
    if not isinstance(source.get('dirty'), dict) or not isinstance(source['dirty'].get('entries'), dict):
        return 'source.dirty.entries must be an object'
    for step, record in packet['completed_steps'].items():
        if not isinstance(step, str) or not w.ID.fullmatch(step) or not isinstance(record, dict):
            return 'completed_steps must map step IDs to records'
        for name in ('inputs', 'outputs'):
            hashes = record.get(name)
            if not isinstance(hashes, dict) or any(not isinstance(path, str) or digest is not None and not isinstance(digest, str)
                                                  for path, digest in hashes.items()):
                return 'completed_steps.' + step + '.' + name + ' must be a path/hash object'
    if packet.get('producer') is not None and not isinstance(packet['producer'], dict):
        return 'producer must be an object or null'
    return None


def _receiver_problem(receiver):
    import model_host
    if not isinstance(receiver, dict) or not isinstance(receiver.get('id'), str) \
            or not w.ID.fullmatch(receiver['id']) or receiver.get('host') not in model_host.HOSTS:
        return 'receiver must name an id and a supported host'
    model = receiver.get('model')
    if model is not None and (not isinstance(model, str) or not model.strip()):
        return 'receiver model must be a nonempty string or null'
    return None


def _validate(root, packet_path, receiver, plan_file=None, plan=None):
    """Everything a receiver must hold before it may continue. Returns {accepted, reasons, ...}."""
    import model_host
    import project_binding as pb
    root = Path(root).resolve()
    reasons, notes = [], []
    result = {'accepted': False, 'reasons': reasons, 'stale_steps': [], 'preserved_steps': [],
              'pending_actions': [], 'receiver_profile': None}
    try:
        packet = _load_packet(packet_path)
    except (ValueError, OSError) as exc:
        reasons.append(str(exc))
        return result
    if not isinstance(packet, dict) or packet.get('kind') != KIND or packet.get('schema_version') != SCHEMA_VERSION:
        reasons.append('not a supported continuation packet')
        return result
    body = {k: v for k, v in packet.items() if k != 'packet_sha256'}
    if packet.get('packet_sha256') != sha(body):
        reasons.append('packet hash mismatch: corrupt or edited')
        return result
    problem = _packet_shape_problem(packet)
    if problem:
        reasons.append('malformed continuation packet: ' + problem)
        return result
    identity = packet['identity']
    try:
        binding = pb.load_binding(root)
    except ValueError as exc:
        reasons.append('receiving project is not bound here: ' + str(exc))
        return result
    if identity['project_root'] != str(root):
        reasons.append('different root: moving to another machine or root needs an explicit rebind')
    if identity['project_id'] != binding['project_id'] or identity['checkout_id'] != binding['checkout_id']:
        reasons.append('project or checkout identity does not match the receiving binding')
    if reasons:
        return result
    workflow = identity['task_id']
    latest = committed_latest(root, workflow)
    if latest is None:
        reasons.append('the latest checkpoint is missing, corrupt or not backed by its sequence record')
    elif latest.get('packet_sha256') != packet['packet_sha256']:
        reasons.append('stale or copied packet: it is not the latest checkpoint of this workflow')
    if packet['policy_sha256'] != _policy_sha(root):
        reasons.append('project policy changed since the checkpoint')
    problem = _plan_problem(root, packet, plan_file, plan)
    if problem:
        reasons.append(problem)
    active = w.active_workflow(root)
    if active and active['workflow'] != workflow:
        reasons.append('another workflow holds the project: ' + active['workflow'])
    task = pb.reservation(root)
    if task and task['task_id'] != workflow:
        reasons.append('another context task holds the project: ' + task['task_id'])
    owner = read_owner(root, workflow)
    if owner and owner['state'] == 'active':
        reasons.append('live owner %s holds the writable slot; it must be interrupted or released first'
                       % owner.get('owner'))
    problem = _receiver_problem(receiver)
    if problem:
        reasons.append(problem)
    else:
        result['receiver_profile'] = model_host.capability_profile(receiver['host'], receiver.get('model'))
        producer = packet.get('producer') or {}
        if producer.get('profile_fingerprint') == result['receiver_profile']['fingerprint'] and producer.get('host'):
            notes.append('receiver profile equals the producer profile; recomputed, not copied')
    # Scoped re-verification: steps whose recorded outputs no longer match are stale; the rest stay valid.
    for step_id, record in packet['completed_steps'].items():
        current = {}
        for relative in record['outputs']:
            try:
                path = w.safe_path(root, relative)
                current[relative] = w.digest(path.read_bytes()) if path.is_file() else None
            except ValueError:
                current[relative] = None
        (result['preserved_steps'] if current == record['outputs'] else result['stale_steps']).append(step_id)
    recorded_dirty = packet['source']['dirty']['entries']
    now_dirty = dirty_fingerprints(root)['entries']
    result['source_drift'] = sorted(name for name in set(recorded_dirty) | set(now_dirty)
                                    if recorded_dirty.get(name) != now_dirty.get(name))
    head = (_git(root, 'rev-parse', 'HEAD') or b'').decode().strip() or None
    result['revision_changed'] = head != packet['source']['base_revision']
    if result['revision_changed']:
        result['pending_actions'].append('base revision moved; re-verify affected evidence')
    if any(a['status'] == 'running' for a in _ledger(root)['attempts'] if a.get('workflow') == workflow):
        result['pending_actions'].append('reconcile in-flight attempts (uncertain side effects) before any dispatch')
    if result['stale_steps']:
        result['pending_actions'].append('re-verify stale steps: ' + ', '.join(result['stale_steps']))
    result['notes'] = notes
    result['accepted'] = not reasons
    return result


def accept(root, packet_path, receiver, plan_file=None, plan=None):
    """Validate and claim the single writable owner slot in one critical section.

    The project lock is the same non-reentrant lock a running workflow holds, so a live run, a second
    receiver, `interrupt`, `release` and `reconcile` all serialise with this decision. Validation runs
    inside it via `_validate`, which takes no lock, so the lock is never acquired twice. The returned
    `owner_token` is shown once; only its hash is stored. Budgets and counters are never touched."""
    root = Path(root).resolve()
    with _project_lock(root, reentrant=False):
        result = _validate(root, packet_path, receiver, plan_file, plan)
        if not result['accepted']:
            raise ValueError('Continuation refused: ' + '; '.join(result['reasons']))
        packet = _load_packet(packet_path)
        workflow = packet['identity']['task_id']
        previous = read_owner(root, workflow) or {'epoch': 0, 'lineage': []}
        token = secrets.token_hex(32)
        owner = {'state': 'active', 'epoch': previous.get('epoch', 0) + 1, 'owner': receiver['id'],
                 'host': receiver['host'], 'model': receiver.get('model'),
                 'receiver_profile_fingerprint': result['receiver_profile']['fingerprint'],
                 'packet_sha256': packet['packet_sha256'], 'accepted_at': now(),
                 'project_root': str(root), 'policy_sha256': packet['policy_sha256'],
                 'token_sha256': _token_sha(token),
                 'lineage': previous.get('lineage', []) + ([{'owner': previous['owner'], 'epoch': previous['epoch'],
                                                              'state': previous['state']}] if previous.get('owner') else [])}
        _private_write(folder(root, workflow) / 'owner.json', json.dumps(owner, indent=2, ensure_ascii=False) + '\n')
        result['owner'] = owner
        result['owner_token'] = token
        return result


def resume(root, plan_file, receivers, max_switches, max_model_requests, image=w.DEFAULT_IMAGE,
           allow_host_cli=False, claim=None):
    """Opt-in quota fallback under existing ownership, checkpoints and aggregate admission.

    Receivers and integer bounds are operator inputs. Only a confirmed structured
    quota rejection can switch hosts; uncertain dispatches are never replayed.
    The durable switch count and request ledger survive controller restarts.
    """
    import admission
    import model_host
    if admission.current() is not None:
        raise ValueError('Quota resume needs its own workflow admission scope; nested batch fallback is unsupported')
    if type(max_switches) is not int or not 1 <= max_switches <= 8:
        raise ValueError('max-switches must be an integer from 1 to 8')
    if type(max_model_requests) is not int or not 1 <= max_model_requests <= 32:
        raise ValueError('max-model-requests must be an integer from 1 to 32')
    if not isinstance(receivers, list) or not 1 <= len(receivers) <= 8:
        raise ValueError('Receivers must be a bounded ordered list of 1..8 explicit hosts')
    for receiver in receivers:
        problem = _receiver_problem(receiver)
        if problem: raise ValueError(problem)
        if not isinstance(receiver, dict) or set(receiver) - {'id', 'host', 'model'} or not isinstance(receiver.get('id'), str) \
                or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', receiver['id']) or receiver.get('host') not in model_host.HOSTS:
            raise ValueError('Each receiver needs a stable id and supported host')
        if receiver['host'] in model_host.CLI_HOSTS and not allow_host_cli:
            raise ValueError('Native receivers require explicit --allow-host-cli')
        if receiver['host'] in ('openai', 'anthropic') and (not isinstance(receiver.get('model'), str) or not receiver['model'].strip()):
            raise ValueError('API receivers require an explicit model')
    if len({r['id'] for r in receivers}) != len(receivers): raise ValueError('Receiver ids must be unique')
    root = Path(root).resolve(strict=True)
    import project_binding
    binding = project_binding.load_binding(root)
    plan, fingerprint = w.read_plan(root, plan_file)
    checkpoint_dir = folder(root, plan['id'])
    config_path = w.safe_path(root, '.crewloom/handoffs/' + plan['id'] + '/fallback.json', internal=True)
    identity = {'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'], 'project_root': str(root)}
    def read_config():
        if not config_path.exists(): return None
        metadata = config_path.stat()
        if not config_path.is_file() or metadata.st_nlink != 1 or metadata.st_size > 65536:
            raise ValueError('Fallback record must be a bounded regular file with one link')
        value = json.loads(config_path.read_text())
        if not isinstance(value, dict) or value.get('schema_version') != 1 or value.get('identity') != identity \
                or type(value.get('switches')) is not int or not 0 <= value['switches'] <= 8 \
                or type(value.get('max_switches')) is not int or not 1 <= value['max_switches'] <= 8:
            raise ValueError('Malformed or foreign fallback record')
        return value
    with _project_lock(root, reentrant=True):
        fence(root, plan['id'], claim)
        if claim is not None: claim = dict(claim, use_receiver_host=True)
        old = read_config()
        receiver_hash = sha(receivers)
        if old and (old.get('receivers_sha256') != receiver_hash or old.get('plan_sha256') != fingerprint):
            raise ValueError('Fallback receivers or immutable plan changed; use a reviewed new workflow')
        config = old or {'schema_version': 1, 'identity': identity, 'plan_sha256': fingerprint, 'receivers_sha256': receiver_hash,
                         'switches': 0, 'max_switches': max_switches}
        config['max_switches'] = min(config['max_switches'], max_switches)
        _private_write(config_path, json.dumps(config, indent=2))
    admission_dir = w.safe_path(root, '.crewloom/workflows/' + plan['id'] + '/admission', internal=True)
    admission.configure(admission_dir, plan['id'], {'max_model_requests': max_model_requests})
    def finish(report, details):
        # This controller releases only its own authenticated, settled slot. No token
        # needs to be written to disk or leaked in a retained workflow report.
        if claim is not None:
            with _project_lock(root, reentrant=True):
                fence(root, plan['id'], claim)
                release(root, plan['id'])
        return dict(report, fallback=details)
    with admission.context(admission_dir, plan['id']):
        while True:
            # A prior uncertain attempt is retained and requires explicit reconciliation/review.
            if any(a.get('workflow') == plan['id'] and (a.get('status') == 'running' or a.get('uncertain_side_effects')) for a in _ledger(root)['attempts']):
                raise ValueError('Uncertain prior dispatch prevents automatic replay; inspect and reconcile explicitly')
            report = w.run(root, plan, fingerprint, image, allow_host_cli=allow_host_cli, owner=claim, plan_file=plan_file)
            state = w.state_for(root, plan, fingerprint)[1]
            pending = next((s for s in plan['steps'] if state['steps'].get(s['id'], {}).get('status') != 'complete'), None)
            failure = (state['steps'].get(pending['id'], {}).get('failure') or {}) if pending else {}
            if report.get('status') != 'failed' or not pending or pending.get('kind') != 'model' \
                    or failure.get('kind') != 'quota_exhausted' or failure.get('confidence') != 'confirmed' \
                    or failure.get('side_effects') == 'uncertain':
                return finish(report, {'switches': config['switches'], 'automatic_switch_eligible': False})
            with _project_lock(root, reentrant=True):
                fence(root, plan['id'], claim)
                config = read_config()
                if config['switches'] >= min(config['max_switches'], len(receivers)):
                    return finish(report, {'switches': config['switches'], 'stop_reason': 'switch budget exhausted'})
                receiver = receivers[config['switches']]
                # Charge before ownership transfer; a crash never grants a replacement switch.
                config['switches'] += 1
                _private_write(config_path, json.dumps(config, indent=2))
                interrupt(root, plan['id'], failure, 'Explicit bounded quota fallback')
            accepted = accept(root, checkpoint_dir / 'latest.json', receiver, plan_file=plan_file)
            claim = {'owner': accepted['owner']['owner'], 'epoch': accepted['owner']['epoch'],
                     'token': accepted['owner_token'], 'use_receiver_host': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'show', 'validate', 'accept', 'interrupt', 'reconcile', 'release', 'resume'))
    parser.add_argument('--project', required=True)
    parser.add_argument('--workflow')
    parser.add_argument('--plan', help='Project-relative workflow plan file (create: the plan to record; validate and '
                                       'accept: the recorded plan path by default, or another file for the same plan)')
    parser.add_argument('--packet')
    parser.add_argument('--receiver-id')
    parser.add_argument('--receiver-host')
    parser.add_argument('--receiver-model')
    parser.add_argument('--owner-epoch', help='Epoch returned by accept; the token comes from ' + TOKEN_ENVIRONMENT)
    parser.add_argument('--failure', help='JSON classification from model_host.classify_failure')
    parser.add_argument('--reason', default='')
    parser.add_argument('--receivers', help='Explicit ordered JSON list of receiver id/host/model objects for bounded quota resume')
    parser.add_argument('--max-switches', type=int, help='Persistent maximum host switches (1..8); required for resume')
    parser.add_argument('--max-model-requests', type=int, help='Aggregate workflow request ceiling (1..32), never reset on resume')
    parser.add_argument('--image', default=w.DEFAULT_IMAGE)
    parser.add_argument('--allow-host-cli', action='store_true')
    args = parser.parse_args(argv)
    try:
        root = Path(args.project).resolve()
        if args.action == 'resume':
            result = resume(root, args.plan or 'workflow.json', json.loads(args.receivers or 'null'),
                            args.max_switches, args.max_model_requests, args.image, args.allow_host_cli,
                            claim_from(args.receiver_id, args.owner_epoch))
        elif args.action == 'create':
            plan, fingerprint = w.read_plan(root, args.plan)
            state = w.state_for(root, plan, fingerprint)[1]
            result = write_checkpoint(root, plan, state, _ledger(root), 'manual', None, None, None, args.plan)
        elif args.action == 'show':
            result = _load_packet(args.packet or folder(root, args.workflow) / 'latest.json')
        elif args.action == 'interrupt':
            result = interrupt(root, args.workflow, json.loads(args.failure) if args.failure else None, args.reason)
        elif args.action == 'reconcile':
            result = {'reconciled': reconcile(root, args.workflow, claim_from(args.receiver_id, args.owner_epoch))}
        elif args.action == 'release':
            result = release(root, args.workflow)
        else:
            receiver = {'id': args.receiver_id, 'host': args.receiver_host, 'model': args.receiver_model}
            packet = args.packet or str(folder(root, args.workflow) / 'latest.json')
            result = (accept if args.action == 'accept' else validate)(root, packet, receiver, args.plan)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get('accepted', True) is not False and (args.action != 'resume' or result.get('status') == 'complete') else 2
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, OwnershipError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
