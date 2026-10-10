"""Opt-in, machine-shared admission ledger for managed model calls (POSIX).

Request limits are enforced before dispatch. Dollar amounts are conservative admission
allowances, not a vendor billing cap: unknown/failed calls retain their allowance and an
observed overrun blocks subsequent admission. No prompts, credentials or artifacts live here.
"""
import argparse
import contextlib
import json
import math
import os
import stat
import tempfile
import time
import uuid
from pathlib import Path


def private_directory(value, create=True):
    path = Path(value).absolute()
    for part in [*reversed(path.parents), path]:
        if (part / 'crewloom.project.json').exists():
            raise ValueError('Shared control directory must live outside bound projects')
        if part.is_symlink():
            raise ValueError('Control directory may not follow symlinks')
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    elif not path.is_dir():
        raise ValueError('Existing configured control directory required')
    if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError('Control directory must be owner-only (chmod 700)')
    return path


def read(path):
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4 * 1024 * 1024:
        raise ValueError('Invalid or oversized control record')
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Control record must be owner-only')
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(data) > 4 * 1024 * 1024:
        raise ValueError('Control record size exhausted')
    # Refuse redirected records, including dangling links, before replacement.
    read(path)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def locked(folder, name='state.lock', blocking=True):
    import fcntl
    path = folder / name
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Invalid control lock')
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield
    finally:
        os.close(fd)


def money(value):
    if isinstance(value, bool):
        raise ValueError('Dollar allowance must be finite and nonnegative')
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError('Dollar allowance must be finite and nonnegative')
    # Integers avoid rounding drift in concurrent reservations.
    return math.ceil(number * 1_000_000)


def configure(directory, max_requests, max_usd=None, reserve_usd=None):
    if type(max_requests) is not int or not 1 <= max_requests <= 10000:
        raise ValueError('max_requests must be an integer from 1 to 10000')
    if (max_usd is None) != (reserve_usd is None):
        raise ValueError('Dollar control needs both max_usd and reserve_usd')
    maximum = money(max_usd) if max_usd is not None else None
    allowance = money(reserve_usd) if reserve_usd is not None else None
    if maximum is not None and (not allowance or allowance > maximum):
        raise ValueError('Per-call allowance must be positive and within total allowance')
    folder = private_directory(directory)
    with locked(folder):
        if read(folder / 'budget.json') is not None:
            raise ValueError('Budget already exists; use a new explicit budget period, never reset live reservations')
        write(folder / 'budget.json', {'schema_version': 1, 'max_requests': max_requests,
              'max_microusd': maximum, 'reserve_microusd': allowance, 'calls': []})
    return summary(directory)


def _state(folder):
    state = read(folder / 'budget.json')
    if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('calls'), list):
        raise ValueError('Configured shared budget required')
    if type(state.get('max_requests')) is not int or not 1 <= state['max_requests'] <= 10000:
        raise ValueError('Malformed budget request limit')
    for key in ('max_microusd', 'reserve_microusd'):
        if state.get(key) is not None and (type(state[key]) is not int or state[key] < 1):
            raise ValueError('Malformed dollar budget')
    if (state.get('max_microusd') is None) != (state.get('reserve_microusd') is None):
        raise ValueError('Incomplete dollar budget')
    seen = set()
    for call in state['calls']:
        if not isinstance(call, dict) or not isinstance(call.get('id'), str) or call['id'] in seen or call.get('status') not in ('reserved', 'known', 'unknown'):
            raise ValueError('Malformed budget call')
        seen.add(call['id'])
        if type(call.get('charged_microusd')) is not int or call['charged_microusd'] < 0:
            raise ValueError('Malformed budget charge')
    return state


def reserve(directory, identity):
    import project_binding as pb
    root = Path(identity['project_root']).resolve(strict=True)
    binding = pb.load_binding(root)
    if any(binding[key] != identity[key] for key in ('project_id', 'checkout_id')):
        raise ValueError('Budget request identity does not match project binding')
    folder = private_directory(directory)
    with locked(folder):
        state = _state(folder)
        if len(state['calls']) >= state['max_requests']:
            raise ValueError('Shared model request budget exhausted')
        charge = state['reserve_microusd'] or 0
        if state['max_microusd'] is not None and sum(c['charged_microusd'] for c in state['calls']) + charge > state['max_microusd']:
            raise ValueError('Shared dollar admission allowance exhausted')
        call = {'id': uuid.uuid4().hex, 'status': 'reserved', 'charged_microusd': charge,
                'at': time.time(), **{key: identity[key] for key in ('project_id', 'checkout_id', 'workflow', 'step')}}
        state['calls'].append(call)
        write(folder / 'budget.json', state)
        return call['id']


def settle(directory, call_id, cost=None):
    charge = money(cost) if cost is not None else None
    folder = private_directory(directory)
    with locked(folder):
        state = _state(folder)
        call = next((c for c in state['calls'] if c['id'] == call_id), None)
        if call is None or call['status'] != 'reserved':
            raise ValueError('Unknown or already settled budget reservation')
        call['status'] = 'unknown' if charge is None else 'known'
        if charge is not None:
            call['charged_microusd'] = charge
        write(folder / 'budget.json', state)


def summary(directory):
    folder = private_directory(directory, create=False)
    with locked(folder):
        state = _state(folder)
        charged = sum(c['charged_microusd'] for c in state['calls'])
        return {'requests': len(state['calls']), 'max_requests': state['max_requests'],
                'reserved_or_reported_usd': charged / 1_000_000,
                'max_usd': None if state['max_microusd'] is None else state['max_microusd'] / 1_000_000,
                'unknown_cost_calls': sum(c['status'] != 'known' for c in state['calls']),
                'over_allowance': state['max_microusd'] is not None and charged > state['max_microusd']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('configure', 'status'))
    parser.add_argument('--directory', required=True)
    parser.add_argument('--max-requests', type=int)
    parser.add_argument('--max-usd', type=float)
    parser.add_argument('--reserve-usd', type=float)
    args = parser.parse_args(argv)
    try:
        result = configure(args.directory, args.max_requests, args.max_usd, args.reserve_usd) if args.action == 'configure' else summary(args.directory)
        print(json.dumps(result)); return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error': str(exc)})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
