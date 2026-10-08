"""Project-bound workflow execution, resumable evidence, and Docker isolation."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from pathlib import Path

import crewloom_resources as resources

LIBRARY = resources.distribution_root()
ROLES = resources.roles_dir()
ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*$')
MEMORY = ('ARCHITECTURE', 'COMPLETED', 'CHALLENGES', 'IDEAS_VAULT', 'ROADMAP_TODO')
# Project policy files a declared artifact may never name. `crewloom.project.json` is the local
# project binding, and `REPOSITORY_SCOPE.json` is the reviewed declaration of which top-level files
# and directories belong to this project at all. Both are the authority that decides what a managed
# run is allowed to produce, so a step output can never become either of them: a run that could
# widen its own project scope, or replace the policy that authorised it, would be reviewing itself.
# These are the project policy files; Git state, the native host configuration trees and the root
# host configuration files are refused by `RESERVED_KEYS` and `NATIVE_KEYS` instead.
PROTECTED = ('crewloom.project.json', 'REPOSITORY_SCOPE.json')
# Runtime and Git state a declared artifact may never name, in any spelling a filesystem is
# willing to resolve. APFS and HFS+ compare names without case or normalization, so `Result.txt`,
# `result.txt` and an NFD spelling of either are one file there while staying different strings;
# the portable answer is to compare the folded forms before every reserved-name and collision
# check rather than to ask the host filesystem which way it resolves a name.
RESERVED = ('.crewloom', '.git')
# The native host configuration trees, and the root host configuration files themselves. `.codex`,
# `.claude` and `.opencode` are where Codex, Claude Code and OpenCode actually read project
# configuration and plugins from, and `opencode.json`/`opencode.jsonc` in the project root are
# OpenCode's own project configuration (https://opencode.ai/docs/config/). A declared artifact that
# names one of these is asking to become the authority that decides what a host agent may write, so
# declaring it never grants it. Crewloom's own installer still writes `.codex/hooks.json`,
# `.claude/settings.json` and `.opencode/plugins/crewloom-lifecycle.js`: that is an explicitly
# authorized control write through the metadata path, not a declared agent artifact, and it is
# deliberately not routed through this boundary.
NATIVE_TREES = ('.codex', '.claude', '.opencode')
NATIVE_CONFIGS = ('opencode.json', 'opencode.jsonc')
DEFAULT_IMAGE = 'python:3.14-slim'


def folded(value):
    """One spelling-independent form of a path component.

    Case folding plus NFC is the conservative portable comparison: two components that fold
    together are refused as one destination on every platform, including a genuinely
    case-sensitive one where they would have been two files. Nothing is probed and no host
    setting is read, so the decision is the same on a developer Mac, in CI and in a container.
    """
    return unicodedata.normalize('NFC', str(value)).casefold()


PROTECTED_KEYS = frozenset(folded(name) for name in PROTECTED)
RESERVED_KEYS = frozenset(folded(name) for name in RESERVED)
NATIVE_KEYS = frozenset(folded(name) for name in NATIVE_TREES + NATIVE_CONFIGS)


def path_key(relative):
    """The key that decides whether two declared project paths are one destination.

    `first.txt` and `./first.txt` fold to one key for the same reason `Result.txt` and
    `result.txt` do: the key is the path as names are compared, not as they were spelled.
    """
    return '/'.join(folded(part) for part in Path(relative).parts)


def physical_identity(path):
    """The device and inode a path resolves to, or ``None`` when nothing is there.

    Lexical containment cannot see a case alias, because macOS `resolve()` keeps the spelling
    the caller asked for: `(root/'VENDOR')` and `(root/'vendor')` stay different strings for a
    directory that is demonstrably one inode. Identity is what the filesystem itself used to
    answer the same question.
    """
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_dev, info.st_ino


def inside(path, containers):
    """Whether one resolved path lies inside any of these roots, compared physically as well.

    The lexical test is kept because it also covers a container that does not exist yet, and
    every existing ancestor of the path is then compared by device and inode with every
    container. That reaches a trusted root through any spelling the host resolves to it, and
    it decides a destination that does not exist yet by its nearest existing ancestor, so no
    probe file and no host configuration change is needed to know which filesystem this is.
    """
    identities = set()
    for container in containers:
        container = Path(container)
        if path.is_relative_to(container):
            return True
        identity = physical_identity(container)
        if identity is not None:
            identities.add(identity)
    if not identities:
        return False
    walk = Path(path)
    while True:
        identity = physical_identity(walk)
        if identity is not None and identity in identities:
            return True
        parent = walk.parent
        if parent == walk:
            return False
        walk = parent


def safe_path(root, value, internal=False):
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError('Expected a project-relative path')
    path = (root / value).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Path escapes selected project: ' + value)
    if internal:
        current = root
        for part in Path(value).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError('Runtime state path may not use symlinks')
    if not internal and any(folded(part) in RESERVED_KEYS
                            for part in (*Path(value).parts, *path.relative_to(root).parts)):
        raise ValueError('Workflow artifacts cannot use runtime or Git state')
    return path


def native_authorities(root):
    """The exact native host authority paths of one project: three trees and two root configs.

    These are the only paths compared by identity, so the check answers "is this one file the
    host's own policy" with a fixed number of `stat` calls instead of a project scan.
    """
    return [Path(root) / name for name in NATIVE_TREES + NATIVE_CONFIGS]


def host_authority_conflict(root, relative):
    """The native host authority one declared path reaches, however it is spelled, or ``None``.

    Three spellings have to be caught, because a reserved file can be reached without ever being
    written down. `src/../.codex/hooks.json` names an ordinary directory first, and a symlinked
    `alias -> .codex` never spells the tree at all, so the resolved path is compared exactly as the
    written one is. Case and normalization are folded on both sides because APFS and HFS+ resolve
    them as one name; nothing is probed and no host setting is read, so the answer is the same on a
    developer Mac, in CI and in a container.

    A hardlink is one inode behind two names, so no spelling of the declared path shows the tree it
    belongs to: `ordinary.json` linked to `opencode.json` reaches the host's own configuration while
    spelling nothing reserved. What does reach it is the file's own identity, so the declared path
    is compared by device and inode with this project's exact native authorities. That is a fixed
    set of paths, not a recursive scan, so the check stays bounded however large the project is.

    Only a *name* or a *file* is reserved, never a subtree pattern: `src/settings.json` and
    `docs/.claude-notes.md` stay ordinary project configuration.
    """
    parts = Path(relative).parts
    resolved = Path(root / relative).resolve()
    try:
        parts = tuple(parts) + resolved.relative_to(root).parts
    except ValueError:
        # A path that leaves the project is not this project's host authority. The caller has
        # already refused such a path, and a resolution error is raised rather than swallowed,
        # because a check that quietly passes when it cannot answer is not a check.
        pass
    for part in parts:
        if folded(part) in NATIVE_KEYS:
            return part
    for authority in native_authorities(root):
        if inside(resolved, [authority]):
            return str(authority)
    return None


def declared_path(root, relative):
    """One declared step artifact path, refusing project control and host authority files.

    `crewloom.project.json` sets the enforcement policy, and `REPOSITORY_SCOPE.json` declares which
    top-level files and directories belong to this project. The reviewer issuance authority now
    lives under `.crewloom`, which `safe_path` already refuses as runtime state, so a step
    may neither read it nor replace it and cannot forge a reviewer proof or weaken the
    policy that authorised it. A native host configuration tree or root host configuration file
    is refused for the same reason and by the same rule: the host reads its own policy from
    there, so a managed step that could write it could switch off the guard constraining it.
    This is the artifact boundary only: Crewloom's own control paths still resolve through
    `safe_path` and its installer writes its own control configuration as metadata.

    Every name is folded before it is matched, so `CREWLOOM.PROJECT.JSON` and
    `repository_scope.json` are refused on a case-insensitive filesystem where they are the same
    files, and refused identically everywhere else so the rule a step is held to does not depend
    on the host it runs on.
    """
    path = safe_path(root, relative)
    if folded(Path(relative).name) in PROTECTED_KEYS:
        raise ValueError('Workflow artifacts cannot use project control files: ' + str(relative))
    if host_authority_conflict(root, relative) is not None:
        raise ValueError('Workflow artifacts cannot use native host configuration: ' + str(relative))
    return path


def digest(value):
    return hashlib.sha256(value).hexdigest()


def hashes(root, paths):
    result = {}
    for relative in paths:
        path = declared_path(root, relative)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing or empty artifact: ' + relative)
        if path.stat().st_size>16*1024*1024:raise ValueError('Artifact input budget exceeded: '+relative)
        hasher=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(65536),b''):hasher.update(chunk)
        result[relative] = hasher.hexdigest()
    return result


def read_plan(root, filename):
    source = safe_path(root, filename)
    plan = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(plan, dict) or plan.get('schema_version') != 1 or not ID.fullmatch(str(plan.get('id', ''))):
        raise ValueError('Workflow requires schema_version 1 and a stable kebab-case id')
    if plan.get('language', 'en') not in ('en', 'ar'):
        raise ValueError('Language must be en or ar')
    unknown = set(plan) - {'schema_version', 'id', 'language', 'steps', 'criteria'}
    if unknown:
        raise ValueError('Unknown workflow plan fields: ' + ', '.join(sorted(unknown)))
    if 'criteria' in plan:
        safe_path(root, plan['criteria'])
        if not safe_path(root, plan['criteria']).is_file():
            raise ValueError('Workflow criteria file is missing')
    steps = plan.get('steps')
    if not isinstance(steps, list) or not steps:
        raise ValueError('Workflow needs at least one step')
    seen = set()
    outputs = set(); output_targets = set(); output_keys = set()
    plan_path = safe_path(root, filename); plan_key = path_key(filename)
    for step in steps:
        if not isinstance(step, dict) or not ID.fullmatch(str(step.get('id', ''))) or step['id'] in seen:
            raise ValueError('Step IDs must be unique kebab-case')
        seen.add(step['id'])
        role = step.get('role')
        if not isinstance(role, str) or not ID.fullmatch(role) or not (ROLES / role / 'SKILL.md').is_file():
            raise ValueError('Unknown role')
        kind = step.get('kind', 'command')
        if kind not in ('command', 'task', 'model') or not isinstance(step.get('summary'), str) or not step['summary'].strip():
            raise ValueError('Each step needs a summary and command/task/model kind')
        if kind == 'command':
            argv = step.get('argv')
            if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a or '\0' in a for a in argv):
                raise ValueError('Command argv must be a nonempty string array')
        if kind == 'model':
            from model_host import HOSTS
            if step.get('host') not in HOSTS:
                raise ValueError('Model step needs an explicit model provider/host')
            if 'model' in step and (not isinstance(step['model'], str) or not step['model'].strip()):
                raise ValueError('Model identifier must be nonempty')
        timeout = step.get('timeout_seconds', 60)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError('Timeout must be an integer from 1 to 3600')
        for field in ('inputs', 'outputs'):
            values = step.get(field)
            if not isinstance(values, list) or (field == 'outputs' and not values):
                raise ValueError('Each step needs inputs and nonempty outputs lists')
            for value in values:
                resolved = safe_path(root, value)
                if field == 'outputs' and (resolved == plan_path or path_key(value) == plan_key
                                           or any(resolved == safe_path(root, old) for old in outputs)):
                    raise ValueError('Each artifact needs one owner and cannot overwrite the plan')
                if value in outputs and field == 'outputs':
                    raise ValueError('Each artifact needs one owner')
        for value in step['outputs']:
            target = safe_path(root, value)
            key = path_key(value)
            if target in output_targets or key in output_keys:
                # The folded key is compared too, so two steps cannot own one artifact by
                # spelling it two ways where the filesystem would resolve both to one file.
                raise ValueError('Each artifact needs one owner after canonicalization')
            output_targets.add(target)
            output_keys.add(key)
            if value in outputs or value == filename:
                raise ValueError('Each artifact needs one owner and cannot overwrite the plan')
            outputs.add(value)
    return plan, digest(json.dumps(plan, sort_keys=True).encode())


def runtime(root, ident):
    return safe_path(root, '.crewloom/workflows/' + ident, internal=True)


def save(folder, state):
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'state.json'
    if target.is_symlink():
        raise ValueError('State file may not be a symlink')
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(state, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, target)


_LOCKS = threading.local()


def _lock_depth():
    """Thread-local lock ownership that a forked process can never inherit.

    `fork` copies thread-local storage, so recorded depth is only ever trusted for the
    process that created it. Ownership is therefore keyed by process, thread and the
    canonical folder, and the depth table is dropped whenever the process identity changes.
    """
    state = getattr(_LOCKS, 'state', None)
    if state is None or state['pid'] != os.getpid():
        state = _LOCKS.state = {'pid': os.getpid(), 'depth': {}}
    return state['depth']


def _lock_owner(record):
    """Whether the process that recorded this lock can still be running.

    Signal 0 performs the kernel's existence and permission check without delivering anything,
    so a lock left behind by a killed writer is recognised as abandoned instead of blocking the
    project for good. That probe is POSIX-only: Python documents `os.kill(pid, 0)` on Windows as
    `TerminateProcess`, which would terminate the recorded process rather than inspect it, so no
    platform whose semantics are not verified here is probed at all. Every uncertain case counts
    as alive: an unreadable record, a missing or nonsensical pid, a pid this process may not
    inspect, and every pid on a platform without a safe probe all keep the lock, so reclamation
    never lets a second writer in on a guess and never signals a process it did not mean to
    touch. A recycled pid reads as alive, which fails closed and only asks the operator to clear
    the file, and that is also the only way a lock is released on a non-POSIX host: native
    Windows support is truthful about being manual there, not automatic.
    """
    pid = record.get('pid') if isinstance(record, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or pid == os.getpid():
        return True
    if os.name != 'posix':
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def _lock_record(path):
    """The ownership record in a lock file, or ``None`` when it is not a readable one."""
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and 'pid' in record else None


# The only entries a live reclaimer creates inside its claim directory. Nothing else is ever
# deleted inside a `.reclaim` path on its behalf, so a claim this protocol does not recognise
# is left exactly as it is found and blocks the lock for an operator to reconcile by hand.
CLAIM_ENTRIES = ('owner.json', 'pin')


def _owned_claim(claim):
    """The claim directory when it is a real one this protocol created, else ``None``.

    A `.reclaim` path that is a symlink, is not a directory, or holds anything other than the
    two entries above is refused outright. Deleting unrecognised contents would delete files
    this protocol never created, and following a symlinked claim would delete files in whatever
    directory it happens to point at, so neither is ever attempted.
    """
    if claim.is_symlink() or not claim.is_dir():
        return None
    try:
        found = sorted(item.name for item in claim.iterdir())
    except OSError:
        return None
    if any(name not in CLAIM_ENTRIES for name in found):
        return None
    if any((claim / name).is_symlink() or not (claim / name).is_file() for name in found):
        return None
    return claim


def _discard_claim(claim):
    """Remove exactly the entries a reclaimer created, and nothing else.

    `rmdir` succeeds only on an empty directory, so a claim a competing reclaimer is still
    using, or one holding unrecognised contents, stays in place rather than being emptied. A
    single named `unlink` is used rather than a recursive walk, so no directory tree outside
    the claim can be reached from here at all.
    """
    if claim.is_symlink() or not claim.is_dir():
        return False
    for name in CLAIM_ENTRIES:
        item = claim / name
        if item.is_symlink():
            return False
        try:
            item.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False
    try:
        claim.rmdir()
    except OSError:
        return False
    return True


def _claim_reclamation(folder):
    """Take the exclusive right to reclaim this folder's lock, or ``None``.

    Reclamation itself needs mutual exclusion, otherwise two callers observing the same stale
    file would each conclude it was theirs to remove and both would then create a lock. The
    claim is a directory created with `mkdir`, which is atomic and fails when the name exists.
    A claim left behind by a reclaimer that was itself killed is reconciled exactly once, by
    deleting only its two recorded entries before retrying; a live, unreadable or unrecognised
    claim is left alone and blocks, as it must.
    """
    claim = folder / '.reclaim'
    for attempt in (1, 2):
        try:
            claim.mkdir(mode=0o700)
        except FileExistsError:
            existing = _owned_claim(claim)
            if attempt == 2 or existing is None:
                return None
            record = _lock_record(existing / 'owner.json')
            if record is None or _lock_owner(record):
                return None
            if not _discard_claim(existing):
                return None
            continue
        (claim / 'owner.json').write_text(json.dumps({'pid': os.getpid()}, sort_keys=True))
        return claim
    return None


def _release_reclamation(claim):
    if claim is None:
        return
    _discard_claim(claim)


def _reclaim(folder, path):
    """Remove a lock whose owning process is provably gone; otherwise leave it untouched.

    The observed file is pinned with `link()` before its record is read, so the decision is made
    about one exact inode. The stale file is removed only while `path` still names that same
    inode: a competing reclaimer that installed its own live lock in between therefore keeps it,
    and this caller fails closed instead of deleting the winner's lock with a record it read
    before the winner existed. While the stale file is still present an ordinary acquirer cannot
    create `path` at all, and the reclamation claim admits one reclaimer, so at most one managed
    caller can conclude it holds the root.

    A lock path that is a symlink is never read, pinned or removed: this protocol only ever
    creates a regular file there, so a link at that name is someone else's and is left alone.
    """
    if path.is_symlink():
        return False
    claim = _claim_reclamation(folder)
    if claim is None:
        return False
    pin = claim / 'pin'
    try:
        os.link(path, pin)
    except OSError:
        _release_reclamation(claim)
        return False
    try:
        record = _lock_record(pin)
        if record is None or _lock_owner(record):
            return False
        pinned = os.stat(pin)
        current = os.stat(path)
        if (pinned.st_dev, pinned.st_ino) != (current.st_dev, current.st_ino):
            return False
        path.unlink()
        return True
    except OSError:
        return False
    finally:
        _release_reclamation(claim)


@contextmanager
def project_lock(folder, reentrant=False):
    """The single project lock protocol; internal callers may compose it re-entrantly.

    External writers still contend on the same `O_CREAT|O_EXCL` lock file, so a second
    process is rejected whether it uses `lock` or `project_lock`. A lock left behind by a
    process that was killed mid-step is reclaimed exactly once, because that residue belongs to
    an interrupted run rather than to a live writer. Re-entrancy is scoped to one process and
    one thread, so a forked child contends instead of inheriting ownership.
    """
    folder.mkdir(parents=True, exist_ok=True)
    depth = _lock_depth()
    key = (os.getpid(), threading.get_ident(), os.path.realpath(str(folder)))
    if reentrant and depth.get(key, 0):
        depth[key] += 1
        try:
            yield
        finally:
            depth[key] -= 1
        return
    path = folder / 'lock'
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if not _reclaim(folder, path):
            raise ValueError('Workflow locked: another execution or interrupted host owns the lock')
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError('Workflow locked: another execution or interrupted host owns the lock')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps({'pid': os.getpid(), 'thread': threading.get_ident(),
                                     'folder': key[2]}, sort_keys=True))
        if reentrant:
            depth[key] = depth.get(key, 0) + 1
        yield
    finally:
        if reentrant:
            depth[key] = max(0, depth.get(key, 1) - 1)
        path.unlink(missing_ok=True)


@contextmanager
def lock(folder):
    """Public, strictly non-reentrant project lock; external writers contend on the same file."""
    with project_lock(folder, reentrant=False):
        yield


def save_ledger(root, ledger):
    folder = safe_path(root, '.crewloom', internal=True)
    target = safe_path(root, '.crewloom/attempts.json', internal=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, delete=False) as stream:
        temporary = Path(stream.name); json.dump(ledger, stream, ensure_ascii=False)
    os.replace(temporary, target)


def state_for(root, plan, fingerprint):
    folder = runtime(root, plan['id'])
    path = folder / 'state.json'
    if path.exists():
        if path.is_symlink():
            raise ValueError('State file may not be a symlink')
        state = json.loads(path.read_text())
        if not isinstance(state, dict) or state.get('schema_version') != 1 or not isinstance(state.get('steps'), dict):
            raise ValueError('Malformed workflow state')
        if state.get('status') not in ('pending', 'running', 'failed', 'complete', 'awaiting_task', 'blocked', 'cancelled'):
            raise ValueError('Malformed workflow progress status')
        definitions = {step['id']: step for step in plan['steps']}
        for ident, record in state['steps'].items():
            if ident not in {step['id'] for step in plan['steps']} or not isinstance(record, dict) or not isinstance(record.get('attempts'), list):
                raise ValueError('Malformed workflow step state')
            if record.get('status') not in ('pending', 'running', 'failed', 'complete') or record.get('role') != definitions[ident]['role']:
                raise ValueError('Malformed workflow ownership or step status')
            if any(not isinstance(attempt, dict) or not isinstance(attempt.get('signature'), str) for attempt in record['attempts']):
                raise ValueError('Malformed workflow attempt history')
            if record.get('status') == 'complete':
                for field in ('inputs', 'outputs'):
                    values = record.get(field)
                    if not isinstance(values, dict) or set(values) != set(definitions[ident][field]) or any(not isinstance(key, str) or not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value) for key, value in values.items()):
                        raise ValueError('Malformed workflow artifact evidence')
        if state.get('project_root') != str(root) or state.get('plan_sha256') != fingerprint:
            raise ValueError('State belongs to another project or plan revision; use a new workflow ID')
        return folder, state
    folder.mkdir(parents=True, exist_ok=True)
    return folder, {'schema_version': 1, 'project_root': str(root), 'workflow': plan['id'],
                    'plan_sha256': fingerprint, 'steps': {}, 'status': 'pending',
                    'project_id': binding_id(root)[0], 'checkout_id': binding_id(root)[1]}


def inspect_image(image):
    if not hasattr(os, 'getuid'):
        raise ValueError('Workflow containers require Linux, macOS or WSL; native Windows is not supported yet')
    if not shutil.which('docker'):
        raise ValueError('Docker not installed; isolated execution cannot start')
    result = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image], capture_output=True, text=True, timeout=20)
    if result.returncode or not result.stdout.strip().startswith('sha256:'):
        raise ValueError('Docker/image unavailable; start Docker and explicitly pull ' + image)
    return result.stdout.strip()


def docker_execute(root, argv, image_id, timeout, writable=None):
    """Only project mounted; runtime state hidden; image immutable; network off."""
    if ',' in str(root):
        raise ValueError('Docker mount paths cannot contain commas')
    name = 'crewloom-' + uuid.uuid4().hex
    command = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--read-only',
               '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '128',
               '--memory', '1g', '--cpus', '2', '--ulimit', 'fsize=4194304:4194304',
               '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:rw,nosuid,size=128m',
               '--tmpfs', '/workspace/.crewloom:ro,noexec,nosuid,size=1m',
               '--mount', f'type=bind,src={root},dst=/workspace' + (',readonly' if writable is not None else ''),
               '--workdir', '/workspace', '--env', 'HOME=/tmp', '--env', 'PYTHONDONTWRITEBYTECODE=1',
               '--env', 'PYTHONUNBUFFERED=1', image_id, *argv]
    if writable is not None:
        mounts=[]
        for relative in writable:
            path=safe_path(root,relative)
            if ',' in str(path):raise ValueError('Docker mount paths cannot contain commas')
            mounts.extend(['--mount',f'type=bind,src={path},dst=/workspace/{path.relative_to(root)}'])
        index=command.index(image_id);command[index:index]=mounts
    started = time.monotonic()
    captured = bytearray()
    discarded = [False]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    def collect():
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                return
            available = max(0, 65536-len(captured))
            captured.extend(chunk[:available])
            if len(chunk) > available:
                discarded[0] = True
    reader = threading.Thread(target=collect, daemon=True); reader.start()
    try:
        try:
            code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(); code = 124; timed_out = True
    finally:
        subprocess.run(['docker', 'rm', '--force', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if process.poll() is None:
            process.kill(); process.wait()
        reader.join(timeout=5)
        process.stdout.close()
    output = captured.decode('utf-8', errors='replace')
    return {'exit_code': code, 'timed_out': timed_out, 'duration_ms': round((time.monotonic()-started)*1000),
            'output': output, 'output_truncated': discarded[0], 'image_id': image_id, 'network': 'none'}


def review_policy(root):
    """Effective manual-review policy, read from the bound project configuration."""
    import reviewer_credentials
    return reviewer_credentials.policy(root)


def review_proof(root, plan, step, outputs, reviewer=None, review_token=None):
    """One credential-verified or explicitly declared reviewer proof for a task step."""
    import reviewer_credentials
    return reviewer_credentials.authorize(root, plan['id'], step, outputs, plan.get('criteria'),
                                         label=reviewer, token=review_token)


def review_state(root, plan, step, record):
    """Whether a recorded task review still authorizes this step, artifact set, and project."""
    import reviewer_credentials
    try:
        outputs = hashes(root, step['outputs'])
    except ValueError:
        return 'stale'
    settings = review_policy(root)
    method = reviewer_credentials.CREDENTIAL_METHOD if settings['mode'] == 'verified' else reviewer_credentials.LABEL_METHOD
    return reviewer_credentials.verify_record(root, record, step, plan['id'], outputs, plan.get('criteria'), method)


def verify_completed(root, state):
    for ident, record in state['steps'].items():
        if record.get('status') != 'complete':
            continue
        for field in ('inputs', 'outputs'):
            expected = {key: value for key, value in record[field].items() if field != 'inputs' or key not in record['outputs']}
            if hashes(root, list(expected)) != expected:
                raise ValueError('Stale evidence in ' + ident + '; use a new workflow ID after reviewing changes')


def project_role(root, role):
    candidates = [root / host / 'skills' / role for host in ('.agents', '.claude')]
    installed = [folder for folder in candidates if (folder / 'SKILL.md').is_file()]
    if len(installed) != 1:
        return {'ready': False, 'error': 'Install exactly one project-local copy of the owning role'}
    folder = installed[0]
    for file in [folder / 'SKILL.md', *[folder / 'brain' / (name + '.md') for name in MEMORY]]:
        if not file.resolve().is_relative_to(root) or not file.is_file():
            return {'ready': False, 'error': 'Role memory is missing or escapes the project'}
    return {'ready': True, 'guide': str(folder / 'SKILL.md'), 'memory': str(folder / 'brain')}


def handoff(root, plan, state):
    verify_completed(root, state)
    next_step = next((s for s in plan['steps'] if state['steps'].get(s['id'], {}).get('status') != 'complete'), None)
    completed = {}
    for key, value in state['steps'].items():
        if value.get('status') != 'complete':
            continue
        step = next((item for item in plan['steps'] if item['id'] == key), None)
        review = value.get('review')
        completed[key] = {**{field: value[field] for field in ('role', 'summary', 'inputs', 'outputs', 'reviewer', 'review') if field in value},
                          'attempt_count': len(value['attempts']),
                          'image_id': value['attempts'][-1].get('image_id') if value['attempts'] else None,
                          'review_state': review_state(root, plan, step, value) if step and step.get('kind') == 'task' else None}
    return {'project_root': str(root), 'workflow': plan['id'], 'language': plan.get('language', 'en'),
            'status': state['status'], 'next_step': next_step,
            'role_setup': project_role(root, next_step['role']) if next_step else None,
            'completed': completed,
            'review_policy': review_policy(root),
            'review_limitation': 'A verified reviewer credential proves possession of a registered principal’s '
                                 'secret, not the presence of an independent human reviewer. Acceptance commands '
                                 'and lesson promotion still require recorded executor evidence.',
            'next_step_state': ({**{field: state['steps'].get(next_step['id'], {}).get(field) for field in ('status', 'error')}, 'attempt_count': len(state['steps'].get(next_step['id'], {}).get('attempts', []))} if next_step else None),
            'state_file': str(runtime(root, plan['id']) / 'state.json'),
            'blocker': state.get('error'),
            'project_context': project_context_status(root, plan['id']),
            'instruction': 'Read the selected role and project memory; retain this root and verify every supplied artifact.'}


def binding_id(root):
    """Project and checkout identity for executor evidence correlation, when this project is bound."""
    path = safe_path(root, '.crewloom/binding.json', internal=True)
    if not path.is_file():
        return None, None
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None, None
    if not isinstance(value, dict) or value.get('project_root') != str(root):
        return None, None
    return value.get('project_id'), value.get('checkout_id')


def active_workflow(root):
    path=safe_path(root,'.crewloom/active_workflow.json',internal=True)
    if not path.exists():return None
    value=json.loads(path.read_text())
    if not isinstance(value,dict) or value.get('project_root')!=str(root) or not ID.fullmatch(str(value.get('workflow',''))) or not re.fullmatch('[0-9a-f]{64}',str(value.get('plan_sha256',''))):
        raise ValueError('Invalid or cross-project active workflow reservation')
    return value


def reserve_workflow(root, plan, fingerprint):
    value=active_workflow(root)
    if value and (value['workflow']!=plan['id'] or value['plan_sha256']!=fingerprint):
        raise ValueError('Project already has an unfinished workflow: '+value['workflow']+'; finish or explicitly cancel it first')
    native=project_context_reservation(root)
    if native and native['task_id']!=plan['id']:
        raise ValueError('Project is reserved by native context task: '+native['task_id']+'; finish or cancel it first')
    path=safe_path(root,'.crewloom/active_workflow.json',internal=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name)
        json.dump({'project_root':str(root),'workflow':plan['id'],'plan_sha256':fingerprint},stream)
    os.replace(temporary,path)


def cancel(root, plan, fingerprint, reason='operator request'):
    with lock(safe_path(root,'.crewloom',internal=True)):
        folder,state=state_for(root,plan,fingerprint)
        value=active_workflow(root)
        if not (folder/'state.json').is_file():
            # Managed entry can fail after this root was reserved and before any step state
            # exists. The reservation is real: it blocks the next task, so it must be
            # explicitly cancellable instead of leaving the project permanently reserved.
            if not value or value['workflow']!=plan['id'] or value['plan_sha256']!=fingerprint:
                raise ValueError('Cannot cancel an unstarted workflow')
            state['status']='cancelled';state['started']=False
            state['cancelled_at']=time.time();state['cancel_reason']=str(reason)[:200];save(folder,state)
            safe_path(root,'.crewloom/active_workflow.json',internal=True).unlink(missing_ok=True)
            project_context_cancel(root,plan['id'],reason)
            return {'project_root':str(root),'workflow':plan['id'],'status':'cancelled','idempotent':False,
                    'started':False,'completed_steps':[],
                    'instruction':'The reservation was released before any step ran; files and history are preserved.'}
        if value and (value['workflow']!=plan['id'] or value['plan_sha256']!=fingerprint):
            raise ValueError('Cancel must name the active workflow and unchanged plan')
        if state['status']=='complete':raise ValueError('Completed workflow does not need cancellation')
        if state['status']=='cancelled':
            return {'project_root':str(root),'workflow':plan['id'],'status':'cancelled','idempotent':True,
                    'instruction':'Cancellation preserves files and failure history; use a new workflow ID for new work.'}
        state['status']='cancelled';state['cancelled_at']=time.time();state['cancel_reason']=str(reason)[:200];save(folder,state)
        safe_path(root,'.crewloom/active_workflow.json',internal=True).unlink(missing_ok=True)
        project_context_cancel(root,plan['id'],reason)
        return {'project_root':str(root),'workflow':plan['id'],'status':'cancelled','idempotent':False,
                'completed_steps':[key for key,value in state['steps'].items() if value.get('status')=='complete'],
                'instruction':'Cancellation preserves files and failure history; use a new workflow ID for new work.'}


def run(root, plan, fingerprint, image, accept=None, reviewer=None, allow_host_cli=False, review_token=None):
    """Reserve the root, execute under the shared project lock, then finalize recorded evidence."""
    from project_binding import catalog_guard
    catalog_guard(root, plan.get('project_id'))
    with project_lock(safe_path(root, '.crewloom', internal=True), reentrant=True):
        try:
            result = _execute(root, plan, fingerprint, image, accept, reviewer, allow_host_cli, review_token)
        except BaseException:
            _settle(root, plan, fingerprint, enforce=False)
            raise
        _settle(root, plan, fingerprint, enforce=True)
        result = dict(result)
        result['project_context'] = project_context_status(root, plan['id'])
        return result


def _settle(root, plan, fingerprint, enforce=False):
    """Release the reservation and record finalization while the project lock is still held."""
    _, latest = state_for(root, plan, fingerprint)
    if latest['status'] not in ('complete', 'failed', 'blocked'):
        return
    release_reservation(root, plan, fingerprint)
    problem = project_context_finish(root, plan, latest, hold_lock=True)
    if problem and enforce and lifecycle_mode(root) == 'enforced':
        raise ValueError(problem)


def release_reservation(root, plan, fingerprint):
    _, latest = state_for(root, plan, fingerprint)
    if latest['status'] in ('complete', 'failed', 'blocked'):
        safe_path(root, '.crewloom/active_workflow.json', internal=True).unlink(missing_ok=True)


def lifecycle_mode(root):
    """Managed lifecycle exists only where the project explicitly enabled it."""
    if not (root / 'crewloom.project.json').is_file():
        return None
    import project_binding as pb
    config, _ = pb.load_config(root)
    if not config:
        return None
    return config['policy']['mode'] if config['policy']['managed_lifecycle'] else None


def project_context_reservation(root):
    """Native context tasks and managed workflows serialize on the same project reservation."""
    path=safe_path(root,'.crewloom/active_task.json',internal=True)
    if not path.exists():return None
    value=json.loads(path.read_text())
    if not isinstance(value,dict) or value.get('project_root')!=str(root) or not re.fullmatch(r'[0-9a-f]{32}',str(value.get('checkout_id',''))):
        raise ValueError('Invalid or cross-project context task reservation')
    return value


def project_context_status(root, task_id):
    path = safe_path(root, '.crewloom/tasks/' + task_id + '/state.json', internal=True)
    if not path.is_file():
        return None
    import project_binding as pb
    state = pb.task_state(root, task_id)
    return {'task_id': task_id, 'status': state['status'], 'lifecycle': state['lifecycle'],
            'policy_mode': state['policy_mode'], 'evidence_only': state.get('evidence_only'),
            'context': state.get('context'), 'verified': state.get('verified'),
            'metrics': state.get('metrics', {}),
            'host_callbacks_verified': False}


def project_context_enter(root, plan, state):
    import project_binding as pb
    step = next((item for item in plan['steps'] if state['steps'].get(item['id'], {}).get('status') != 'complete'),
                plan['steps'][-1])
    return pb.enter(root, None, plan['id'], step['role'], seeds=step['inputs'], sources=step['inputs'],
                    language=plan.get('language', 'en'), criteria_path=plan.get('criteria'), hold_lock=False)


def project_context_checkpoint(root, plan, state, step):
    """Rebuild the frozen generation before a step instead of executing on obsolete evidence.

    The rebuild is also required when a step declares different sources or a different role
    than the stored generation, so per-step inputs refresh even when no earlier byte changed.
    """
    import project_context as pc
    path = pc.context_path(root, plan['id'])
    if path.is_file():
        stored = json.loads(path.read_text(encoding='utf-8'))
        changed = pc.changed_files(root, stored)
        declared = sorted(item['path'] for item in stored.get('bodies', []))
        scope = stored.get('scope') or {}
        drifted = (scope.get('role') != step['role']
                   or declared != sorted(step['inputs'])
                   or (stored.get('criteria_file') or {}).get('path') != plan.get('criteria'))
        if not changed and not drifted:
            return {'stale': False, 'generation': stored.get('generation')}
        if changed:
            pc.invalidate(root, plan['id'], 'sources changed before step ' + step['id'])
    project_context_enter(root, plan, state)
    return {'stale': True, 'rebuilt': True}


def project_context_publish_gate(root, plan, step):
    """Enforced mode refuses to publish model artifacts against a stale snapshot."""
    if lifecycle_mode(root) != 'enforced':
        return None
    import project_context as pc
    import project_binding as pb
    binding = pb.load_binding(root)
    return pc.require_fresh(root, binding, plan['id'])


def project_context_finish(root, plan, state, hold_lock=True):
    import project_binding as pb
    try:
        binding = pb.load_binding(root, required=False)
        if binding is None:
            return None
        definitions = {step['id']: step for step in plan['steps']}
        changed = sorted({name for record in state['steps'].values() for name in record.get('outputs', {})})
        evidence = []
        for name, record in state['steps'].items():
            step = definitions[name]
            if step.get('kind', 'command') != 'command' or record.get('reviewer'):
                continue
            if record.get('status') not in ('complete', 'failed'):
                continue
            if not record.get('attempts'):
                continue
            evidence.append({'workflow': plan['id'], 'step': name,
                             'scope': 'acceptance command step ' + name})
        pb.finish(root, binding['project_id'], plan['id'], changed, [], role=plan['steps'][-1]['role'],
                  evidence=evidence, hold_lock=hold_lock)
        return None
    except (ValueError, OSError) as exc:
        return 'Project context finalization failed: ' + str(exc)


def project_context_cancel(root, task_id, reason):
    import project_binding as pb
    try:
        binding = pb.load_binding(root, required=False)
        if binding is None:
            return None
        pb.cancel(root, binding['project_id'], task_id, reason, hold_lock=False)
    except (ValueError, OSError):
        return None
    return None


def _execute(root, plan, fingerprint, image, accept=None, reviewer=None, allow_host_cli=False, review_token=None):
    with project_lock(safe_path(root, '.crewloom', internal=True), reentrant=True):
        # An interrupted grouped publication is reconciled before this run reads any workflow
        # state, builds a frozen context, evaluates a publish gate or records acceptance, so a
        # half-published group is never the baseline any of them observe. A destination that no
        # longer matches its journal is refused here, before this run reserves the root.
        from execution_policy import recover as recover_publications
        recover_publications(root)
        folder, state = state_for(root, plan, fingerprint)
        if state['status'] == 'cancelled':
            raise ValueError('Cancelled workflow cannot resume; use a new workflow ID')
        reserve_workflow(root, plan, fingerprint)
        verify_completed(root, state)
        if accept:
            next_step = next((s for s in plan['steps'] if state['steps'].get(s['id'], {}).get('status') != 'complete'), None)
            if not next_step or next_step['id'] != accept or next_step.get('kind') != 'task':
                raise ValueError('Accept must name the next outstanding task')
        ledger_file = safe_path(root, '.crewloom/attempts.json', internal=True)
        ledger = json.loads(ledger_file.read_text()) if ledger_file.exists() else {'attempts': []}
        if not isinstance(ledger, dict) or not isinstance(ledger.get('attempts'), list) or any(not isinstance(item, dict) or item.get('status') not in ('running', 'failed', 'succeeded') or not isinstance(item.get('signature'), str) for item in ledger['attempts']):
            raise ValueError('Malformed project attempt ledger')
        image_id = None
        lifecycle = project_context_enter(root, plan, state) if lifecycle_mode(root) else None
        if lifecycle: state = state_for(root, plan, fingerprint)[1]
        for step in plan['steps']:
            record = state['steps'].setdefault(step['id'], {'status': 'pending', 'role': step['role'], 'summary': step['summary'], 'kind': step.get('kind', 'command'), 'argv': list(step.get('argv') or []), 'attempts': []})
            if record['status'] == 'complete':
                if step.get('kind')=='model':
                    from model_host import bound_context, build_prompt, pc_path_exists
                    # Reuse verifies the prompt against the exact archived generation this step
                    # consumed, never against whichever context happens to be current now. A
                    # project with no project context at all still verifies the prompt hash.
                    consumed=(bound_context(root,plan['id'],record)
                              if 'context_generation' in record or pc_path_exists(root,plan['id']) else None)
                    current=digest(build_prompt(root,step,plan.get('language','en'),plan['id'],consumed).encode())
                    if record.get('context_sha256')!=current:
                        raise ValueError('Model context changed or old evidence lacks context hash; review and use a new workflow ID')
                if step.get('kind') == 'task' and review_policy(root)['mode'] == 'verified':
                    # Verified mode fails closed: a recorded review that was edited, replays
                    # another project or task, or no longer covers these bytes cannot be reused.
                    recorded = review_state(root, plan, step, record)
                    if recorded != 'valid':
                        raise ValueError('Recorded reviewer proof for ' + step['id'] + ' is ' + recorded
                                         + '; start a new workflow ID rather than reusing this state')
                continue
            if lifecycle_mode(root): project_context_checkpoint(root, plan, state, step)
            try:
                inputs = hashes(root, step['inputs'])
            except ValueError as exc:
                state['status'] = 'blocked'; state['error'] = str(exc); save(folder, state)
                return handoff(root, plan, state)
            state.pop('error', None)
            if step.get('kind') == 'task':
                if accept != step['id']:
                    state['status'] = 'awaiting_task'; save(folder, state); return handoff(root, plan, state)
                # Authorize before any state is written: a refused reviewer records nothing.
                outputs = hashes(root, step['outputs'])
                review = review_proof(root, plan, step, outputs, reviewer, review_token)
                record.update(status='complete', inputs=inputs, outputs=outputs,
                              reviewer=review['principal'], review=review)
                state['status'] = 'complete' if step is plan['steps'][-1] else 'pending'
                save(folder, state)
                return handoff(root, plan, state)
            if accept:
                raise ValueError('Accept only the next task step; commands must run to produce evidence')
            if step.get('kind') == 'model':
                run_model_step(root, plan, step, inputs, record, state, folder, ledger, allow_host_cli)
                if record['status'] != 'complete':
                    return handoff(root, plan, state)
                continue
            try:
                image_id = image_id or inspect_image(image)
            except ValueError as exc:
                state['status'] = 'blocked'; state['error'] = str(exc); save(folder, state)
                raise
            signature = digest(json.dumps({'inputs': inputs, 'argv': step['argv'], 'outputs': step['outputs'], 'image_id': image_id, 'broker_sha256': digest(resources.module_file('execution_policy.py').read_bytes())}, sort_keys=True).encode())
            if sum(a['signature'] == signature and a['status'] != 'succeeded' for a in ledger['attempts']) >= 2:
                state['status'] = 'blocked'; save(folder, state)
                raise ValueError('Two attempts exhausted for unchanged command and inputs')
            before = {rel: (safe_path(root, rel).stat().st_mtime_ns, safe_path(root, rel).stat().st_ino) for rel in step['outputs'] if safe_path(root, rel).is_file()}
            attempt = {'signature': signature, 'status': 'running', 'started_at': time.time()}
            record['attempts'].append(attempt)
            project_attempt = {'signature': signature, 'status': 'running', 'workflow': plan['id'], 'step': step['id']}
            ledger['attempts'].append(project_attempt)
            save_ledger(root, ledger)
            record['status'] = 'running'; state['status'] = 'running'; save(folder, state)
            from execution_policy import execute as isolated_execute
            try:
                result = isolated_execute(root, step, image_id, step.get('timeout_seconds', 60))
            except (ValueError, OSError) as exc:
                result = {'exit_code': 2, 'output': str(exc), 'boundary': 'artifact broker rejected execution'}
            attempt.update(result); attempt['status'] = 'finished'
            record['inputs'] = inputs
            try:
                if result['exit_code']:
                    raise ValueError('Command failed: ' + step['id'])
                record['outputs'] = hashes(root, step['outputs'])
                for rel, previous in before.items():
                    stat = safe_path(root, rel).stat()
                    if previous == (stat.st_mtime_ns, stat.st_ino):
                        raise ValueError('Unchanged pre-existing output is not fresh execution evidence: ' + rel)
            except ValueError as exc:
                project_attempt['status'] = 'failed'; save_ledger(root, ledger)
                # The run carries the same cause as the step it stopped on, so every reader of
                # this finished run learns which acceptance failed and why, instead of finding a
                # `failed` status with no recorded cause next to it.
                record['status'] = 'failed'; state['status'] = 'failed'
                record['error'] = str(exc); state['error'] = str(exc)
                save(folder, state); return handoff(root, plan, state)
            project_attempt['status'] = 'succeeded'; save_ledger(root, ledger)
            record['status'] = 'complete'; record.pop('error', None); save(folder, state)
        state['status'] = 'complete'; save(folder, state)
        return handoff(root, plan, state)


def run_model_step(root, plan, step, inputs, record, state, folder, ledger, allow_host_cli):
    import model_host as host_module
    from model_host import build_prompt, generate
    try:
        # Every installed-CLI host, not a hardcoded pair, needs the explicit operator opt-in.
        # The list is owned by the adapter, so a host added there is guarded here too instead of
        # becoming a CLI-execution path the gate does not know about.
        if step['host'] in host_module.CLI_HOSTS and not allow_host_cli:
            raise ValueError('Host CLI execution is disabled in enforced mode; use openai/anthropic or explicit operator --allow-host-cli')
        from provider_gateway import MAX_PROJECT_MODEL_REQUESTS
        if sum(a.get('kind')=='model' for a in ledger['attempts']) >= MAX_PROJECT_MODEL_REQUESTS:
            raise ValueError('Project model request budget exhausted')
        project_context_publish_gate(root, plan, step)
        consumed=host_module.consumed_context(root,plan['id'],step)
        prompt=build_prompt(root,step,plan.get('language','en'),plan['id'],consumed)
        record['context_sha256']=digest(prompt.encode())
        record['context_bytes']=len(prompt.encode())
        if consumed:
            # Bind this step to the generation it actually read; a later reuse resolves the
            # same immutable evidence instead of inferring it from matching declared sources.
            record['context_generation']=consumed['generation']
            record['context_semantic_sha256']=consumed['semantic_sha256']
        else:
            record.pop('context_generation',None)
            record.pop('context_semantic_sha256',None)
        record['memory_mode']=step.get('memory_mode','focused')
        signature=digest(json.dumps({'prompt':prompt,'host':step['host'],'model':step.get('model'),
                                    'timeout':step.get('timeout_seconds',180),
                                    'adapter_sha256':digest(Path(host_module.__file__).read_bytes()),
                                    'gateway_sha256':digest(resources.module_file('provider_gateway.py').read_bytes()),
                                    'broker_sha256':digest(resources.module_file('execution_policy.py').read_bytes())},sort_keys=True).encode())
        if sum(a['signature']==signature and a['status']!='succeeded' for a in ledger['attempts'])>=2:
            raise ValueError('Two attempts exhausted for unchanged model task and inputs')
        attempt={'signature':signature,'status':'running','started_at':time.time()}
        record['attempts'].append(attempt)
        entry={'signature':signature,'status':'running','workflow':plan['id'],'step':step['id'],'kind':'model'}
        ledger['attempts'].append(entry);save_ledger(root,ledger)
        record['status']='running';state['status']='running';save(folder,state)
        artifacts,evidence=generate(step['host'],prompt,step['outputs'],step.get('timeout_seconds',180),step.get('model'))
        if hashes(root,step['inputs']) != inputs:
            raise ValueError('Inputs changed during model generation; outputs rejected')
        project_context_publish_gate(root, plan, step)
        from execution_policy import publish
        publish(root,{path:text.encode() for path,text in artifacts.items()},inputs)
        attempt.update(evidence,status='finished',exit_code=0)
        entry['status']='succeeded';save_ledger(root,ledger)
        record.update(status='complete',inputs=inputs,outputs=hashes(root,step['outputs']))
        record['context_bytes']=len(prompt.encode())
        usage=evidence.get('usage') or {}
        if isinstance(usage,dict):
            record['provider_usage']={key:usage[key] for key in ('input_tokens','cached_input_tokens','output_tokens','total_tokens') if isinstance(usage.get(key),int)}
            record['provider_usage_available']=bool(record['provider_usage'])
        record.pop('error',None);save(folder,state)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        if 'entry' in locals():
            entry['status']='failed';save_ledger(root,ledger)
            attempt.update(status='finished',exit_code=2)
        record['status']='failed';record['error']=str(exc)
        state['status']='failed';state['error']=str(exc);save(folder,state)


def doctor(image, root=None, host=None, model_host=None):
    checks = {'python': os.sys.version.split()[0], 'git': bool(shutil.which('git')), 'docker': bool(shutil.which('docker'))}
    try:
        checks['image_id'] = inspect_image(image); checks['isolated_execution_ready'] = True
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        checks['isolated_execution_ready'] = False; checks['error'] = str(exc)
    if model_host:
        from model_host import probe
        from provider_gateway import PROVIDERS
        try:
            checks['model_host'] = ({'provider':model_host,'generation_supported':True,'credentials_configured':bool(os.environ.get(PROVIDERS[model_host][1])),'authentication_verified':False} if model_host in PROVIDERS else probe(model_host))
        except (ValueError, OSError, subprocess.SubprocessError) as exc: checks['model_host'] = {'generation_supported': False, 'error': str(exc)}
    if root and host:
        directory = root / ('.agents' if host == 'agents' else '.claude') / 'skills'
        checks['host_layout'] = host
        checks['installed_roles'] = [p.parent.name for p in directory.glob('*/SKILL.md')]
        checks['host_model_execution_verified'] = False
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('run', 'status', 'handoff', 'accept', 'cancel', 'doctor'))
    parser.add_argument('--project', help='Explicit canonical project root; required for task actions')
    parser.add_argument('--plan', default='workflow.json')
    parser.add_argument('--image', default=DEFAULT_IMAGE)
    parser.add_argument('--host', choices=('agents', 'claude'))
    parser.add_argument('--step'); parser.add_argument('--reviewer'); parser.add_argument('--reason')
    parser.add_argument('--reviewer-token-stdin', action='store_true',
                        help='Read the reviewer credential from standard input; it is never a command argument')
    parser.add_argument('--allow-host-cli', action='store_true', help='Operator opt-in to legacy CLI hosts outside the enforced boundary')
    # The doctor offers exactly the hosts the adapter names, so a host added there is checkable
    # here instead of hidden. This only probes an installed CLI; generation stays gated above.
    from model_host import HOSTS as MODEL_HOST_CHOICES
    parser.add_argument('--model-host', choices=MODEL_HOST_CHOICES)
    args = parser.parse_args(argv)
    if args.action != 'doctor' and not args.project:
        parser.error('Task actions require --project; the current directory is not project identity')
    try:
        if args.action == 'doctor':
            result = doctor(args.image, Path(args.project or '.').resolve(), args.host, args.model_host)
        else:
            root = Path(args.project).resolve(strict=True)
            if not root.is_dir(): raise ValueError('Project must be a directory')
            plan, fingerprint = read_plan(root, args.plan)
            if args.action in ('status', 'handoff'):
                _, state = state_for(root, plan, fingerprint); result = handoff(root, plan, state)
            elif args.action == 'cancel':
                result = cancel(root, plan, fingerprint, args.reason or 'operator request')
            else:
                if args.action == 'accept' and not args.step: raise ValueError('Accept needs --step')
                import reviewer_credentials
                token = reviewer_credentials.credential_from_environment(sys.stdin if args.reviewer_token_stdin else None)
                result = run(root, plan, fingerprint, args.image, args.step if args.action == 'accept' else None,
                             args.reviewer, args.allow_host_cli, token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if args.action in ('status', 'handoff', 'accept', 'cancel') or result.get('status') == 'complete' or result.get('isolated_execution_ready') else 2
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
