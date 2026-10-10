"""Concurrent task coordination: a real DAG of Git worktrees, verified executors, reviewed integration.

The coordinator is an owner of one explicit project root, not a parallel runtime. Every task runs
the existing managed executor, `workflow.run`, inside its own Git worktree, so the isolation
boundary, the declared-artifact broker, the failure ledger and the Docker image policy are exactly
the ones an ordinary workflow already uses. The coordinator adds what a single workflow cannot do:
concurrent independent tasks, dependency integration, an explicit review decision, and a root
fast-forward that changes the checked-out tree only after that decision is revalidated.

Boundaries this module does not cross and does not claim:

- It is not a scheduler, a task queue, or a provider client. No provider call is made here: a
  `model` step runs only inside the existing managed executor `workflow.run`, inside its own Git
  worktree, under that module's own host policy, request budget and artifact broker. A manual
  `task` step never runs in a batch; a per-task human review stays a `workflow accept` decision
  with its own reviewer credential.
- A generated artifact is never committed on the strength of the generation alone. A workflow that
  declares a `model` step must also declare a later real command step that reads every generated
  artifact as a declared input, and the task commit needs the succeeded executor evidence of both.
  An unconsumed or unchecked artifact stays in the worktree, uncommitted.
- An installed CLI host is the operator's explicit exception, required twice: `native_host_cli`
  true on the batch task (auditable in the committed manifest) and `--allow-host-cli` on the run
  that executes it. Either one alone is refused before any provider call.
- Reclaiming a controller lock does not stop a container or command that outlived its process, and
  a declared-label review decision names a reviewer without authenticating one.
- Publishing moves the root by one recorded fast-forward of a reviewed candidate commit. It is not
  an arbitrary checkout, a reset, or a history rewrite, and it never pushes, merges on GitHub, or
  deletes the worktrees the evidence is bound to.
"""
import argparse
import concurrent.futures
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import execution_policy
import project_binding as pb
import repo_map
import reviewer_credentials
import workflow as w

DEFAULT_IMAGE = w.DEFAULT_IMAGE
DEFAULT_WORKERS = 2
MAX_WORKERS = 4
MAX_TASKS = 32
SCHEMA_VERSION = 1

COORDINATOR_DIRECTORY = '.crewloom/coordinators'
WORKTREE_DIRECTORY = '.crewloom/worktrees'
COORDINATOR_RESERVATION = '.crewloom/active_coordinator.json'
INTEGRATION_TASK = 'integration'

PLAN_KEYS = frozenset({'schema_version', 'id', 'language', 'project_id', 'base', 'workers',
                       'tasks', 'integration'})
TASK_KEYS = frozenset({'id', 'workflow', 'depends_on', 'native_host_cli', 'priority'})
INTEGRATION_KEYS = frozenset({'workflow', 'native_host_cli'})
CONTROL_FILES = frozenset(['.gitignore', 'crewloom.project.json', *pb.INSTRUCTION_FILES])
CONTROL_KEYS = frozenset(w.folded(name) for name in CONTROL_FILES)

BATCH_STATUSES = ('planned', 'running', 'verified', 'failed', 'blocked', 'cancelled',
                  'integrating', 'conflict', 'review_ready', 'reviewed', 'published')
TASK_STATUSES = ('pending', 'running', 'verified', 'failed', 'blocked', 'cancelled')
INTEGRATABLE = ('verified', 'conflict', 'review_ready', 'reviewed', 'failed')

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_STATE_BYTES = 512 * 1024
MAX_EVENT_BYTES = 256 * 1024
MAX_EVENT_LINE = 4096
MAX_EVENTS = 512
MAX_DIFF_BYTES = 64 * 1024 * 1024
MAX_CONSUMED = 64

REF = re.compile(r'[A-Za-z0-9][A-Za-z0-9._/+@\-]{0,199}$')
SHA = re.compile(r'[0-9a-f]{64}$')
GIT_OBJECT = re.compile(r'[0-9a-f]{40,64}$')
DEFAULT_CHECKS = ('structure', 'git', 'clean', 'ownership')

_STATE_LOCK = threading.Lock()
try:
    import fcntl
except ImportError:  # pragma: no cover - reported honestly instead of guessed around
    fcntl = None


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(value):
    return w.digest(value)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


class CoordinatorError(ValueError):
    """One refusal reason for a coordinator action; every caller reports it verbatim."""


# ---------------------------------------------------------------------------------
# Git access. Every child inherits no Git repository, index or configuration override
# and is given an explicit working directory, so a hook environment cannot redirect a
# worktree to another repository.
# ---------------------------------------------------------------------------------

def git_environment():
    """The shared cleared Git environment plus `GIT_OPTIONAL_LOCKS=0`.

    Read-only coordinator actions must be read-only on disk too. Without this, Git refreshes the
    index opportunistically to cache stat data, which rewrites `.git/index` during a command that
    is only supposed to inspect the repository. The inherited Git overrides are still dropped by
    the shared helper, so a hook environment cannot redirect a worktree.
    """
    return {**repo_map.git_environment(), 'GIT_OPTIONAL_LOCKS': '0'}


def git(root, argv, timeout=180, check=True):
    result = subprocess.run(['git', *[str(item) for item in argv]], cwd=str(root),
                            env=git_environment(), capture_output=True, timeout=timeout)
    if check and result.returncode:
        detail = result.stderr.decode('utf-8', 'replace').strip().replace('\n', ' ')[:400]
        raise CoordinatorError('git ' + ' '.join(str(item) for item in argv) + ' failed in '
                               + str(root) + ': ' + (detail or 'exit ' + str(result.returncode)))
    return result


def git_text(root, argv, timeout=60):
    return git(root, argv, timeout).stdout.decode('utf-8', 'replace').strip()


# ---------------------------------------------------------------------------------
# Bounded owner-only runtime records
# ---------------------------------------------------------------------------------

def _private_folder(path):
    if path.is_symlink():
        raise CoordinatorError('Coordinator runtime path may not be a symlink: ' + str(path))
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise CoordinatorError('Coordinator runtime path became a symlink: ' + str(path))
    try:
        os.chmod(str(path), 0o700)
    except OSError as exc:
        raise CoordinatorError('Coordinator runtime directory must be owner-only: ' + str(exc))
    return path


def _write_private(path, data, limit):
    """Atomically replace one bounded owner-only record, refusing links and oversized bodies."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    if len(data) > limit:
        raise CoordinatorError('Bounded coordinator record exceeded its limit: ' + path.name)
    if path.is_symlink():
        raise CoordinatorError('Coordinator record may not be a symlink: ' + str(path))
    if path.exists() and (path.is_dir() or path.stat().st_nlink != 1):
        raise CoordinatorError('Coordinator record must be one regular unlinked file: ' + str(path))
    folder = _private_folder(path.parent)
    descriptor, name = tempfile.mkstemp(dir=str(folder), prefix=path.name + '.', suffix='.tmp')
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        os.replace(name, str(path))
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return len(data)


def _read_record(path, limit, label):
    """Read one bounded record; an oversized or link-shaped file is refused, never truncated."""
    if path.is_symlink():
        raise CoordinatorError(label + ' may not be a symlink: ' + str(path))
    if not path.is_file():
        return None
    if path.stat().st_nlink != 1:
        raise CoordinatorError(label + ' must be a single-link regular file: ' + str(path))
    if path.stat().st_size > limit:
        raise CoordinatorError(label + ' exceeds its bounded size: ' + str(path))
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise CoordinatorError(label + ' is unreadable: ' + str(exc))


class _Log:
    """Append-only bounded event log. It stops appending rather than growing without limit."""

    def __init__(self, folder):
        self.path = folder / 'events.jsonl'
        self.lock = threading.Lock()
        self.count = 0
        self.truncated = False

    def __call__(self, event, **fields):
        line = canonical({'at': now(), 'event': event, **fields})
        if len(line) > MAX_EVENT_LINE:
            line = line[:MAX_EVENT_LINE - 3] + '...'
        with self.lock:
            if self.truncated or self.count >= MAX_EVENTS:
                self.truncated = True
                return
            try:
                size = self.path.stat().st_size if self.path.exists() else 0
            except OSError:
                size = 0
            if size + len(line) + 1 > MAX_EVENT_BYTES:
                self.truncated = True
                return
            try:
                descriptor = os.open(str(self.path), os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
            except OSError:
                self.truncated = True
                return
            with os.fdopen(descriptor, 'a', encoding='utf-8') as stream:
                stream.write(line + '\n')
            self.count += 1


# ---------------------------------------------------------------------------------
# Ownership. A batch is owned by a kernel-held advisory lock, so a second controller is
# refused and an interrupted controller is provably gone without ever guessing whether a
# recorded PID is alive, dead, or a recycled identity.
# ---------------------------------------------------------------------------------

@contextlib.contextmanager
def _advisory_lock(path, label):
    if fcntl is None:
        raise CoordinatorError('Batch ownership needs POSIX advisory locking, which this platform '
                               'does not provide; the coordinator refuses rather than guess')
    _private_folder(path.parent)
    if path.is_symlink():
        raise CoordinatorError(label + ' lock may not be a symlink: ' + str(path))
    descriptor = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise CoordinatorError(label + ' is owned by another live controller process; batch '
                                   'ownership is never taken over from a recorded PID')
        try:
            os.ftruncate(descriptor, 0)
            os.write(descriptor, canonical({'pid': os.getpid(), 'thread': threading.get_ident(),
                                            'acquired_at': now()}).encode('utf-8'))
        except OSError:
            pass
        yield
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def _controller_lock(folder, batch):
    with _advisory_lock(folder / 'controller.lock', 'Batch ' + batch):
        yield


@contextlib.contextmanager
def _worktree_lock(folder, ident):
    with _advisory_lock(folder / 'locks' / (ident + '.lock'), 'Task ' + ident):
        yield


def _controller_is_live(folder):
    if fcntl is None or not (folder / 'controller.lock').exists():
        return False
    descriptor = os.open(str(folder / 'controller.lock'), os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(descriptor)


# ---------------------------------------------------------------------------------
# Root helpers
# ---------------------------------------------------------------------------------

def _root(value):
    try:
        return Path(value).resolve(strict=True)
    except OSError as exc:
        raise CoordinatorError('Explicit existing project root required: ' + str(exc))


def _internal(root, relative):
    return w.safe_path(root, relative, internal=True)


def _coordinator_folder(root, batch):
    return _internal(root, COORDINATOR_DIRECTORY + '/' + batch)


def _worktree_path(root, batch, ident):
    path = _internal(root, WORKTREE_DIRECTORY + '/' + batch + '/' + ident)
    if path.is_symlink():
        raise CoordinatorError('Managed worktree path may not be a symlink: ' + str(path))
    if path.exists() and not path.is_dir():
        raise CoordinatorError('Managed worktree path exists and is not a directory: ' + str(path))
    return path


def _branch(batch, ident):
    return 'crewloom/' + batch + '/' + ident


def _unlink(path):
    try:
        if path.is_symlink():
            raise CoordinatorError('Coordinator control record may not be a symlink: ' + str(path))
        path.unlink()
    except FileNotFoundError:
        pass


def _root_lock(root):
    return w.project_lock(_internal(root, '.crewloom'), reentrant=True)


def _tracked_status(root):
    """Tracked changes staged or present in the work tree, read without rewriting the index.

    `git diff` opportunistically refreshes `.git/index` to cache stat data, which would make a
    read-only preflight write to the repository. `git status` does the same comparison under
    `GIT_OPTIONAL_LOCKS=0` without that side effect.
    """
    listed = git(root, ['status', '--porcelain=v1', '-z', '--untracked-files=no'], check=False)
    return sorted(set(filter(None, listed.stdout.decode('utf-8', 'replace').split('\0'))))


def _root_untracked(root):
    listed = git(root, ['ls-files', '-z', '--others', '--exclude-standard'], check=False)
    return sorted(set(filter(None, listed.stdout.decode('utf-8', 'replace').split('\0'))))


def _candidate_paths(root, base, candidate):
    listed = git(root, ['diff', '--name-only', '-z', base + '..' + candidate], check=False)
    return sorted(set(filter(None, listed.stdout.decode('utf-8', 'replace').split('\0'))))


def _diff_digest(root, base, candidate):
    result = git(root, ['diff', '--no-color', '--no-ext-diff', '--full-index', '--binary',
                        base + '..' + candidate], check=False)
    if result.returncode:
        raise CoordinatorError('Candidate diff could not be produced: '
                               + result.stderr.decode('utf-8', 'replace').strip()[:300])
    if len(result.stdout) > MAX_DIFF_BYTES:
        raise CoordinatorError('Candidate diff exceeds the bounded review size')
    return digest(result.stdout)


# ---------------------------------------------------------------------------------
# Manifest contract
# ---------------------------------------------------------------------------------

def topological(tasks):
    """Deterministic dependency-first order; ties break by task id, never by discovery order."""
    by_id = {task['id']: task for task in tasks}
    remaining = {ident: {item for item in by_id[ident].get('depends_on', [])} for ident in by_id}
    for ident in by_id:
        for dependency in remaining[ident]:
            if dependency not in by_id:
                raise CoordinatorError('Missing dependency ' + str(dependency) + ' for task ' + ident)
    order = []
    while remaining:
        ready = sorted(ident for ident in remaining if not remaining[ident] - set(order))
        if not ready:
            raise CoordinatorError('Task dependency graph contains a cycle: '
                                   + ', '.join(sorted(remaining)))
        for ident in ready:
            order.append(ident)
            del remaining[ident]
    return order


def _declared_outputs(plan):
    outputs = []
    for step in plan['steps']:
        for relative in step['outputs']:
            if relative not in outputs:
                outputs.append(relative)
    return outputs


def _declared_inputs(plan):
    inputs = []
    for step in plan['steps']:
        for relative in step['inputs']:
            if relative not in inputs:
                inputs.append(relative)
    return inputs


def _native_hosts():
    """Every host reached through an installed CLI, named by the adapter rather than restated here."""
    from model_host import CLI_HOSTS
    return frozenset(CLI_HOSTS)


def _step_positions(plan):
    return {step['id']: index for index, step in enumerate(plan['steps'])}


def _command_consumers(plan, step):
    """Later command steps that declare one of this step's outputs as an input, by canonical path."""
    positions = _step_positions(plan)
    wanted = {w.path_key(item) for item in step['outputs']}
    return [other for other in plan['steps']
            if other.get('kind', 'command') == 'command'
            and positions[other['id']] > positions[step['id']]
            and wanted & {w.path_key(item) for item in other['inputs']}]


def _check_workflow(root, relative, native_host_cli=False):
    """One managed workflow a coordinator task may run.

    Command steps are the acceptance. A `model` step is allowed only where a real command step in
    the same workflow reads every generated artifact as a declared input, so generated code is
    verified by running it before any of it becomes a task commit. A manual `task` step, and a
    native CLI host without the task's explicit operator opt-in, are refused here — before a
    worktree, a provider call or an artifact exists.
    """
    if not isinstance(relative, str) or not relative.strip():
        raise CoordinatorError('Each task and the integration need an explicit workflow path')
    path = w.safe_path(root, relative)
    if path.is_symlink() or not path.is_file():
        raise CoordinatorError('Workflow plan is missing or redirected: ' + str(relative))
    plan, fingerprint = w.read_plan(root, relative)
    commands = [step for step in plan['steps'] if step.get('kind', 'command') == 'command']
    models = [step for step in plan['steps'] if step.get('kind') == 'model']
    for step in plan['steps']:
        if step.get('kind', 'command') == 'task':
            raise CoordinatorError('Coordinator batches execute no manual task step: ' + relative
                                   + ' step ' + step['id'] + ' waits for a human review decision '
                                   'this coordinator does not grant; run workflow accept outside '
                                   'the batch')
    for step in models:
        if step['host'] in _native_hosts() and not native_host_cli:
            raise CoordinatorError('The native CLI host ' + step['host'] + ' needs an explicit operator '
                                   'opt-in: declare native_host_cli true for this task in the '
                                   'manifest and pass --allow-host-cli to the run that executes it')
    if models and not commands:
        raise CoordinatorError('A model step needs a real command acceptance in the same workflow; '
                               + relative + ' declares no command step that could verify generated code')
    for step in models:
        consumers = _command_consumers(plan, step)
        unconsumed = [output for output in step['outputs']
                      if not any(any(w.path_key(item) == w.path_key(output)
                                     for item in other['inputs']) for other in consumers)]
        if unconsumed:
            raise CoordinatorError('Every generated artifact must be read by a later real command '
                                   'acceptance in the same workflow; ' + relative + ' step '
                                   + step['id'] + ' generates what nothing consumes: '
                                   + ', '.join(unconsumed))
    outputs = _declared_outputs(plan)
    if not outputs:
        raise CoordinatorError('A coordinator workflow must declare at least one output: ' + relative)
    for item in outputs + _declared_inputs(plan):
        if w.folded(Path(item).name) in CONTROL_KEYS:
            raise CoordinatorError('Coordinator tasks may not own project control files: ' + str(item))
    return {'plan': plan, 'plan_sha256': fingerprint, 'workflow_id': plan['id'],
            'criteria': plan.get('criteria'), 'outputs': outputs, 'inputs': _declared_inputs(plan),
            'model_steps': [step['id'] for step in models],
            'command_steps': [step['id'] for step in commands],
            'native_hosts': sorted({step['host'] for step in models if step['host'] in _native_hosts()}),
            'native_host_cli': bool(native_host_cli)}


def _resolve_base(root, base):
    """One explicit base commit. An option-like or unknown ref is refused, never guessed."""
    if not isinstance(base, str) or not base or base != base.strip():
        raise CoordinatorError('Base ref must be an explicit single-line string')
    if base.startswith('-'):
        raise CoordinatorError('Option-like base ref is refused: ' + base)
    if not REF.fullmatch(base) or '..' in base or '//' in base or base.endswith(('/', '.lock')):
        raise CoordinatorError('Base ref has unsupported characters: ' + base)
    resolved = git(root, ['rev-parse', '--verify', '--quiet', base + '^{commit}'], check=False)
    commit = resolved.stdout.decode('utf-8', 'replace').strip()
    if resolved.returncode or not GIT_OBJECT.fullmatch(commit):
        raise CoordinatorError('Unknown base ref in this repository: ' + base)
    if git(root, ['cat-file', '-t', commit], check=False).stdout.decode().strip() != 'commit':
        raise CoordinatorError('Base ref does not name a commit: ' + base)
    return commit


def _read_manifest(root, manifest):
    if not isinstance(manifest, str) or not manifest:
        raise CoordinatorError('Explicit relative manifest path required')
    source = w.safe_path(root, manifest)
    walk = root
    for part in Path(manifest).parts:
        walk = walk / part
        if walk.is_symlink():
            raise CoordinatorError('Manifest path may not use symlinks: ' + manifest)
    if not source.is_file():
        raise CoordinatorError('Coordinator manifest is missing: ' + manifest)
    if source.stat().st_nlink != 1:
        raise CoordinatorError('Manifest must be a single-link regular file: ' + manifest)
    if source.stat().st_size > MAX_MANIFEST_BYTES:
        raise CoordinatorError('Manifest exceeds its bounded size: ' + manifest)
    body = source.read_bytes()
    try:
        plan = json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CoordinatorError('Manifest is not readable JSON: ' + str(exc))
    if not isinstance(plan, dict):
        raise CoordinatorError('Manifest must be a JSON object')
    return source, digest(body), plan


def _check_structure(plan, root, project_id):
    """Validate the whole manifest shape, identity and DAG. Nothing here writes anything."""
    if plan.get('schema_version') != SCHEMA_VERSION:
        raise CoordinatorError('Manifest requires schema_version ' + str(SCHEMA_VERSION))
    if not w.ID.fullmatch(str(plan.get('id', ''))):
        raise CoordinatorError('Manifest needs a stable kebab-case batch id')
    if plan.get('language', 'en') not in ('en', 'ar'):
        raise CoordinatorError('Manifest language must be en or ar')
    unknown = set(plan) - PLAN_KEYS
    if unknown:
        raise CoordinatorError('Unknown manifest fields: ' + ', '.join(sorted(unknown)))
    if not isinstance(plan.get('base'), str) or not plan['base']:
        raise CoordinatorError('Manifest needs an explicit base ref')
    workers = plan.get('workers', DEFAULT_WORKERS)
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise CoordinatorError('Manifest workers must be an integer from 1 to ' + str(MAX_WORKERS))
    binding = pb.load_binding(root)
    if not isinstance(project_id, str) or binding['project_id'] != str(plan.get('project_id', '')) \
            or binding['project_id'] != project_id:
        raise CoordinatorError('Explicit project identity does not match the bound project '
                               + binding['project_id'] + '; a coordinator never infers a project '
                               'from a previous client or the working directory')
    tasks = plan.get('tasks')
    if not isinstance(tasks, list) or not tasks:
        raise CoordinatorError('Manifest needs a nonempty tasks array')
    if len(tasks) > MAX_TASKS:
        raise CoordinatorError('Manifest exceeds the bounded task count of ' + str(MAX_TASKS))
    seen = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise CoordinatorError('Each task must be an object')
        unknown = set(task) - TASK_KEYS
        if unknown:
            raise CoordinatorError('Unknown task fields: ' + ', '.join(sorted(unknown)))
        if type(task.get('priority', 0)) is not int or not -100 <= task.get('priority', 0) <= 100:
            raise CoordinatorError('Task priority must be an integer from -100 to 100')
        ident = task.get('id')
        if not w.ID.fullmatch(str(ident or '')):
            raise CoordinatorError('Each task needs a stable kebab-case id')
        if ident in seen:
            raise CoordinatorError('Duplicate task id: ' + str(ident))
        seen.add(ident)
        depends = task.get('depends_on', [])
        if not isinstance(depends, list) or any(not w.ID.fullmatch(str(item)) for item in depends):
            raise CoordinatorError('depends_on must be a list of task ids: ' + str(ident))
        if len(set(depends)) != len(depends):
            raise CoordinatorError('Duplicate dependency in task: ' + str(ident))
        if ident in depends:
            raise CoordinatorError('Task may not depend on itself: ' + str(ident))
        if 'native_host_cli' in task and type(task['native_host_cli']) is not bool:
            raise CoordinatorError('native_host_cli must be true or false, never another value: '
                                   + str(ident))
    topological(tasks)
    integration = plan.get('integration')
    if not isinstance(integration, dict) or set(integration) - INTEGRATION_KEYS \
            or not isinstance(integration.get('workflow'), str):
        raise CoordinatorError('Manifest needs an integration workflow declaration')
    if 'native_host_cli' in integration and type(integration['native_host_cli']) is not bool:
        raise CoordinatorError('Integration native_host_cli must be true or false, never another value')
    return workers, binding


def load_plan(root, manifest, project_id, checks=DEFAULT_CHECKS):
    """Validate the entire manifest, identity, Git base, workflows and DAG before any creation.

    `checks` narrows the preflight for read-only or recovery actions: `status` and `cancel` still
    prove structure and identity but do not require a clean tree they are not changing.
    """
    root = _root(root)
    if 'git' in checks:
        identity = repo_map.require_git_root(root)
    else:
        identity = None
    _, manifest_sha, raw = _read_manifest(root, manifest)
    workers, binding = _check_structure(raw, root, project_id)
    fingerprint = digest(canonical(raw).encode('utf-8'))
    plan = dict(raw)
    plan['tasks'] = [dict(task, depends_on=list(task.get('depends_on', [])))
                     for task in raw['tasks']]
    order = topological(plan['tasks'])
    workflows = {}
    for task in plan['tasks']:
        record = _check_workflow(root, task['workflow'], bool(task.get('native_host_cli')))
        if record['workflow_id'] in workflows:
            raise CoordinatorError('Two batch tasks may not share one workflow id: '
                                   + record['workflow_id'])
        workflows[task['id']] = record
    record = _check_workflow(root, plan['integration']['workflow'],
                             bool(plan['integration'].get('native_host_cli')))
    if record['workflow_id'] in workflows:
        raise CoordinatorError('The integration workflow may not reuse a task workflow id: '
                               + record['workflow_id'])
    workflows[INTEGRATION_TASK] = record
    required = sorted({item for task in plan['tasks'] for item in workflows[task['id']]['outputs']})
    available = {w.path_key(name) for name in workflows[INTEGRATION_TASK]['inputs']}
    missing = [item for item in required if w.path_key(item) not in available]
    if missing:
        raise CoordinatorError('The integration workflow must declare every task output as an '
                               'input, so its acceptance actually exercises the combined result: '
                               + ', '.join(missing))
    criteria = workflows[INTEGRATION_TASK]['criteria']
    if criteria and git(root, ['ls-files', '--error-unmatch', '--', criteria],
                        check=False).returncode:
        raise CoordinatorError('Acceptance criteria must be a tracked file at the base commit so '
                               'the root and the integration worktree agree on it: ' + str(criteria))
    base_commit = head = None
    untracked = []
    if 'git' in checks:
        base_commit = _resolve_base(root, plan['base'])
        head = git_text(root, ['rev-parse', '--verify', '--quiet', 'HEAD'], timeout=30)
        if not GIT_OBJECT.fullmatch(head or ''):
            raise CoordinatorError('Project has no commit at HEAD; a batch needs a fixed base')
    if 'clean' in checks:
        if _tracked_status(root):
            raise CoordinatorError('Base has uncommitted tracked changes; the coordinator preserves '
                                   'them instead of overwriting user work')
        untracked = _root_untracked(root)
    if 'ownership' in checks and base_commit:
        ownership = _ownership(root, plan['id'])
        if ownership['holder']:
            raise CoordinatorError('Project root is already owned by ' + ownership['holder']
                                   + '; finish or cancel that work first')
        if head != base_commit:
            raise CoordinatorError('Checked-out HEAD ' + head + ' is not the manifest base '
                                   + base_commit + '; a batch runs against one fixed base')
    return {'root': root, 'manifest': manifest, 'manifest_sha256': manifest_sha,
            'fingerprint': fingerprint, 'plan': plan, 'base_commit': base_commit, 'head': head,
            'workers': workers, 'order': order, 'workflows': workflows, 'git': identity,
            'untracked': untracked, 'required_integration_inputs': required,
            'binding': {'project_id': binding['project_id'],
                        'checkout_id': binding['checkout_id']}}


# ---------------------------------------------------------------------------------
# Root ownership records. The coordinator writes the same reservation a managed workflow
# writes, so ordinary workflow and native-context writers refuse this root without
# needing to know that a coordinator exists.
# ---------------------------------------------------------------------------------

def _ownership(root, batch):
    record = _read_record(_internal(root, COORDINATOR_RESERVATION), MAX_STATE_BYTES,
                          'Coordinator reservation')
    holder = None
    if record is not None:
        if not isinstance(record, dict) or record.get('schema_version') != SCHEMA_VERSION \
                or record.get('project_root') != str(root) \
                or not w.ID.fullmatch(str(record.get('batch', ''))):
            raise CoordinatorError('Invalid or cross-project coordinator reservation')
        if record['batch'] != batch:
            holder = 'coordinator batch ' + record['batch']
    pending = w.active_workflow(root)
    if pending and (record is None or pending['workflow'] != batch):
        holder = holder or ('managed workflow ' + pending['workflow'])
    native = pb.reservation(root)
    if native and (record is None or native['task_id'] != batch):
        holder = holder or ('native context task ' + native['task_id'])
    return {'holder': holder, 'record': record, 'workflow': pending, 'context_task': native}


def _reserve(root, meta, state):
    _write_private(_internal(root, COORDINATOR_RESERVATION),
                   canonical({'schema_version': SCHEMA_VERSION, 'project_root': str(root),
                              'project_id': state['project_id'],
                              'checkout_id': state['checkout_id'], 'batch': state['batch'],
                              'manifest': meta['manifest'],
                              'manifest_sha256': meta['manifest_sha256'], 'reserved_at': now()}),
                   MAX_STATE_BYTES)
    _write_private(_internal(root, '.crewloom/active_workflow.json'),
                   canonical({'project_root': str(root), 'workflow': state['batch'],
                              'plan_sha256': meta['fingerprint']}), MAX_STATE_BYTES)


def _release(root, batch):
    """Give the root back. Only this batch's own records are removed."""
    record = _read_record(_internal(root, COORDINATOR_RESERVATION), MAX_STATE_BYTES,
                          'Coordinator reservation')
    if record is not None and record.get('batch') != batch:
        return
    _unlink(_internal(root, COORDINATOR_RESERVATION))
    pending = w.active_workflow(root)
    if pending and pending['workflow'] == batch:
        _unlink(_internal(root, '.crewloom/active_workflow.json'))


# ---------------------------------------------------------------------------------
# Persisted batch state
# ---------------------------------------------------------------------------------

def _new_state(meta, image):
    batch = meta['plan']['id']
    state = {'schema_version': SCHEMA_VERSION, 'batch': batch, 'project_root': str(meta['root']),
             'project_id': meta['binding']['project_id'],
             'checkout_id': meta['binding']['checkout_id'], 'manifest': meta['manifest'],
             'manifest_sha256': meta['manifest_sha256'], 'manifest_fingerprint': meta['fingerprint'],
             'language': meta['plan'].get('language', 'en'), 'base': meta['plan']['base'],
             'base_commit': meta['base_commit'], 'workers': meta['workers'], 'image': image,
             'order': meta['order'], 'status': 'planned', 'started_at': now(), 'ended_at': None,
             'error': None, 'events_truncated': False,
             'worktrees_root': WORKTREE_DIRECTORY + '/' + batch,
             'controller': None, 'cancellation': None,
             'tasks': {}, 'integration': None, 'review': None, 'publication': None}
    for ident in meta['order']:
        task = next(item for item in meta['plan']['tasks'] if item['id'] == ident)
        state['tasks'][ident] = {'status': 'pending', 'worktree': None, 'branch': None,
                                 'git_dir': None, 'depends_on': list(task['depends_on']),
                                 'workflow': task['workflow'],
                                 'workflow_id': meta['workflows'][ident]['workflow_id'],
                                 'plan_sha256': None, 'criteria_sha256': None,
                                 'base_commit': meta['base_commit'], 'head': None, 'commit': None,
                                  'declared_outputs': meta['workflows'][ident]['outputs'],
                                   'model_steps': meta['workflows'][ident]['model_steps'],
                                   'native_hosts': meta['workflows'][ident]['native_hosts'],
                                   'native_host_cli': meta['workflows'][ident]['native_host_cli'],
                                  'native_cli_run': None,
                                  'outputs': {}, 'ledger': [], 'state_file': None,
                                 'attempts': 0, 'checkout_id': None, 'dependencies': [],
                                 'started_at': None, 'ended_at': None, 'duration_ms': None,
                                 'verified_at': None, 'resume_reason': None, 'error': None}
    return state


def _load_state(root, batch):
    return _read_record(_coordinator_folder(root, batch) / 'state.json', MAX_STATE_BYTES,
                        'Coordinator state')


def _check_state(state, meta):
    if not isinstance(state, dict) or state.get('schema_version') != SCHEMA_VERSION:
        raise CoordinatorError('Malformed coordinator state')
    if state.get('batch') != meta['plan']['id']:
        raise CoordinatorError('Coordinator state belongs to another batch: ' + str(state.get('batch')))
    expected = {'project_root': str(meta['root']), 'project_id': meta['binding']['project_id'],
                'manifest_sha256': meta['manifest_sha256'],
                'manifest_fingerprint': meta['fingerprint']}
    if meta['base_commit']:
        expected['base_commit'] = meta['base_commit']
    for field, value in expected.items():
        if state.get(field) != value:
            raise CoordinatorError('Coordinator state no longer matches the frozen ' + field
                                   + '; use a new batch id for changed work')
    if state.get('status') not in BATCH_STATUSES:
        raise CoordinatorError('Malformed coordinator batch status')
    if not isinstance(state.get('tasks'), dict) or set(state['tasks']) != set(meta['order']):
        raise CoordinatorError('Coordinator state does not describe this batch DAG')
    if state.get('order') != meta['order']:
        raise CoordinatorError('Coordinator state records a different dependency order')
    for ident, record in state['tasks'].items():
        if not isinstance(record, dict) or record.get('status') not in TASK_STATUSES:
            raise CoordinatorError('Malformed coordinator task status')
        if type(record.get('native_host_cli')) is not bool:
            raise CoordinatorError('Coordinator task lost its recorded native CLI decision: '
                                   + ident)
        grant = record.get('native_cli_run')
        if grant is not None and (not isinstance(grant, dict) or any(
                type(grant.get(field)) is not bool for field in ('declared', 'operator_flag',
                                                                 'granted'))):
            raise CoordinatorError('Malformed coordinator native CLI grant record: ' + ident)
    return state


def _save_state(folder, state):
    state['updated_at'] = now()
    with _STATE_LOCK:
        body = json.dumps(state, ensure_ascii=False, indent=2)
    _write_private(folder / 'state.json', body, MAX_STATE_BYTES)
    return state


# ---------------------------------------------------------------------------------
# Worktrees
# ---------------------------------------------------------------------------------

def _worktree_identity(path):
    """Prove a directory is the exact linked worktree this batch created."""
    repo = repo_map.require_git_root(path)
    return {'git_dir': repo['git_dir'], 'work_tree': repo['work_tree'],
            'branch': git_text(path, ['symbolic-ref', '--quiet', '--short', 'HEAD']),
            'head': git_text(path, ['rev-parse', '--verify', '--quiet', 'HEAD']),
            'common_dir': git_text(path, ['rev-parse', '--git-common-dir'])}


def _materialise(root, meta, state, log):
    """Create every task worktree at the fixed base, or prove the recorded one is still exact."""
    batch = state['batch']
    for ident in meta['order']:
        record = state['tasks'][ident]
        path = _worktree_path(root, batch, ident)
        record['worktree'] = str(path.relative_to(root))
        record['branch'] = _branch(batch, ident)
        if path.exists():
            if not (path / '.git').exists():
                raise CoordinatorError('Existing worktree path is not a Git worktree: '
                                       + record['worktree'])
            identity = _worktree_identity(path)
            if identity['branch'] != record['branch']:
                raise CoordinatorError('Worktree ' + record['worktree'] + ' is on branch '
                                       + str(identity['branch']) + ', not ' + record['branch'])
            if identity['git_dir'] != record['git_dir']:
                raise CoordinatorError('Worktree ' + record['worktree'] + ' belongs to another Git '
                                       + 'directory; its recorded identity does not match')
            if identity['head'] != record['head']:
                raise CoordinatorError('Worktree ' + record['worktree'] + ' moved to '
                                       + identity['head'] + ' instead of its recorded head '
                                       + str(record['head']))
            log('worktree.reused', task=ident, head=identity['head'])
            continue
        if not git(root, ['show-ref', '--verify', '--quiet',
                          'refs/heads/' + record['branch']], check=False).returncode:
            raise CoordinatorError('Branch ' + record['branch'] + ' already exists; the coordinator '
                                   'never moves or force-reuses an existing ref')
        _private_folder(path.parent)
        git(root, ['worktree', 'add', '-b', record['branch'], str(path), state['base_commit']])
        os.chmod(str(path), 0o700)
        identity = _worktree_identity(path)
        if identity['branch'] != record['branch'] or identity['head'] != state['base_commit']:
            raise CoordinatorError('Created worktree does not match its expected identity: '
                                   + record['worktree'])
        record['git_dir'] = identity['git_dir']
        record['head'] = identity['head']
        log('worktree.created', task=ident, worktree=record['worktree'], branch=record['branch'])


def _merge_into(path, ident, commit, message):
    """Merge one already-verified commit, keeping every branch and worktree on conflict."""
    if commit is None:
        return False
    if not git(path, ['merge-base', '--is-ancestor', commit, 'HEAD'], check=False).returncode:
        return False
    result = git(path, ['merge', '--no-ff', '--no-edit', '-m', message, commit], check=False)
    if result.returncode:
        detail = (result.stdout + result.stderr).decode('utf-8', 'replace').strip()[-300:]
        raise CoordinatorError('Integration of ' + ident + ' reported a conflict: ' + detail)
    return True


def _commit_outputs(path, label, outputs):
    """Commit only the verified declared artifacts of one task, and nothing else."""
    if not outputs:
        return None, False
    keys = {w.path_key(name) for name in outputs}
    status = git(path, ['status', '--porcelain=v1', '-z', '--', *outputs], check=False).stdout
    entries = [item for item in status.split(b'\0') if item]
    if not entries:
        return git_text(path, ['rev-parse', '--verify', 'HEAD']), False
    changed = set()
    for entry in entries:
        name = entry[3:].decode('utf-8', 'replace')
        if ' -> ' in name:
            name = name.split(' -> ', 1)[1]
        changed.add(w.path_key(name))
    if not changed <= keys:
        raise CoordinatorError('A declared output path is not the changed path it was recorded as')
    git(path, ['add', '--', *outputs])
    staged = {w.path_key(name) for name in
              filter(None, git(path, ['diff', '--cached', '--name-only', '-z'], check=False)
                     .stdout.decode('utf-8', 'replace').split('\0'))}
    if staged != changed:
        raise CoordinatorError('Refusing to commit anything beyond the verified declared outputs; '
                               'the index also holds ' + ', '.join(sorted(staged - changed)))
    git(path, ['commit', '-m', 'crewloom coordinator ' + label])
    return git_text(path, ['rev-parse', '--verify', 'HEAD']), True


# ---------------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------------

def _model_evidence(plan, state, ledger):
    """Recorded generation evidence, plus proof a real command acceptance read what was generated.

    A generation that nothing runs is a plan, not a result. Each generated artifact is therefore
    matched to a later command step that declared it as an input, that completed, and whose recorded
    input digest at execution time is the exact digest the generation published. The proof is a
    digest comparison against recorded evidence, never a claim about what the code means.
    """
    succeeded = {(item.get('workflow'), item.get('step')) for item in ledger['attempts']
                 if item.get('status') == 'succeeded'}
    evidence = []
    for step in plan['steps']:
        if step.get('kind') != 'model':
            continue
        if (plan['id'], step['id']) not in succeeded:
            raise CoordinatorError('No succeeded generation attempt is recorded for '
                                   + plan['id'] + '/' + step['id'])
        record = state['steps'].get(step['id']) or {}
        if record.get('status') != 'complete':
            raise CoordinatorError('Generation step did not complete: ' + plan['id'] + '/'
                                   + step['id'])
        attempts = [item for item in record.get('attempts', [])
                    if item.get('status') == 'finished' and type(item.get('exit_code')) is int]
        if not attempts or attempts[-1]['exit_code'] != 0:
            raise CoordinatorError('Generation attempt did not succeed for ' + plan['id'] + '/'
                                   + step['id'])
        produced = dict(record.get('outputs') or {})
        if {w.path_key(name) for name in produced} != {w.path_key(name) for name in step['outputs']}:
            raise CoordinatorError('Generated artifacts do not match the declared outputs: '
                                   + plan['id'] + '/' + step['id'])
        consumed_by = []
        for output, produced_sha in produced.items():
            consumer = next((other for other in _command_consumers(plan, step)
                             if any(w.path_key(item) == w.path_key(output) for item in other['inputs'])),
                            None)
            if consumer is None:
                raise CoordinatorError('Generated artifact ' + str(output) + ' is not read by any '
                                       'later real command acceptance in ' + plan['id'])
            consumed = state['steps'].get(consumer['id']) or {}
            if consumed.get('status') != 'complete':
                raise CoordinatorError('The command acceptance ' + consumer['id'] + ' for '
                                       + str(output) + ' did not complete')
            observed = next((value for name, value in (consumed.get('inputs') or {}).items()
                             if w.path_key(name) == w.path_key(output)), None)
            if observed != produced_sha:
                raise CoordinatorError('The command acceptance ' + consumer['id'] + ' did not run '
                                       'against the generated bytes of ' + str(output))
            consumed_by.append({'output': str(output), 'sha256': produced_sha, 'step': consumer['id']})
        evidence.append({'step': step['id'], 'kind': 'model', 'host': step['host'],
                         'signature': attempts[-1].get('signature'), 'exit_code': 0,
                         'context_sha256': record.get('context_sha256'),
                         'outputs': produced, 'consumed_by': consumed_by})
    return evidence


def _run_cause(state):
    """The actual recorded reason a managed run did not complete, or nothing at all.

    A step records its own failure, and the run records the same cause, so a finished run is
    never summarised as having no error recorded while its own steps name the stage that failed.
    Every fragment is taken from recorded evidence — the step id, its recorded owning role and its
    recorded message — so no cause is invented here and no failure is hidden behind another one.
    """
    causes = []
    for ident, record in sorted((state.get('steps') or {}).items()):
        if not isinstance(record, dict) or record.get('status') != 'failed':
            continue
        detail = str(record.get('error') or '').strip()[:240]
        causes.append('step ' + str(ident) + ' (role ' + str(record.get('role')) + ') failed'
                      + (': ' + detail if detail else ' with no cause recorded'))
    recorded = str(state.get('error') or '').strip()
    if recorded and not any(recorded in cause for cause in causes):
        causes.append(recorded[:240])
    return '; '.join(causes)[:400] or 'no error recorded'


def _verify_execution(meta, ident, worktree, plan, fingerprint, criteria_sha):
    """Only a complete managed run with unchanged evidence may become a verified task commit."""
    folder, state = w.state_for(worktree, plan, fingerprint)
    if state.get('status') != 'complete':
        raise CoordinatorError('Managed run in ' + str(worktree) + ' finished as '
                               + str(state.get('status')) + ': ' + _run_cause(state))
    if state.get('project_id') != meta['binding']['project_id']:
        raise CoordinatorError('Managed run in ' + str(worktree)
                               + ' belongs to another portable project')
    if state.get('checkout_id') == meta['binding']['checkout_id']:
        raise CoordinatorError('Managed run in ' + str(worktree) + ' reused the root checkout '
                               'binding; every worktree needs its own local checkout identity')
    w.verify_completed(worktree, state)
    if plan.get('criteria'):
        current = w.digest(w.safe_path(worktree, plan['criteria']).read_bytes())
        if current != criteria_sha:
            raise CoordinatorError('Acceptance criteria changed during the managed run')
    ledger = _read_record(_internal(worktree, '.crewloom/attempts.json'), MAX_STATE_BYTES,
                          'Executor attempt ledger') or {'attempts': []}
    if not isinstance(ledger, dict) or not isinstance(ledger.get('attempts'), list):
        raise CoordinatorError('Malformed executor attempt ledger in ' + str(worktree))
    succeeded = {(item.get('workflow'), item.get('step')) for item in ledger['attempts']
                 if item.get('status') == 'succeeded'}
    evidence = []
    for step in plan['steps']:
        if step.get('kind', 'command') != 'command':
            continue
        if (plan['id'], step['id']) not in succeeded:
            raise CoordinatorError('No succeeded executor attempt is recorded for '
                                   + plan['id'] + '/' + step['id'])
        attempts = [item for item in state['steps'][step['id']].get('attempts', [])
                    if item.get('status') == 'finished' and type(item.get('exit_code')) is int]
        if not attempts or attempts[-1]['exit_code'] != 0:
            raise CoordinatorError('Executor attempt did not succeed for ' + plan['id'] + '/'
                                   + step['id'])
        evidence.append({'step': step['id'], 'signature': attempts[-1].get('signature'),
                         'exit_code': attempts[-1]['exit_code'],
                         'image_id': attempts[-1].get('image_id'),
                         'outputs': dict(state['steps'][step['id']].get('outputs') or {})})
    evidence.extend(_model_evidence(plan, state, ledger))
    return {'state_file': str(folder / 'state.json'), 'plan_sha256': fingerprint,
            'project_id': state['project_id'], 'checkout_id': state['checkout_id'],
            'declared_outputs': _declared_outputs(plan), 'outputs': w.hashes(worktree,
                                                                              _declared_outputs(plan)),
            'evidence': evidence, 'completed_steps': sorted(state['steps'])}


def _bind_worktree(meta, path, log):
    """Give one worktree the same portable project identity and its own local checkout binding.

    A worktree starts with no `.crewloom` at all, so the managed run would otherwise record no
    project or checkout identity. Bootstrapping here is idempotent and keeps every managed run
    inside a worktree attributable to one project and one distinct checkout.
    """
    with w.project_lock(w.safe_path(path, '.crewloom', internal=True), reentrant=True):
        pb.bootstrap(path, project_id=meta['binding']['project_id'])
    binding = pb.load_binding(path)
    if binding['project_id'] != meta['binding']['project_id']:
        raise CoordinatorError('Worktree ' + str(path) + ' did not inherit the portable project '
                               'identity')
    if binding['checkout_id'] == meta['binding']['checkout_id']:
        raise CoordinatorError('Worktree ' + str(path) + ' reused the root checkout binding')
    log('worktree.bound', worktree=str(path.name), project_id=binding['project_id'],
        checkout_id=binding['checkout_id'])
    return binding


def _granted_native_cli(record, allow_host_cli):
    """Whether this task's native CLI permission is actually in force for this run.

    Two explicit decisions have to agree: the committed manifest task that declares the workflow
    may use an installed CLI, and the operator running this batch asked for it. Both default to
    no, so a manifest that merely mentions a CLI host never reaches a provider on its own.
    """
    return bool(record.get('native_host_cli')) and bool(allow_host_cli)


def _native_cli_run(record, allow_host_cli, granted):
    """What one call was actually allowed to do with an installed CLI host.

    The committed manifest decision is an intent that survives a refusal, so it is never written
    back from an outcome. This record is the per-run grant instead: what the manifest declared,
    what the operator asked for, and what the two together allowed. Resuming the same batch with
    the operator flag therefore retries the refused task against its still-declared intent,
    instead of reading a refusal back as a retracted decision.
    """
    return {'declared': bool(record.get('native_host_cli')),
            'operator_flag': bool(allow_host_cli), 'granted': bool(granted),
            'hosts': list(record.get('native_hosts') or []), 'at': now()}


def _refuse_without_opt_in(label, record, allow_host_cli):
    """Refuse a native CLI host the operator did not authorise for this call, before any work."""
    if record.get('native_host_cli') and not allow_host_cli:
        raise CoordinatorError(label + ' declares the native CLI host(es) '
                               + ', '.join(record['native_hosts']) + '; this call was not given '
                               'the explicit operator opt-in, so no provider call is made')
    return _granted_native_cli(record, allow_host_cli)


def _execute_task(root, meta, state, ident, image, log, allow_host_cli=False):
    """Run one task's real managed workflow in its own worktree and return a bounded record."""
    record = state['tasks'][ident]
    path = root / record['worktree']
    started = time.time()
    native = _granted_native_cli(record, allow_host_cli)
    outcome = {'task': ident, 'started_at': started, 'ended_at': None, 'duration_ms': None,
               'status': 'blocked', 'error': None, 'commit': None, 'outputs': {},
               'declared_outputs': record['declared_outputs'], 'changed': False,
               'checkout_id': None, 'ledger': [], 'dependencies': [], 'plan_sha256': None,
               'criteria_sha256': None, 'state_file': None, 'native_host_cli': native,
               'native_cli_run': _native_cli_run(record, allow_host_cli, native)}
    try:
        native = _refuse_without_opt_in('Task ' + ident, record, allow_host_cli)
        with _worktree_lock(root / WORKTREE_DIRECTORY / state['batch'], ident):
            dependencies = []
            for dependency in meta['order']:
                if dependency not in record['depends_on']:
                    continue
                ancestor = state['tasks'][dependency]
                if ancestor['status'] != 'verified':
                    raise CoordinatorError('Dependency ' + dependency + ' is not verified: '
                                           + str(ancestor.get('error') or ancestor['status']))
                if _merge_into(path, dependency, ancestor['commit'],
                               'crewloom coordinator ' + state['batch'] + ': integrate '
                               + dependency):
                    dependencies.append(dependency)
                    log('dependency.integrated', task=ident, dependency=dependency,
                        commit=ancestor['commit'])
            outcome['dependencies'] = dependencies
            _bind_worktree(meta, path, log)
            plan, fingerprint = w.read_plan(path, record['workflow'])
            if plan['id'] != record['workflow_id']:
                raise CoordinatorError('Workflow identity changed for task ' + ident)
            criteria_sha = w.digest(w.safe_path(path, plan['criteria']).read_bytes()) \
                if plan.get('criteria') else None
            outcome['plan_sha256'] = fingerprint
            outcome['criteria_sha256'] = criteria_sha
            log('task.started', task=ident, workflow=plan['id'], dependencies=dependencies)
            w.run(path, plan, fingerprint, image, allow_host_cli=native)
            verified = _verify_execution(meta, ident, path, plan, fingerprint, criteria_sha)
            head, changed = _commit_outputs(path, _branch(state['batch'], ident),
                                            verified['declared_outputs'])
            outcome.update(status='verified', commit=head, changed=changed,
                           outputs=verified['outputs'], checkout_id=verified['checkout_id'],
                           ledger=verified['evidence'], state_file=verified['state_file'],
                           head=head)
            log('task.verified', task=ident, commit=head, changed=changed,
                outputs=verified['declared_outputs'])
    except (CoordinatorError, ValueError, OSError, subprocess.SubprocessError) as exc:
        message = str(exc)
        outcome['status'] = 'blocked' if isinstance(exc, CoordinatorError) else 'failed'
        outcome['error'] = message[:400]
        log('task.failed', task=ident, error=message[:400])
    outcome['ended_at'] = time.time()
    outcome['duration_ms'] = round((outcome['ended_at'] - started) * 1000)
    return outcome


def _recheck_verified(root, meta, state, ident, log):
    """Resume re-proves the ledger, output hashes, worktree head, workflow and criteria."""
    record = state['tasks'][ident]
    if not record.get('worktree') or not record.get('git_dir'):
        return False, 'no bound worktree'
    path = root / record['worktree']
    if not path.is_dir():
        return False, 'worktree directory is gone'
    try:
        identity = _worktree_identity(path)
    except (ValueError, OSError) as exc:
        return False, 'worktree identity is unprovable: ' + str(exc)
    if identity['git_dir'] != record['git_dir'] or identity['branch'] != record['branch']:
        return False, 'worktree identity or branch changed'
    if identity['head'] != record['commit']:
        return False, 'worktree head moved to ' + str(identity['head'])
    try:
        plan, fingerprint = w.read_plan(path, record['workflow'])
        if plan['id'] != record['workflow_id'] or fingerprint != record.get('plan_sha256'):
            return False, 'workflow plan changed'
        _, recorded = w.state_for(path, plan, fingerprint)
        if recorded.get('status') != 'complete' \
                or recorded.get('checkout_id') != record.get('checkout_id'):
            return False, 'managed run evidence is no longer complete for this checkout'
        w.verify_completed(path, recorded)
        observed = w.hashes(path, record['declared_outputs'])
        if any(step.get('kind') == 'model' for step in plan['steps']):
            # A generated artifact is re-proved like any other evidence: the same ledger entry and
            # the same consuming acceptance digest, or the task runs again.
            ledger = _read_record(_internal(path, '.crewloom/attempts.json'), MAX_STATE_BYTES,
                                  'Executor attempt ledger') or {'attempts': []}
            if not isinstance(ledger, dict) or not isinstance(ledger.get('attempts'), list):
                return False, 'executor attempt ledger is no longer readable'
            try:
                _model_evidence(plan, recorded, ledger)
            except CoordinatorError as exc:
                return False, str(exc)
        if plan.get('criteria'):
            criteria = w.digest(w.safe_path(path, plan['criteria']).read_bytes())
            if criteria != record.get('criteria_sha256'):
                return False, 'acceptance criteria changed since verification'
    except (ValueError, OSError) as exc:
        return False, 'recorded evidence is stale: ' + str(exc)
    if observed != record.get('outputs'):
        return False, 'declared outputs changed since verification'
    if log:
        log('task.reverified', task=ident, commit=record['commit'],
            outputs=record['declared_outputs'])
    return True, 'unchanged verified evidence'


def _cancel_requested(root, batch):
    return (_coordinator_folder(root, batch) / 'cancel.request').exists()


def _apply_cancellation(root, state, folder, log, reason):
    """Stop future dispatch, keep verified work, and never integrate a cancelled batch again."""
    for record in state['tasks'].values():
        if record['status'] in ('pending', 'running', 'failed', 'blocked'):
            record['status'] = 'cancelled'
    state['status'] = 'cancelled'
    state['ended_at'] = now()
    state['cancellation'] = {'reason': str(reason)[:200], 'at': now(),
                             'verified': sorted(ident for ident, record in state['tasks'].items()
                                                if record['status'] == 'verified')}
    state['integration'] = None
    state['review'] = None
    _unlink(folder / 'cancel.request')
    _release(root, state['batch'])
    log('batch.cancelled', reason=state['cancellation']['reason'],
        verified=state['cancellation']['verified'])
    return _save_state(folder, state)


def _execute(root, meta, state, folder, image, log, allow_host_cli=False):
    """Run the whole DAG with at most `workers` concurrent real managed executors."""
    tasks = {task['id']: task for task in meta['plan']['tasks']}
    pending = []
    for ident in meta['order']:
        record = state['tasks'][ident]
        # The manifest is the committed native CLI decision and outranks this record: a refused
        # run stored an outcome, never a retraction, so the intent is re-derived from the manifest
        # instead of trusted from a state an earlier refusal may have overwritten.
        declared = bool(meta['workflows'][ident]['native_host_cli'])
        if record.get('native_host_cli') != declared:
            record['native_host_cli'] = declared
            log('task.native_cli_intent_restored', task=ident, native_host_cli=declared)
        if record['status'] == 'verified':
            ok, reason = _recheck_verified(root, meta, state, ident, log)
            if not ok:
                record.update(status='pending', commit=None, error=None, resume_reason=reason)
                log('task.recheck_failed', task=ident, reason=reason)
        if record['status'] != 'verified':
            pending.append(ident)
    state['status'] = 'running'
    state['ended_at'] = None
    state['error'] = None
    _save_state(folder, state)
    _reserve(root, meta, state)
    workers = max(1, min(MAX_WORKERS, int(state.get('workers') or meta['workers'])))
    verified = {ident for ident, record in state['tasks'].items() if record['status'] == 'verified'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers,
                                                thread_name_prefix='crewloom-coordinator') as pool:
        futures = {}
        while True:
            if not _cancel_requested(root, state['batch']):
                for ident in sorted(pending, key=lambda item: -tasks[item].get('priority', 0)):
                    if len(futures) >= workers:
                        break
                    blockers = [item for item in tasks[ident]['depends_on']
                                if state['tasks'][item]['status'] in ('failed', 'blocked',
                                                                        'cancelled')]
                    if blockers:
                        pending.remove(ident)
                        state['tasks'][ident].update(status='blocked',
                                                     error='Blocked by ' + ', '.join(blockers))
                        log('task.blocked', task=ident, blockers=blockers)
                        _save_state(folder, state)
                        continue
                    if not set(tasks[ident]['depends_on']) <= verified:
                        continue
                    pending.remove(ident)
                    state['tasks'][ident].update(status='running', started_at=time.time(),
                                                 attempts=state['tasks'][ident]['attempts'] + 1,
                                                 error=None)
                    _save_state(folder, state)
                    futures[pool.submit(_execute_task, root, meta, dict(state), ident, image,
                                        log, allow_host_cli)] = ident
            if not futures:
                break
            done, _ = concurrent.futures.wait(list(futures), timeout=0.2,
                                              return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                ident = futures.pop(future)
                try:
                    outcome = future.result()
                except Exception as exc:  # a worker crash is recorded, never silently dropped
                    # This synthesized record carries every field the update below reads, so the
                    # crash is persisted instead of raising KeyError out of the batch loop.
                    declared = list(state['tasks'][ident].get('declared_outputs') or [])
                    outcome = {'status': 'blocked', 'error': str(exc)[:400],
                               'started_at': None, 'ended_at': time.time(), 'duration_ms': 0,
                               'commit': None, 'outputs': {}, 'declared_outputs': declared,
                               'changed': False,
                               'checkout_id': None, 'ledger': [], 'dependencies': [],
                               'plan_sha256': None, 'criteria_sha256': None, 'state_file': None,
                               'native_host_cli': False,
                               'native_cli_run': _native_cli_run(
                                   state['tasks'][ident], allow_host_cli, False)}
                    log('task.crashed', task=ident, error=str(exc)[:400])
                state['tasks'][ident].update(status=outcome['status'], ended_at=outcome['ended_at'],
                                            duration_ms=outcome['duration_ms'],
                                            error=outcome['error'], outputs=outcome['outputs'],
                                            declared_outputs=outcome['declared_outputs'],
                                            checkout_id=outcome['checkout_id'],
                                            ledger=outcome['ledger'], commit=outcome['commit'],
                                            head=outcome['commit'] or state['tasks'][ident]['head'],
                                            plan_sha256=outcome['plan_sha256'],
                                            criteria_sha256=outcome['criteria_sha256'],
                                            state_file=outcome['state_file'],
                                            dependencies=outcome['dependencies'],
                                            native_cli_run=outcome['native_cli_run'])
                if outcome['status'] == 'verified':
                    state['tasks'][ident]['verified_at'] = now()
                    verified.add(ident)
                _save_state(folder, state)
    if _cancel_requested(root, state['batch']):
        return _apply_cancellation(root, state, folder, log,
                                   'controller observed the cancellation request')
    for ident in meta['order']:
        record = state['tasks'][ident]
        if record['status'] == 'pending':
            record.update(status='blocked', error='Dependency did not reach a verified state')
    state['status'] = 'verified' if verified == set(meta['order']) else 'failed'
    state['ended_at'] = now()
    if state['status'] != 'verified':
        _release(root, state['batch'])
    _save_state(folder, state)
    log('batch.finished', status=state['status'], verified=sorted(verified))
    return state


# ---------------------------------------------------------------------------------
# Public actions
# ---------------------------------------------------------------------------------

def validate(root, manifest, project_id):
    """Read-only preflight of the whole manifest, identity, Git base and DAG; writes nothing."""
    meta = load_plan(root, manifest, project_id)
    return {'status': 'validated', 'batch': meta['plan']['id'], 'project_root': str(meta['root']),
            'project_id': meta['binding']['project_id'],
            'checkout_id': meta['binding']['checkout_id'], 'base': meta['plan']['base'],
            'base_commit': meta['base_commit'], 'head': meta['head'], 'workers': meta['workers'],
            'tasks': [task['id'] for task in meta['plan']['tasks']], 'order': meta['order'],
            'integration_workflow': meta['plan']['integration']['workflow'],
            'required_integration_inputs': meta['required_integration_inputs'],
            'model_steps': {ident: record['model_steps'] for ident, record
                            in sorted(meta['workflows'].items()) if record['model_steps']},
            'native_cli_tasks': sorted(ident for ident, record in meta['workflows'].items()
                                       if record['native_hosts']),
            'native_cli_opt_in': sorted(ident for ident, record in meta['workflows'].items()
                                        if record['native_host_cli']),
            'manifest': manifest, 'manifest_sha256': meta['manifest_sha256'],
            'untracked_paths_at_base': len(meta['untracked']), 'git': meta['git'],
            'limits': {'max_workers': MAX_WORKERS, 'max_tasks': MAX_TASKS,
                       'max_state_bytes': MAX_STATE_BYTES, 'max_event_bytes': MAX_EVENT_BYTES}}


def _preflight_branches(root, meta):
    """A fresh batch may not adopt refs it did not create; resume reuses recorded ones instead."""
    for ident in list(meta['order']) + [INTEGRATION_TASK]:
        branch = _branch(meta['plan']['id'], ident)
        if not git(root, ['show-ref', '--verify', '--quiet', 'refs/heads/' + branch],
                   check=False).returncode:
            raise CoordinatorError('Branch ' + branch + ' already exists; the coordinator never '
                                   'moves, force-reuses or deletes an existing ref')


def _begin(root, meta, folder, log, image):
    """Create the batch record, take the root, and bind every task worktree at the fixed base."""
    with _root_lock(root):
        execution_policy.recover(root)
        _preflight_branches(root, meta)
        state = _new_state(meta, image)
        state['controller'] = {'pid': os.getpid(), 'acquired_at': now(), 'token': uuid.uuid4().hex}
        _save_state(folder, state)
        _reserve(root, meta, state)
        _materialise(root, meta, state, log)
        _save_state(folder, state)
    log('batch.started', batch=state['batch'], base=state['base_commit'],
        workers=state['workers'], tasks=state['order'])
    return state


def start(root, manifest, project_id, workers=None, image=DEFAULT_IMAGE):
    """Take batch ownership and bind every task worktree at the fixed base. Runs no workflow."""
    meta = load_plan(root, manifest, project_id)
    _apply_workers(meta, workers)
    root = meta['root']
    folder = _coordinator_folder(root, meta['plan']['id'])
    log = _Log(folder)
    with _controller_lock(folder, meta['plan']['id']):
        existing = _load_state(root, meta['plan']['id'])
        if existing is not None:
            state = _check_state(existing, meta)
            log('batch.resumed', batch=state['batch'], status=state['status'])
            return _report(meta, state, folder, resumed=True)
        state = _begin(root, meta, folder, log, image)
        return _report(meta, state, folder, resumed=False)


def _apply_workers(meta, workers):
    if workers is None:
        return
    if type(workers) is not int or not 1 <= workers <= MAX_WORKERS:
        raise CoordinatorError('Requested workers must be an integer from 1 to ' + str(MAX_WORKERS))
    meta['workers'] = workers


def run(root, manifest, project_id, workers=None, image=DEFAULT_IMAGE, allow_host_cli=False):
    """Start or resume the batch and execute every task through the real managed executor.

    `allow_host_cli` is this run's explicit operator opt-in for installed CLI hosts. It is
    additional to the manifest task's `native_host_cli`, never a substitute for it.
    """
    meta = load_plan(root, manifest, project_id)
    _apply_workers(meta, workers)
    root = meta['root']
    batch = meta['plan']['id']
    folder = _coordinator_folder(root, batch)
    with _controller_lock(folder, batch):
        log = _Log(folder)
        state = _load_state(root, batch)
        if state is None:
            state = _begin(root, meta, folder, log, image)
        else:
            state = _check_state(state, meta)
            if state['status'] == 'published':
                raise CoordinatorError('Published batch ' + batch + ' cannot run again; start a '
                                       'new batch id for new work')
            if state.get('workers') != meta['workers']:
                log('batch.workers_changed', recorded=state.get('workers'),
                    requested=meta['workers'])
                state['workers'] = meta['workers']
            if state.get('image') != image:
                log('batch.image_changed', recorded=state.get('image'), requested=image)
                state['image'] = image
            if _cancel_requested(root, batch) and not any(
                    record['status'] == 'verified' for record in state['tasks'].values()):
                return _report(meta, _apply_cancellation(root, state, folder, log,
                                                         'operator request'), folder, True)
            _unlink(folder / 'cancel.request')
            with _root_lock(root):
                execution_policy.recover(root)
                _materialise(root, meta, state, log)
                _save_state(folder, state)
        state['controller'] = {'pid': os.getpid(), 'acquired_at': now(), 'token': uuid.uuid4().hex}
        _save_state(folder, state)
        _execute(root, meta, state, folder, image, log, allow_host_cli)
        return _report(meta, state, folder, resumed=True)


def status(root, manifest, project_id):
    """Read the recorded batch, worktrees and evidence references without changing anything."""
    meta = load_plan(root, manifest, project_id, checks=('structure',))
    root = meta['root']
    batch = meta['plan']['id']
    folder = _coordinator_folder(root, batch)
    state = _load_state(root, batch)
    if state is None:
        return {'status': 'absent', 'batch': batch, 'project_root': str(root),
                'project_id': meta['binding']['project_id'],
                'checkout_id': meta['binding']['checkout_id'], 'manifest': manifest,
                'manifest_sha256': meta['manifest_sha256'], 'order': meta['order'],
                'state_file': None,
                'tasks': [{'id': ident, 'status': 'absent'} for ident in meta['order']],
                'instruction': 'Run crewloom coordinator run with this manifest to start the batch.'}
    return _report(meta, _check_state(state, meta), folder, resumed=True)


def cancel(root, manifest, project_id, reason='operator request'):
    """Stop future dispatch and persist the request. Verified results are kept for resume."""
    meta = load_plan(root, manifest, project_id, checks=('structure',))
    root = meta['root']
    batch = meta['plan']['id']
    folder = _coordinator_folder(root, batch)
    state = _check_state(_load_state(root, batch), meta) \
        if _load_state(root, batch) is not None else None
    if state is None:
        raise CoordinatorError('No coordinator state for batch ' + batch)
    if state['status'] == 'published':
        raise CoordinatorError('A published batch is not cancellable; its root is already integrated')
    if state['status'] == 'cancelled':
        return {'status': 'cancelled', 'batch': batch, 'idempotent': True,
                'verified': (state.get('cancellation') or {}).get('verified', []),
                'drained': True,
                'instruction': 'Cancellation preserves verified evidence; rerun to resume.'}
    log = _Log(folder)
    try:
        with _controller_lock(folder, batch):
            state = _apply_cancellation(root, state, folder, log, reason)
            return {'status': 'cancelled', 'batch': batch, 'idempotent': False,
                    'verified': state['cancellation']['verified'], 'drained': True,
                    'instruction': 'The root was not integrated. Rerun to resume verified tasks '
                                   'without new executor attempts.'}
    except CoordinatorError as exc:
        if 'another live controller' not in str(exc):
            raise
        _write_private(folder / 'cancel.request',
                       canonical({'at': now(), 'reason': str(reason)[:200], 'batch': batch}),
                       MAX_STATE_BYTES)
        return {'status': 'cancellation_requested', 'batch': batch, 'drained': False,
                'running': sorted(ident for ident, record in state['tasks'].items()
                                  if record['status'] == 'running'),
                'instruction': 'A live controller owns this batch. It stops dispatching, lets '
                               'in-flight managed work drain, releases the root, and records the '
                               'verified tasks for resume. Claiming a lock back never stops a '
                               'container that outlived its process.'}


def prepare(root, manifest, project_id, image=None, allow_host_cli=False):
    """Combine every verified task commit once, then run the actual combined acceptance.

    The same two explicit decisions govern an installed CLI host in the integration workflow as
    govern one in a task: the manifest declaration and this call's operator opt-in.
    """
    meta = load_plan(root, manifest, project_id)
    root = meta['root']
    batch = meta['plan']['id']
    folder = _coordinator_folder(root, batch)
    state = _check_state(_load_state(root, batch), meta) \
        if _load_state(root, batch) is not None else None
    if state is None:
        raise CoordinatorError('No coordinator state for batch ' + batch)
    if state['status'] not in INTEGRATABLE:
        raise CoordinatorError('Batch is ' + state['status'] + '; every task must be verified '
                               'before integration')
    unverified = {ident: state['tasks'][ident].get('error') or state['tasks'][ident]['status']
                  for ident in meta['order'] if state['tasks'][ident]['status'] != 'verified'}
    if unverified:
        raise CoordinatorError('Refusing partial acceptance; unverified tasks: '
                               + ', '.join(sorted(unverified)))
    # Refused before the integration worktree exists, so an unauthorised host costs nothing.
    native = _refuse_without_opt_in('The integration workflow',
                                    meta['workflows'][INTEGRATION_TASK], allow_host_cli)
    image = image or state.get('image') or DEFAULT_IMAGE
    log = _Log(folder)
    with _controller_lock(folder, batch):
        state = _check_state(_load_state(root, batch), meta)
        for ident in meta['order']:
            ok, reason = _recheck_verified(root, meta, state, ident, log)
            if not ok:
                raise CoordinatorError('Verified task ' + ident + ' no longer holds: ' + reason)
        if _cancel_requested(root, batch):
            raise CoordinatorError('Batch was cancelled; integration needs an explicit new run')
        path = _worktree_path(root, batch, INTEGRATION_TASK)
        record = {'status': 'pending', 'worktree': str(path.relative_to(root)),
                  'branch': _branch(batch, INTEGRATION_TASK), 'git_dir': None}
        if not path.exists():
            if not git(root, ['show-ref', '--verify', '--quiet',
                              'refs/heads/' + record['branch']], check=False).returncode:
                raise CoordinatorError('Integration branch ' + record['branch']
                                       + ' already exists and is never force-reused')
            _private_folder(path.parent)
            git(root, ['worktree', 'add', '-b', record['branch'], str(path),
                       state['base_commit']])
            os.chmod(str(path), 0o700)
        if git(path, ['rev-parse', '--verify', '--quiet', 'MERGE_HEAD'], check=False).stdout.strip():
            raise CoordinatorError('An integration merge is unresolved in ' + record['worktree']
                                   + '; resolve and commit it there, then run prepare again')
        identity = _worktree_identity(path)
        if identity['branch'] != record['branch']:
            raise CoordinatorError('Integration worktree is on another branch: '
                                   + str(identity['branch']))
        record['git_dir'] = identity['git_dir']
        merged = []
        for ident in meta['order']:
            try:
                changed = _merge_into(path, ident, state['tasks'][ident]['commit'],
                                      'crewloom coordinator ' + batch + ': integrate ' + ident)
            except CoordinatorError:
                conflicts = sorted(filter(None, git(path, ['diff', '--name-only', '-z',
                                                          '--diff-filter=U'],
                                                    check=False).stdout
                                          .decode('utf-8', 'replace').split('\0')))
                state['integration'] = {**record, 'status': 'conflict', 'conflicts': conflicts,
                                        'base': state['base_commit'],
                                        'blocked_task': ident}
                state['status'] = 'conflict'
                state['review'] = None
                state['error'] = 'Integration conflict on ' + (', '.join(conflicts) or ident)
                _save_state(folder, state)
                log('integration.conflict', task=ident, conflicts=conflicts)
                raise
            if changed:
                merged.append(ident)
                log('integration.merged', task=ident, commit=state['tasks'][ident]['commit'])
        state['status'] = 'integrating'
        _save_state(folder, state)
        try:
            _bind_worktree(meta, path, log)
            plan, fingerprint = w.read_plan(path, meta['plan']['integration']['workflow'])
            criteria_sha = w.digest(w.safe_path(path, plan['criteria']).read_bytes()) \
                if plan.get('criteria') else None
            log('integration.acceptance_started', workflow=plan['id'])
            w.run(path, plan, fingerprint, image, allow_host_cli=native)
            verified = _verify_execution(meta, INTEGRATION_TASK, path, plan, fingerprint,
                                         criteria_sha)
        except (CoordinatorError, ValueError, OSError, subprocess.SubprocessError) as exc:
            state['status'] = 'failed'
            state['error'] = 'Combined acceptance failed: ' + str(exc)[:300]
            state['review'] = None
            _save_state(folder, state)
            log('integration.acceptance_failed', error=str(exc)[:300])
            raise CoordinatorError(state['error']) from exc
        head, _ = _commit_outputs(path, _branch(batch, INTEGRATION_TASK),
                                  verified['declared_outputs'])
        diff_sha = _diff_digest(root, state['base_commit'], head)
        outputs = dict(verified['outputs'])
        for ident in meta['order']:
            outputs.update(state['tasks'][ident]['outputs'])
        state['integration'] = {**record, 'status': 'review_ready', 'merged': merged,
                                'head': head, 'workflow': plan['id'],
                                'workflow_sha256': fingerprint, 'base': state['base_commit'],
                                'declared_outputs': verified['declared_outputs'],
                                'outputs': outputs, 'diff_sha256': diff_sha,
                                'ledger': verified['evidence'], 'state_file': verified['state_file'],
                                'criteria': plan.get('criteria'),
                                'image_id': next((item['image_id'] for item in verified['evidence']
                                                  if item.get('image_id')), None),
                                'reviewed_artifacts': len(outputs)}
        state['status'] = 'review_ready'
        state['error'] = None
        state['review'] = None
        _save_state(folder, state)
        log('integration.ready', head=head, diff_sha256=diff_sha)
        return _report(meta, state, folder, resumed=True)


def review(root, manifest, project_id, principal=None, expected_base=None, candidate_head=None,
           diff_sha256=None, role=None, token=None):
    """Record one explicit reviewed decision over a named base, candidate head and diff digest."""
    meta = load_plan(root, manifest, project_id)
    root = meta['root']
    batch = meta['plan']['id']
    state = _check_state(_load_state(root, batch), meta) \
        if _load_state(root, batch) is not None else None
    if state is None:
        raise CoordinatorError('No coordinator state for batch ' + batch)
    if state['status'] not in ('review_ready', 'reviewed'):
        raise CoordinatorError('Batch is ' + state['status']
                               + '; prepare the combined candidate first')
    integration = state['integration']
    for name, value in (('--expected-base', expected_base), ('--candidate-head', candidate_head),
                        ('--diff-sha256', diff_sha256)):
        if not value:
            raise CoordinatorError('An explicit reviewed publication needs ' + name)
    if expected_base != integration['base']:
        raise CoordinatorError('Expected base ' + str(expected_base) + ' is not the candidate base '
                               + integration['base'])
    if candidate_head != integration['head']:
        raise CoordinatorError('Expected candidate head ' + str(candidate_head)
                               + ' is not the prepared candidate ' + integration['head'])
    if diff_sha256 != integration['diff_sha256']:
        raise CoordinatorError('Expected diff digest does not match the prepared candidate')
    if _diff_digest(root, integration['base'], integration['head']) != diff_sha256:
        raise CoordinatorError('Candidate diff changed after preparation')
    settings = reviewer_credentials.policy(root)
    if settings['mode'] == 'label' and not (principal or '').strip():
        raise CoordinatorError('Declared-label review needs an explicit reviewer identifier')
    integration_plan, _ = w.read_plan(root, meta['plan']['integration']['workflow'])
    owning_role = role or integration_plan['steps'][-1]['role']
    if not w.ID.fullmatch(str(owning_role)) or not (w.ROLES / owning_role / 'SKILL.md').is_file():
        raise CoordinatorError('Unknown owning role for the integration decision: '
                               + str(owning_role))
    proof = reviewer_credentials.authorize(root, 'coordinator-' + batch,
                                           {'id': INTEGRATION_TASK, 'role': owning_role},
                                           integration['outputs'], integration.get('criteria'),
                                           label=principal, token=token)
    folder = _coordinator_folder(root, batch)
    state['review'] = {'decided_at': proof['decided_at'], 'principal': proof['principal'],
                       'method': proof['method'], 'proof': proof,
                       'proof_sha256': proof['proof_sha256'], 'expected_base': expected_base,
                       'candidate_head': candidate_head, 'diff_sha256': diff_sha256,
                       'owning_role': owning_role, 'reviewed_artifacts': integration['reviewed_artifacts'],
                       'consumed_at': None}
    state['status'] = 'reviewed'
    _Log(folder)('review.decided', principal=proof['principal'], method=proof['method'],
                 candidate_head=candidate_head, proof_sha256=proof['proof_sha256'])
    _save_state(folder, state)
    return {'status': 'reviewed', 'batch': batch, 'principal': proof['principal'],
            'method': proof['method'], 'expected_base': expected_base,
            'candidate_head': candidate_head, 'diff_sha256': diff_sha256,
            'reviewed_artifacts': integration['reviewed_artifacts'],
            'proof_sha256': proof['proof_sha256'], 'review_policy': settings,
            'limitation': 'A credential proves possession of a registered principal secret, not '
                          'the presence of an independent human reviewer. In declared-label mode '
                          'the identifier names a reviewer without authenticating one.'}


def _consume_nonce(folder, proof, batch, head):
    path = folder / 'review-nonces.json'
    record = _read_record(path, MAX_STATE_BYTES, 'Consumed review decisions') or \
        {'schema_version': SCHEMA_VERSION, 'consumed': []}
    if not isinstance(record, dict) or not isinstance(record.get('consumed'), list):
        raise CoordinatorError('Malformed consumed review record')
    nonce = str(proof.get('nonce') or '')
    if any(isinstance(item, dict) and item.get('nonce') == nonce for item in record['consumed']):
        raise CoordinatorError('This review decision was already consumed; replaying one recorded '
                               'publication is refused')
    record['consumed'].append({'nonce': nonce, 'batch': batch, 'principal': proof.get('principal'),
                               'method': proof.get('method'), 'head': head, 'at': now()})
    record['consumed'] = record['consumed'][-MAX_CONSUMED:]
    _write_private(path, json.dumps(record, ensure_ascii=False, indent=2), MAX_STATE_BYTES)
    return record


def _verify_decision(root, meta, state, integration, settings):
    """Re-check one recorded decision against the exact artifacts, criteria and authority.

    Verified mode uses the project's issuance authority: an HMAC signature, the registry epoch,
    and revocation. Declared-label mode has no authority to check, so it is verified as what it
    actually is: an intact recorded declaration bound to this exact scope. No signature is
    invented for it, and the report says which of the two produced the decision.
    """
    proof = state['review']['proof']
    method = reviewer_credentials.CREDENTIAL_METHOD if settings['mode'] == 'verified' \
        else reviewer_credentials.LABEL_METHOD
    integration_plan, _ = w.read_plan(root, meta['plan']['integration']['workflow'])
    if integration_plan['id'] != integration['workflow']:
        raise CoordinatorError('Integration workflow identity changed')
    scope = reviewer_credentials.binding(root, 'coordinator-' + state['batch'],
                                         {'id': INTEGRATION_TASK,
                                          'role': state['review']['owning_role']},
                                         integration['outputs'], integration.get('criteria'))
    if method == reviewer_credentials.CREDENTIAL_METHOD:
        outcome = reviewer_credentials.verify(proof, scope, method)
        if outcome != 'valid':
            raise CoordinatorError('Recorded review decision is ' + outcome)
        credential = reviewer_credentials.verify_credential(root, proof)
        if credential != 'valid':
            raise CoordinatorError('Reviewer credential is ' + credential)
        return
    if not isinstance(proof, dict) or proof.get('proof_sha256') != \
            reviewer_credentials.proof_digest(proof):
        raise CoordinatorError('Recorded review decision is tampered')
    if proof.get('method') != method:
        raise CoordinatorError('Recorded review decision is unverified')
    if any(proof.get(field) != value for field, value in scope.items()):
        raise CoordinatorError('Recorded review decision is stale')


def _revalidate_publication(root, meta, state, expected_base, candidate_head, diff_sha256):
    """Re-prove every freeze input, task, worktree, proof and root precondition before writing."""
    integration = state['integration']
    if state['base_commit'] != expected_base:
        raise CoordinatorError('Recorded base no longer matches --expected-base')
    if integration['head'] != candidate_head or integration['diff_sha256'] != diff_sha256:
        raise CoordinatorError('Prepared candidate no longer matches the reviewed head or diff digest')
    binding = pb.load_binding(root)
    if binding['project_id'] != state['project_id'] or binding['checkout_id'] != state['checkout_id']:
        raise CoordinatorError('Project identity or local checkout binding changed since the batch '
                               'was prepared')
    for ident in meta['order']:
        ok, reason = _recheck_verified(root, meta, state, ident, None)
        if not ok:
            raise CoordinatorError('Verified task ' + ident + ' no longer holds: ' + reason)
    identity = _worktree_identity(root / integration['worktree'])
    if identity['head'] != candidate_head:
        raise CoordinatorError('Integration worktree head moved to ' + identity['head'])
    if identity['git_dir'] != integration['git_dir']:
        raise CoordinatorError('Integration worktree Git identity changed')
    if _diff_digest(root, expected_base, candidate_head) != diff_sha256:
        raise CoordinatorError('Candidate diff digest changed since the review')
    if git(root, ['merge-base', '--is-ancestor', expected_base, candidate_head],
           check=False).returncode:
        raise CoordinatorError('Candidate is not a descendant of the expected base; a root '
                               'publication is a fast-forward only')
    if _tracked_status(root):
        raise CoordinatorError('Root has uncommitted tracked changes; nothing was written')
    untracked = _root_untracked(root)
    keys = {w.path_key(name): name for name in untracked}
    collisions = [relative for relative in _candidate_paths(root, expected_base, candidate_head)
                  if w.path_key(relative) in keys or (root / relative).is_symlink()]
    if collisions:
        raise CoordinatorError('Untracked root files collide with the candidate and were preserved: '
                               + ', '.join(sorted(collisions)))
    _verify_decision(root, meta, state, integration, reviewer_credentials.policy(root))
    return untracked


def publish(root, manifest, project_id, expected_base, candidate_head, diff_sha256):
    """Fast-forward the root onto the reviewed candidate exactly once, under the project lock."""
    meta = load_plan(root, manifest, project_id)
    root = meta['root']
    batch = meta['plan']['id']
    folder = _coordinator_folder(root, batch)
    loaded = _load_state(root, batch)
    if loaded is None:
        raise CoordinatorError('No coordinator state for batch ' + batch)
    state = _check_state(loaded, meta)
    if state['status'] != 'reviewed':
        raise CoordinatorError('Batch is ' + state['status']
                               + '; an explicit reviewed decision is required before publication')
    log = _Log(folder)
    with _controller_lock(folder, batch):
        state = _check_state(_load_state(root, batch), meta)
        with _root_lock(root):
            untracked = _revalidate_publication(root, meta, state, expected_base, candidate_head,
                                               diff_sha256)
            head = git_text(root, ['rev-parse', '--verify', '--quiet', 'HEAD'])
            if head != expected_base:
                raise CoordinatorError('Root HEAD ' + head + ' is not the reviewed base '
                                       + expected_base)
            result = git(root, ['merge', '--ff-only', '--no-edit', candidate_head], check=False)
            if result.returncode:
                raise CoordinatorError('Root fast-forward refused: '
                                       + result.stderr.decode('utf-8', 'replace').strip()[:300]
                                       + '; the root is unchanged')
            published = git_text(root, ['rev-parse', '--verify', 'HEAD'])
            _consume_nonce(folder, state['review']['proof'], batch, published)
            state['publication'] = {'expected_base': expected_base,
                                    'candidate_head': candidate_head,
                                    'diff_sha256': diff_sha256, 'published_head': published,
                                    'principal': state['review']['principal'],
                                    'method': state['review']['method'],
                                    'proof_sha256': state['review']['proof_sha256'],
                                    'nonce': state['review']['proof']['nonce'],
                                    'project_id': state['project_id'],
                                    'checkout_id': state['checkout_id'], 'at': now(),
                                    'untracked_preserved': len(untracked),
                                    'worktrees_retained': True}
            state['review']['consumed_at'] = now()
            state['status'] = 'published'
            _release(root, batch)
            _save_state(folder, state)
        log('batch.published', published=published, principal=state['review']['principal'])
    return _report(meta, state, folder, resumed=True)


def _report(meta, state, folder, resumed):
    """One bounded report: exact worktrees, evidence references, ownership and honest limits."""
    tasks = []
    for ident in meta['order']:
        record = dict(state['tasks'][ident])
        record['id'] = ident
        tasks.append(record)
    intervals = sorted((item['started_at'], item['ended_at']) for item in tasks
                       if item.get('started_at') and item.get('ended_at'))
    overlap = any(intervals[index][0] < intervals[index - 1][1] for index in range(1, len(intervals)))
    return {'status': state['status'], 'batch': state['batch'], 'project_root': state['project_root'],
            'project_id': state['project_id'], 'checkout_id': state['checkout_id'],
            'manifest': state['manifest'], 'manifest_sha256': state['manifest_sha256'],
            'base': state['base'], 'base_commit': state['base_commit'],
            'workers': state['workers'], 'image': state.get('image'), 'order': state['order'],
            'tasks': tasks, 'workers_overlapped': overlap, 'error': state.get('error'),
            'integration': state.get('integration'), 'review': state.get('review'),
            'publication': state.get('publication'), 'cancellation': state.get('cancellation'),
            'controller': state.get('controller'),
            'controller_live': _controller_is_live(folder),
            'state_file': str(folder / 'state.json'), 'events': str(folder / 'events.jsonl'),
            'events_truncated': bool(state.get('events_truncated')),
            'worktrees_root': str(meta['root'] / state['worktrees_root']), 'resumed': bool(resumed),
            'claims': [
                'Tasks ran the real managed executor inside their own Git worktree, never a host '
                'shell chosen by this coordinator.',
                'A model step is only accepted with a later real command acceptance that read its '
                'generated bytes in that same worktree; an unconsumed artifact is never committed.',
                'An installed CLI host needs both the manifest task opt-in and this run\'s '
                'operator flag; the coordinator itself makes no provider call.',
                'The root checkout is unchanged until an explicit reviewed fast-forward.',
                'Worktrees and runtime evidence are retained after publication.',
                'No push, GitHub merge, reset, forced checkout or untracked cleanup is performed.',
                'Claiming a lock back does not stop a container or command that outlived its process.',
                'A declared-label review names a reviewer; a credential proves key possession only.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('validate', 'run', 'status', 'cancel', 'prepare',
                                           'review', 'publish'))
    parser.add_argument('--project', required=True, help='Explicit canonical project root')
    parser.add_argument('--project-id', required=True,
                        help='Explicit portable project identity; never inferred')
    parser.add_argument('--manifest', required=True,
                        help='Coordinator manifest, relative to --project')
    parser.add_argument('--workers', type=int, default=None, help='Concurrent tasks, 1 to 4')
    parser.add_argument('--image', default=DEFAULT_IMAGE)
    parser.add_argument('--reason', default='operator request')
    parser.add_argument('--allow-host-cli', action='store_true',
                        help='This run\'s explicit operator opt-in for installed CLI model hosts; '
                             'the manifest task must also declare native_host_cli true')
    parser.add_argument('--principal', help='Declared reviewer identifier (label mode)')
    parser.add_argument('--role', help='Owning role for the integration decision; default is the '
                                       'integration workflow final step role')
    parser.add_argument('--expected-base')
    parser.add_argument('--candidate-head')
    parser.add_argument('--diff-sha256')
    parser.add_argument('--reviewer-token-stdin', action='store_true',
                        help='Read the reviewer credential from standard input, never an argument')
    args = parser.parse_args(argv)
    try:
        if args.action == 'validate':
            result = validate(args.project, args.manifest, args.project_id)
        elif args.action == 'status':
            result = status(args.project, args.manifest, args.project_id)
        elif args.action == 'run':
            result = run(args.project, args.manifest, args.project_id, args.workers, args.image,
                        args.allow_host_cli)
        elif args.action == 'cancel':
            result = cancel(args.project, args.manifest, args.project_id, args.reason)
        elif args.action == 'prepare':
            result = prepare(args.project, args.manifest, args.project_id, args.image,
                             args.allow_host_cli)
        elif args.action == 'review':
            token = reviewer_credentials.credential_from_environment(
                sys.stdin if args.reviewer_token_stdin else None)
            result = review(args.project, args.manifest, args.project_id, args.principal,
                            args.expected_base, args.candidate_head, args.diff_sha256, args.role,
                            token)
        else:
            result = publish(args.project, args.manifest, args.project_id, args.expected_base,
                             args.candidate_head, args.diff_sha256)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('status') in ('validated', 'absent', 'verified', 'cancelled',
                                         'cancellation_requested', 'review_ready', 'reviewed',
                                         'published') else 2


if __name__ == '__main__':
    raise SystemExit(main())