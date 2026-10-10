"""Native host lifecycle adapters: install, observe, guard and verify one bound project's host callbacks.

One adapter engine serves three hosts without pretending they behave alike. A host is only
declared *installed* when its rendered payloads are present and unchanged, *delivered* when this
exact installation returned a successful injection callback, *observed* when a real host callback
reached this engine with the exact installed digest, and *verified* only when this project's own
Docker executor ledger resolved configured acceptance evidence. Those four states are separate
fields and never collapse into one another, so an idle event, a Stop hook or a confident reply can
never promote itself to verified work, and an installed plugin file is never read as proof that a
host received anything. Each state is scoped to the installation contract that produced it, so a
reinstalled project starts again from its own evidence.

The engine adds no second context engine and no self-reported checks. Frozen context comes from
`project_context` through `project_binding.enter`, freshness from recorded generation digests,
and acceptance evidence from the existing managed workflow ledger through `project_binding.finish`.
Every callback revalidates the explicit project identity, the host version, the payload shape,
the session and turn scope, and the installed payload digest before a single byte of project
state is written, so a copied configuration, a foreign working directory or an unknown host is
refused rather than adopted.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

import crewloom_resources as resources
import project_binding as pb
import project_context as pc
import workflow as w

SCHEMA_VERSION = 1
STATE_RELATIVE = '.crewloom/hosts'
MAX_STATE_BYTES = 256 * 1024
MAX_EVENTS = 512
MAX_TEXT = 128 * 1024
MAX_PATCH_RECORDS = 64
MAX_MANAGED_COMMANDS = 16
ADDITIONAL_CONTEXT_LIMIT = 65536
MAX_HOOK_ERROR_BYTES = 512
OWNER = 'host-lifecycle'
COORDINATOR_RESERVATION = '.crewloom/active_coordinator.json'
NORMALIZED_SHA = '0' * 64

# Every project path component a host agent may never write, however it spells itself. `.agents`
# and `.claude` hold installed role memory, `.crewloom` holds runtime state, `.git` holds Git
# state, and `.codex` and `.opencode` hold the host configuration and plugins whose guards this
# adapter installs. The project policy file sets the very enforcement this engine serves, so a
# declared output never buys permission to write any of these, not even the host's own config.
FORBIDDEN_COMPONENTS = ('.crewloom', '.git', '.agents', '.claude', '.codex', '.opencode')
FORBIDDEN_NAMES = ('crewloom.project.json',)
FORBIDDEN_KEYS = frozenset(w.folded(item) for item in FORBIDDEN_COMPONENTS + FORBIDDEN_NAMES)

HOSTS = ('codex', 'claude', 'opencode')

# Versions whose callbacks and deny schemas were actually observed. A different version is
# refused rather than extrapolated: the installed plugin package types are 1.18.23 while the
# binary is 1.18.32, so a schema hint is never evidence for a binary that was never run.
SUPPORTED_VERSIONS = {
    'codex': ('0.155.1',),
    'claude': ('2.1.150',),
    'opencode': ('1.18.32',),
}

HOST_SPEC = {
    'codex': {
        'template': 'adapters/codex/hooks.json',
        'control': '.codex/hooks.json',
        'delivery': 'needs-project-trust',
        'launcher': 'session-inline',
        'context_limit_key': 'additionalContextLimit',
        'stages': {'SessionStart': 'prepare', 'UserPromptSubmit': 'inject', 'PreToolUse': 'guard',
                   'PostToolUse': 'checkpoint', 'Stop': 'verify', 'SessionEnd': 'close'},
        'guard_tools': ('apply_patch', 'shell'),
        'code_mode_host_required': True,
    },
    'claude': {
        'template': 'adapters/claude/settings.json',
        'control': '.claude/settings.json',
        'delivery': 'needs-project-trust',
        'launcher': 'session-inline',
        'context_limit_key': None,
        'stages': {'SessionStart': 'prepare', 'UserPromptSubmit': 'inject', 'PreToolUse': 'guard',
                   'PostToolUse': 'checkpoint', 'Stop': 'verify', 'SessionEnd': 'close'},
        'guard_tools': ('Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'Bash'),
        'code_mode_host_required': False,
    },
    'opencode': {
        'template': 'adapters/opencode/crewloom-lifecycle.js',
        'control': '.opencode/plugins/crewloom-lifecycle.js',
        'delivery': 'project-plugin',
        'launcher': 'project-plugin',
        'context_limit_key': None,
        'stages': {'chat.message': 'prepare',
                   'experimental.chat.system.transform': 'inject',
                   'tool.execute.before': 'guard',
                   'tool.execute.after': 'checkpoint',
                   'session.idle': 'verify',
                   'session.error': 'close'},
        'guard_tools': ('patch', 'write', 'edit', 'bash'),
        'code_mode_host_required': False,
    },
}

# The stage a bare stop or idle event may reach. It exists to run configured acceptance, never to
# turn a host signal into a claim about verified work.
STAGES = ('prepare', 'inject', 'guard', 'checkpoint', 'verify', 'close')

# Hosts whose control config is a JSON document this installer may merge into. A host whose owned
# payload is a single plugin file cannot be merged, so an existing file there is never replaced.
MERGEABLE_HOSTS = ('codex', 'claude')

# The task states a native session cannot continue inside. `project_binding.enter` returns a
# completed task unchanged with its frozen generation, and a cancelled task keeps the record of the
# work that was cancelled, so a later turn of the same host session is new work rather than a retry
# of this one. This is the shared terminal set plus the explicit cancellation state.
CLOSED_SCOPE_STATES = tuple(pb.TERMINAL_STATES) + ('cancelled',)

# How many real task scopes one host session may use before this engine stops guessing.
MAX_SCOPE_EPOCHS = 64

LIMITS = (
    'Covers only the callbacks the host actually delivers on the recorded version; arbitrary '
    'external host tools and privileged processes stay outside this boundary.',
    'The Docker broker remains the strong managed boundary. A hook guard runs inside the host '
    'process and does not close a race against a privileged concurrent mutation.',
    'There is no universal agent enforcement: a host that does not deliver an event is reported '
    'unobserved rather than assumed covered.',
    'No shell parser is claimed. A managed command is matched by exact canonical working directory '
    'and exact argv, never by a substring inside a compound command.',
    'The bounded project task log keeps digests, byte counts, outcomes and its installation '
    'identity, not the injected context body: the delivered text is returned to the host on the '
    'callback that produced it and repeated turns cannot accumulate whole source bodies in state.',
)


class LifecycleError(ValueError):
    """One refusal reason for a native lifecycle action; every caller reports it verbatim."""


def now():
    return pb.now()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def digest(value):
    return w.digest(value if isinstance(value, bytes) else str(value).encode('utf-8'))


# ---------------------------------------------------------------------------- owned state


def _spec(host):
    if host not in HOSTS:
        raise LifecycleError('Host must be one of: ' + ', '.join(HOSTS))
    return HOST_SPEC[host]


def _private_folder(path):
    """One bounded owner-only directory: no symlink, no foreign replacement."""
    if path.is_symlink():
        raise LifecycleError('Native lifecycle state path may not be a symlink: ' + str(path))
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise LifecycleError('Native lifecycle state path is not a real directory: ' + str(path))
    try:
        os.chmod(str(path), 0o700)
    except OSError as exc:
        raise LifecycleError('Native lifecycle state must be owner-only: ' + str(exc))
    return path


def _write_private(path, data, limit=MAX_STATE_BYTES):
    """Atomically replace one bounded owner-only record, refusing links and oversized bodies."""
    if isinstance(data, str):
        data = data.encode('utf-8')
    if len(data) > limit:
        raise LifecycleError('Bounded native lifecycle record exceeded its limit: ' + path.name)
    if path.is_symlink():
        raise LifecycleError('Native lifecycle record may not be a symlink: ' + path.name)
    if path.exists() and (path.is_dir() or path.stat().st_nlink != 1):
        raise LifecycleError('Native lifecycle record must be a regular single-link file: ' + path.name)
    _private_folder(path.parent)
    with tempfile.NamedTemporaryFile(mode='wb', dir=str(path.parent), delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    os.chmod(str(temporary), 0o600)
    os.replace(str(temporary), str(path))
    return path


def _read_record(path, label):
    if path.is_symlink():
        raise LifecycleError(label + ' may not be a symlink')
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise LifecycleError(label + ' must be a regular single-link file')
    if not path.exists():
        return None
    if path.stat().st_size > MAX_STATE_BYTES:
        raise LifecycleError(label + ' exceeded its bounded size')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise LifecycleError('Malformed ' + label + ': ' + str(exc))
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA_VERSION:
        raise LifecycleError('Malformed ' + label)
    return value


def _host_folder(root, host):
    return w.safe_path(root, STATE_RELATIVE + '/' + host, internal=True)


def _install_path(root, host):
    return _host_folder(root, host) / 'install.json'


def _events_path(root, host):
    return _host_folder(root, host) / 'events.jsonl'


def load_install(root, host):
    return _read_record(_install_path(root, host), 'Native lifecycle install record')


def _save_install(root, host, record):
    return _write_private(_install_path(root, host),
                          json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + '\n')


# ---------------------------------------------------------------------------- identity


def bound_identity(root, project_id):
    """Bind the one canonical root and require both identities.

    A relative path, the trusted runtime, a missing root, a non-kebab-case project ID, or a
    project ID that disagrees with the local binding is refused. Identity is never inferred from
    a folder name, a remote URL, Git or a prior conversation, and this never bootstraps a project.
    """
    root = pb.project_root(root)
    if not isinstance(project_id, str) or not pb.PROJECT_ID.fullmatch(project_id):
        raise LifecycleError('Explicit lowercase kebab-case --project-id is required')
    binding = pb.load_binding(root)
    if binding['project_id'] != project_id:
        raise LifecycleError('Explicit project ID does not match the local binding; identity is never '
                             'inferred from a folder, a remote URL, Git or a prior conversation')
    return root, binding


def normalize_version(raw):
    """The host's own version string, reduced to its dotted release identity."""
    match = re.search(r'(\d+\.\d+\.\d+)', str(raw or ''))
    return match.group(1) if match else None


def supported(host, raw):
    version = normalize_version(raw)
    if version is None:
        raise LifecycleError('Host version is unknown; a callback from an unidentified host is refused')
    if version not in SUPPORTED_VERSIONS[host]:
        raise LifecycleError('Unsupported ' + host + ' host version ' + version + '; the adapter was '
                             'probed on ' + ' and '.join(SUPPORTED_VERSIONS[host])
                             + ' only and is never extrapolated to another release')
    return version


def physical_equal(root, value):
    """Compare a host-reported working directory to the bound root by identity, not by spelling."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        candidate = Path(value).resolve()
    except OSError:
        return False
    if candidate == root:
        return True
    left = w.physical_identity(candidate)
    right = w.physical_identity(root)
    return left is not None and left == right


def task_scope(host, root, binding, payload_sha, session_id, turn_id=None, epoch=0):
    """The deterministic scope hashes for one host session and for one turn inside it.

    Both digests bind the actual host, canonical root, checkout, installed payload digest and
    session, so the same session is re-enterable after an interruption or a retry, while a
    different host, checkout, configuration or session can never collide with it. The session
    identity is the context task, because a project holds one reservation and one frozen
    generation per session; the turn identity is recorded alongside it, so every callback is
    still bound to the exact turn that produced it.

    `epoch` is the one number a completed session task moves forward by. It is zero for every
    ordinary scope, so the deterministic shape above is unchanged; it exists because a finished
    task cannot hold another turn, and the next real scope of the same session has to differ from
    it without inventing a task ID out of nothing.
    """
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 200:
        raise LifecycleError('Host callback needs an explicit real session_id')
    if turn_id is not None and (not isinstance(turn_id, str) or not turn_id.strip()
                                or len(turn_id) > 200):
        raise LifecycleError('Host callback turn_id must be explicit nonempty text')
    if not isinstance(epoch, int) or isinstance(epoch, bool) or not 0 <= epoch < MAX_SCOPE_EPOCHS:
        raise LifecycleError('Host callback scope epoch is out of range')

    def scope(with_turn):
        return canonical({'host': host, 'project_root': str(root), 'project_id': binding['project_id'],
                          'checkout_id': binding['checkout_id'], 'payload_sha256': payload_sha,
                          'session_id': session_id, 'turn_id': with_turn, 'scope_epoch': epoch})

    session = digest(scope(None))
    return {'task_id': 'host-' + host + '-' + session[:16],
            'turn_task_id': 'host-' + host + '-' + digest(scope(turn_id))[:16] if turn_id else None,
            'session_task_id': 'host-' + host + '-' + session[:16],
            'scope_sha256': digest(scope(turn_id)) if turn_id else session,
            'session_sha256': session, 'scope_epoch': epoch}


def active_scope(host, root, binding, record, session_id, turn_id):
    """The task scope that is actually live for this session, resolved from recorded task state.

    Every active turn of one session is one task, so an ordinary callback keeps re-entering the same
    scope and nothing changes for a project whose task is still running. A finished task cannot hold
    another turn: `project_binding.enter` returns a completed task unchanged and reuses its frozen
    generation, and a cancelled task keeps the history of the work that was cancelled. Either way
    the next turn of the same host session is new work, so it gets the next real scope of the same
    session and a fresh generation, and it borrows neither the old task's completion nor its
    verification. Epochs are counted from the recorded tasks themselves, never invented, and the
    walk is bounded.
    """
    scope = task_scope(host, root, binding, record['payload_sha256'], session_id, turn_id)
    for epoch in range(1, MAX_SCOPE_EPOCHS):
        state = pb.task_state(root, scope['task_id'])
        if not state or state.get('status') not in CLOSED_SCOPE_STATES:
            return scope
        scope = task_scope(host, root, binding, record['payload_sha256'], session_id, turn_id, epoch)
    raise LifecycleError('Host session ' + str(session_id) + ' has exhausted its bounded task scopes; '
                         'a finished task is never resurrected and no scope is invented')


# ---------------------------------------------------------------------------- ownership


def root_holder(root):
    """Whoever already owns this root. A native adapter never steals a reservation."""
    holder = None
    try:
        record = _read_record(w.safe_path(root, COORDINATOR_RESERVATION, internal=True),
                              'Coordinator reservation')
    except ValueError:
        holder = 'an unreadable coordinator reservation'
    if record is not None:
        holder = 'coordinator batch ' + str(record.get('batch'))
    try:
        pending = w.active_workflow(root)
    except ValueError as exc:
        return {'holder': holder or ('an invalid managed workflow reservation: ' + str(exc))}
    if pending:
        holder = holder or ('managed workflow ' + pending['workflow'])
    native = pb.reservation(root)
    if native:
        holder = holder or ('native context task ' + native['task_id'])
    return {'holder': holder, 'coordinator': record, 'workflow': pending, 'context_task': native}


def require_free_root(root, task_id=None):
    """Refuse an install or a callback against a root another writer already reserved."""
    state = root_holder(root)
    holder = state['holder']
    if holder and task_id and holder.endswith(' ' + task_id):
        return state
    if holder:
        raise LifecycleError('Project root is already owned by ' + holder
                             + '; the native adapter never steals a reservation')
    return state


# ---------------------------------------------------------------------------- templates


def _template_bytes(host):
    """The shipped payload, read from the trusted distribution and never from the project."""
    relative = _spec(host)['template']
    path = resources.resolve(relative)
    if not path.is_file():
        raise LifecycleError('Shipped ' + host + ' adapter template is missing from this installation: '
                             + relative + '; a project may never supply its own')
    return path.read_bytes(), relative


def bridge_command(root, project_id, host, payload_sha):
    return (shlex.quote(sys.executable or 'python3') + ' ' + shlex.quote(str(Path(__file__).resolve()))
            + ' event --project ' + shlex.quote(str(root)) + ' --project-id '
            + shlex.quote(str(project_id)) + ' --host ' + shlex.quote(str(host))
            + ' --config-sha ' + shlex.quote(payload_sha))


def _values(root, project_id, host, payload_sha):
    # The plugin appends its own `event` subcommand and flags, so this argv stops at the module.
    return {'__CREWLOOM_BRIDGE_COMMAND__': bridge_command(root, project_id, host, payload_sha),
            '__CREWLOOM_BRIDGE_ARGV__': canonical([sys.executable or 'python3',
                                                   str(Path(__file__).resolve())]),
            '__CREWLOOM_ROOT__': canonical(str(root)),
            '__CREWLOOM_PROJECT_ID__': canonical(str(project_id)),
            '__CREWLOOM_CONFIG_SHA__': canonical(payload_sha),
            '__CREWLOOM_HOST__': canonical(str(host))}


def _render(host, root, project_id, payload_sha):
    source, relative = _template_bytes(host)
    text = source.decode('utf-8')
    for key, value in _values(root, project_id, host, payload_sha).items():
        text = text.replace(key, value)
    if '__CREWLOOM_' in text:
        raise LifecycleError('Unresolved placeholder in the shipped ' + relative + ' template')
    return text.encode('utf-8'), relative


def payload_digest(host, root, project_id):
    """The digest the installed hooks and plugin pass back to this engine.

    It is computed over the payload rendered with a normalized digest field, so it never depends
    on itself. A configuration copied from another project hashes differently and is refused; a
    changed adapter template changes it too, which is how a corrupted installation is caught.
    """
    rendered, _ = _render(host, root, project_id, NORMALIZED_SHA)
    return digest(rendered)


def verify_payload(host, root, project_id, expected):
    """Re-render the trusted template and refuse a callback whose installed payload drifted."""
    if payload_digest(host, root, project_id) != expected:
        raise LifecycleError('Installed adapter payload digest does not match the trusted template; '
                             'the installation is altered or copied from another project')


def _writable(root, relative):
    """The shared metadata path checks, reported as one lifecycle refusal rather than a bare error."""
    try:
        return pb.writable(root, relative)
    except ValueError as exc:
        raise LifecycleError(str(exc))


def _no_links(root, relative):
    try:
        return pb.no_links(root, relative)
    except ValueError as exc:
        raise LifecycleError(str(exc))


def _existing_control(root, relative):
    """The project's existing control config, or an empty one. Foreign entries are never dropped."""
    target = _no_links(root, relative)
    if not target.exists():
        return {}
    if target.stat().st_nlink != 1:
        raise LifecycleError('Host control config must be a regular single-link file: ' + relative)
    try:
        value = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise LifecycleError('Malformed existing host control config ' + relative + ': ' + str(exc))
    if not isinstance(value, dict):
        raise LifecycleError('Host control config must be a JSON object: ' + relative)
    return value


def _is_owned_group(group, command):
    for hook in (group or {}).get('hooks', []):
        if hook.get('command') == command:
            return True
    return False


def _merge_control(existing, owned):
    """Merge owned hook entries per event, replacing only entries this installer owns.

    Nothing else in the document is touched. A foreign tool's own `owner`, `schema_version`,
    extensions and hooks survive an install byte for byte, because rewriting them would let an
    install silently reconfigure whatever else already shares this file.
    """
    merged = dict(existing)
    hooks = dict(existing.get('hooks') or {})
    command = _command_of(owned)
    for event, entries in owned.items():
        kept = [group for group in hooks.get(event, []) if not _is_owned_group(group, command)]
        hooks[event] = kept + [dict(group) for group in entries]
    merged['hooks'] = hooks
    return (json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def _command_of(owned):
    for groups in owned.values():
        for group in groups:
            for hook in group.get('hooks', []):
                return hook.get('command')
    return None


def _owned_entries(document, host, limit):
    """The exact owned hook entries, one group per lifecycle event, with the context limit set."""
    owned = {}
    limit_key = _spec(host)['context_limit_key']
    for event, groups in document['hooks'].items():
        owned[event] = []
        for group in groups:
            copied = {'matcher': group.get('matcher', '*'),
                      'hooks': [dict(hook) for hook in group.get('hooks', [])]}
            if limit_key:
                for hook in copied['hooks']:
                    hook[limit_key] = limit
            owned[event].append(copied)
    return owned


def declared_output_keys(outputs):
    """Folded destination keys, refusing two declared outputs that are one file."""
    keys = {}
    for name in outputs:
        key = w.path_key(name)
        if key in keys:
            raise LifecycleError('Declared outputs collapse to one destination: ' + str(name))
        keys[key] = name
    return keys


# ---------------------------------------------------------------------------- acceptance contract

# The acceptance contract is the authority a native task is measured against. Its criteria, its plan
# and the checkers and helpers its configured workflow consumes decide whether the work was correct
# at all, so they are pinned by content at install time and a later callback can tell an unchanged
# contract from an edited one. The criteria and the plan are authority whatever else was declared:
# naming one of them a seed or a source is a classification mistake, not a licence to relax it.
# The scope of the freeze is the whole configured workflow rather than the one step this
# installation runs, because the earlier steps authored the checkers and helpers that step consumes,
# so pinning only the selected step leaves exactly the files that decide the outcome editable.
# The source under test is the opposite: the seeds and sources this install was frozen against are
# what the task exists to change, so pinning one of them would refuse the very edit the task was
# asked to make. Neither are the files the workflow itself produces between its steps: the managed
# executor revalidates each one against the producer ledger when it runs, and they do not exist yet
# at install time. Nothing else is invented as immutable, so an ordinary project file outside the
# configured workflow keeps whatever legitimate edit the task makes to it.


def _candidate_keys(seeds, sources):
    """The folded paths of the source under test: what this task is meant to change."""
    return {w.path_key(str(name)) for name in list(seeds) + list(sources) if name}


def _generated_keys(plan):
    """The folded paths this configured workflow produces itself, between its own steps.

    A step's own output is generated by the run, not authored before it, so it is never pinned as
    contract input and never refused as a declared output. The managed executor records the hash
    each producing step wrote and revalidates every declared output against that ledger, so these
    files are checked where they actually change instead of where they do not yet exist.
    """
    return {w.path_key(str(name)) for item in (plan or {}).get('steps') or []
            for name in item.get('outputs') or [] if name}


def acceptance_contract(criteria_path, acceptance_record, plan=None, seeds=(), sources=()):
    """The exact authority files this installation's acceptance contract depends on.

    Two kinds of entry, and they are never exchanged. The authority is the criteria this install
    names, the plan itself and the criteria the plan itself declares; it is registered whatever the
    seeds and sources say, because a declared output that reaches any of them is refused below
    before a single write. The authored inputs are every declared step input of the *whole*
    configured workflow, which is where the checkers and helpers arrive from and not only from the
    step this installation runs. From those the source under test and the workflow's own generated
    files are left out, so a real candidate edit stays legal and an intermediary artifact stays
    reviewable by the producer ledger.

    Duplicate spellings collapse to one entry and the order is the recorded order rather than a
    sorted guess, so an unchanged contract produces an unchanged record.
    """
    authority = []
    authored = []
    mutable = _candidate_keys(seeds, sources) | _generated_keys(plan)
    if criteria_path:
        authority.append(str(criteria_path))
    if acceptance_record:
        authority.append(str(acceptance_record['workflow']))
        if plan and plan.get('criteria'):
            authority.append(str(plan['criteria']))
        for item in (plan or {}).get('steps') or []:
            authored.extend(str(name) for name in item.get('inputs') or [] if name)
    ordered = {}
    for name in authority:
        ordered.setdefault(w.path_key(name), name)
    for name in authored:
        key = w.path_key(name)
        if key not in mutable:
            ordered.setdefault(key, name)
    return ordered



def _reaches(root, name, other):
    """Whether one project path reaches another by folded name or by real filesystem identity.

    The folded key answers the spellings that compare as one name, and the device and inode answer
    the rest: on a case-insensitive filesystem `Criteria.md` and `criteria.md` stay different
    strings for one file, and a declared `out/../criteria.md` resolves to the pinned file without
    ever naming it. Nothing is probed and no host setting is read, so the answer is the same on a
    developer Mac, in CI and in a container.
    """
    if w.path_key(name) == w.path_key(other):
        return True
    try:
        left = w.physical_identity(w.safe_path(root, name))
        right = w.physical_identity(w.safe_path(root, other))
    except ValueError:
        return False
    return left is not None and left == right


def refuse_contract_outputs(root, outputs, contract):
    """Refuse any declared output that names or physically reaches pinned acceptance authority."""
    for name in outputs:
        for pinned in contract.values():
            if _reaches(root, name, pinned):
                raise LifecycleError('The acceptance contract is immutable authority and is never a '
                                     'declared output: ' + str(name) + ' reaches ' + pinned
                                     + '. Refusing before any write; a reviewed contract change needs '
                                       'a new installation, never an adopted edit.')


def pinned_acceptance_inputs(root, contract):
    """The authority files with the exact digest each one had when this installation recorded them.

    A missing or linked authority file is a refusal here rather than a surprise at verification time:
    an installation that cannot see the contract it depends on must not record one it could never
    check. The candidate is already gone from `contract` by the time it arrives here, which is what
    keeps a real candidate edit legal while its checkers stay pinned.
    """
    pinned = []
    for key, name in sorted(contract.items()):
        path = _writable(root, name)
        if not path.is_file():
            raise LifecycleError('Acceptance contract input is missing: ' + name)
        pinned.append({'path': name, 'sha256': digest(path.read_bytes())})
    return pinned


def acceptance_drift(root, record):
    """The pinned contract files this installation can no longer prove, in recorded order.

    A file that is gone, reached through a link or changed is reported the same way, because an
    absent authority cannot run acceptance either. This compares content against the contract this
    installation recorded; the runtime owner can still mutate a file between this check and the
    executor reading it, so it is contract validation and not an OS sandbox or a race-free lock.
    """
    drifted = []
    for item in (record or {}).get('acceptance_inputs') or []:
        try:
            path = _writable(root, item['path'])
            intact = path.is_file() and digest(path.read_bytes()) == item['sha256']
        except (LifecycleError, OSError):
            intact = False
        if not intact:
            drifted.append(item['path'])
    return drifted


def require_acceptance_contract(root, record):
    """Refuse an altered acceptance contract instead of adopting the changed bytes."""
    drifted = acceptance_drift(root, record)
    if drifted:
        raise LifecycleError('The installed acceptance contract was altered after install ('
                             + ', '.join(drifted[:8]) + '); a reviewed reinstall is required and the '
                             'changed bytes are never adopted as this installation\'s contract')
    return True


# ---------------------------------------------------------------------------- install


def install(root, project_id, host, role, criteria_path=None, seeds=(), sources=(),
            declared_outputs=(), acceptance=None, managed_commands=(), context_limit=ADDITIONAL_CONTEXT_LIMIT,
            host_version=None):
    """Install one host's owned payloads and metadata on an explicitly identified root.

    Everything below is validated before a single write: the canonical root, both identities,
    the host version, the declared output set, the role, the acceptance plan, the immutable
    acceptance contract, and who currently owns the root. The control configuration is merged
    rather than replaced, so unrelated hooks, settings and plugins survive an install untouched.
    """
    spec = _spec(host)
    root, binding = bound_identity(root, project_id)
    version = supported(host, host_version or _version_of(host) or os.environ.get('CREWLOOM_HOST_VERSION'))
    if not pb.PROJECT_ID.fullmatch(str(role or '')):
        raise LifecycleError('Explicit kebab-case --role is required; a role is never guessed')
    installed_role = w.project_role(root, role)
    if not installed_role.get('ready'):
        raise LifecycleError('Role is not installed in this project: ' + str(role) + ' ('
                             + str(installed_role.get('error')) + '); install the role before the adapter')
    outputs = [str(name) for name in declared_outputs]
    if not outputs:
        raise LifecycleError('Explicit declared output files are required; an unguarded task has no boundary')
    keys = declared_output_keys(outputs)
    if criteria_path:
        if not _writable(root, criteria_path).is_file():
            raise LifecycleError('Acceptance criteria file is missing: ' + str(criteria_path))
    for name in list(seeds) + list(sources):
        if not w.safe_path(root, name).is_file():
            raise LifecycleError('Declared seed or source is missing: ' + str(name))
    commands = []
    for item in managed_commands:
        argv = item.get('argv') if isinstance(item, dict) else None
        cwd = item.get('cwd', '.') if isinstance(item, dict) else '.'
        if not isinstance(argv, list) or not argv or any(not isinstance(part, str) for part in argv):
            raise LifecycleError('A managed command needs an exact argv list')
        if cwd != '.':
            raise LifecycleError('A managed command must declare the canonical project root as its cwd')
        commands.append({'argv': list(argv), 'cwd': '.'})
    if len(commands) > MAX_MANAGED_COMMANDS:
        raise LifecycleError('Too many managed commands; the managed allowlist is bounded')
    acceptance_record = None
    contract_plan = None
    if acceptance:
        plan_relative = str(acceptance.get('workflow') or '')
        if not w.safe_path(root, plan_relative).is_file():
            raise LifecycleError('Configured acceptance workflow is missing: ' + plan_relative)
        plan, _ = w.read_plan(root, plan_relative)
        step = acceptance.get('step')
        if not any(item['id'] == step for item in plan['steps']):
            raise LifecycleError('Configured acceptance step is not in workflow ' + plan['id']
                                 + ': ' + str(step))
        acceptance_record = {'workflow': plan_relative, 'workflow_id': plan['id'], 'step': step,
                             'image': str(acceptance.get('image') or w.DEFAULT_IMAGE)}
        contract_plan = plan
    # Everything below is still before the first write: the immutable acceptance contract is resolved,
    # refused against the declared outputs, and pinned by content, so an invalid contract can never
    # half-install this host. The whole configured workflow is frozen, not only the step this install
    # runs, and the source under test leaves the contract first: a declared output that is also the
    # candidate is still a legal destination, while the criteria and the plan never leave it.
    contract = acceptance_contract(criteria_path, acceptance_record, contract_plan, seeds, sources)
    refuse_contract_outputs(root, outputs, contract)
    acceptance_inputs = pinned_acceptance_inputs(root, contract)

    relative = spec['control']
    payload_sha = payload_digest(host, root, project_id)
    rendered, template_relative = _render(host, root, project_id, payload_sha)
    if host == 'opencode':
        body = rendered
    else:
        document = json.loads(rendered.decode('utf-8'))
        body = _merge_control(_existing_control(root, relative),
                              _owned_entries(document, host, context_limit))
    command = bridge_command(root, project_id, host, payload_sha)

    with w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True):
        require_free_root(root)
        pb.preflight(root, [relative])
        target = _writable(root, relative)
        if target.exists() and host not in MERGEABLE_HOSTS and load_install(root, host) is None:
            # A plugin file cannot be merged. Nothing in this project's record owns that file, so
            # writing it would replace somebody else's plugin outright. This is a refusal.
            raise LifecycleError('A host control file already exists and is not owned by this '
                                 'installer: ' + relative + '; it is preserved unchanged')
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_private(target, body, limit=MAX_TEXT)
        marker = digest(canonical({'root': str(root), 'project_id': project_id,
                                   'checkout_id': binding['checkout_id'], 'host': host,
                                   'version': version, 'payload': payload_sha}))[:24]
        record = {'schema_version': SCHEMA_VERSION, 'owner': OWNER, 'project_id': project_id,
                  'checkout_id': binding['checkout_id'], 'project_root': str(root), 'host': host,
                  'host_version': version, 'supported_versions': list(SUPPORTED_VERSIONS[host]),
                  'template': template_relative, 'control_relative': relative,
                  'bridge_command': command,
                  'payload_sha256': payload_sha,
                  'role': role, 'criteria_path': criteria_path,
                  'seeds': [str(item) for item in seeds], 'sources': [str(item) for item in sources],
                  'declared_outputs': outputs, 'declared_output_keys': sorted(keys),
                  'managed_commands': commands, 'acceptance': acceptance_record,
                  'acceptance_inputs': acceptance_inputs,
                  'verification_workflow': acceptance_record['workflow_id'] if acceptance_record else None,
                  'callback_caps': {'stages': spec['stages'], 'guard_tools': list(spec['guard_tools']),
                                    'code_mode_host_required': spec['code_mode_host_required'],
                                    'context_limit': context_limit},
                  'launcher': spec['launcher'], 'delivery': spec['delivery'],
                  'trust': 'needs-project-trust' if spec['delivery'] == 'needs-project-trust'
                           else 'project-local',
                  'additional_context_limit': context_limit,
                  'installed_content_sha256': {relative: digest(body)},
                  'control_config_sha256': digest(body),
                  'owned_entries': ({event: entries for event, entries
                                     in _owned_entries(json.loads(rendered.decode('utf-8')),
                                                       host, context_limit).items()}
                                    if host != 'opencode' else None),
                  'marker': marker, 'installed_at': now()}
        # One installation is identified by its whole contract, not by its payload template alone.
        # The payload digest covers the rendered hook entries, which do not change when the declared
        # outputs, the role, the criteria or the configured acceptance change, so it cannot tell one
        # revision of this installation from the next. Every recorded callback is bound to this ID,
        # and a later install that changes any part of the contract is a new installation that has
        # inherited no observation, no delivery and no verification from the previous one. The
        # install timestamp is the one field deliberately left out: reinstalling an unchanged
        # contract is the same installation.
        contract = {key: value for key, value in record.items() if key != 'installed_at'}
        record['install_id'] = digest(canonical(contract))[:32]
        _save_install(root, host, record)
        _append_event(root, host, {'stage': 'install', 'native_event': None, 'at': record['installed_at'],
                                   'verified': False, 'install_id': record['install_id'],
                                   'detail': 'rendered ' + template_relative
                                   + ' into ' + relative})
    result = dict(record)
    result['state'] = 'installed'
    return result


# ---------------------------------------------------------------------------- uninstall


def uninstall(root, project_id, host):
    """Remove only unchanged owned items. An altered owned file is reported and preserved."""
    root, binding = bound_identity(root, project_id)
    record = load_install(root, host)
    if record is None:
        raise LifecycleError('No native lifecycle installation for ' + host)
    if record['project_id'] != project_id or record['checkout_id'] != binding['checkout_id']:
        raise LifecycleError('Native lifecycle installation belongs to another project or checkout')
    verify_payload(host, root, project_id, record['payload_sha256'])
    relative = record['control_relative']
    conflicts = []
    removed = []
    with w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True):
        target = _no_links(root, relative)
        if not target.exists():
            conflicts.append('owned control config is already absent: ' + relative)
        elif host == 'opencode':
            if digest(target.read_bytes()) != record['installed_content_sha256'][relative]:
                conflicts.append('owned plugin was altered since install and is preserved for review: '
                                 + relative)
            else:
                target.unlink()
                removed.append(relative)
        else:
            try:
                current = json.loads(target.read_text(encoding='utf-8'))
            except (OSError, ValueError) as exc:
                conflicts.append('owned control config became unreadable and is preserved: ' + str(exc))
                current = None
            if isinstance(current, dict):
                hooks = dict(current.get('hooks') or {})
                altered = False
                for event, groups in list(hooks.items()):
                    for group in groups or []:
                        for hook in group.get('hooks', []):
                            if hook.get('command') == record['bridge_command']:
                                continue
                            if isinstance(hook.get('command'), str) \
                                    and _addresses_bridge(hook['command'], project_id):
                                altered = True
                    hooks[event] = [group for group in groups or []
                                   if not _is_owned_group(group, record['bridge_command'])]
                if altered:
                    conflicts.append('an owned hook entry was altered since install and is preserved')
                else:
                    if not any(hooks.values()):
                        current.pop('hooks', None)
                    else:
                        current['hooks'] = hooks
                    target.write_bytes((json.dumps(current, ensure_ascii=False, indent=2,
                                                   sort_keys=True) + '\n').encode('utf-8'))
                    removed.append(relative)
        folder = _host_folder(root, host)
        if not conflicts and folder.is_dir():
            for name in sorted(folder.iterdir()):
                if name.is_file():
                    name.unlink()
            try:
                folder.rmdir()
            except OSError:
                pass
    return {'host': host, 'project_id': project_id, 'project_root': str(root), 'removed': removed,
            'conflicts': conflicts, 'state': 'removed' if not conflicts else 'conflict',
            'note': 'Uninstall removes only items this installer still owns byte for byte; every '
                    'foreign hook, setting and plugin is preserved'}


def _addresses_bridge(command, project_id):
    """Whether a hook command addresses this project's bridge, however it was altered."""
    return str(Path(__file__).resolve()) in command and str(project_id) in command


# ---------------------------------------------------------------------------- status


def status(root, project_id=None, host=None):
    """Report installed, delivered, observed and verified separately, never as one answer."""
    root = pb.project_root(root)
    binding = pb.load_binding(root, required=False)
    if project_id and binding and binding['project_id'] != project_id:
        raise LifecycleError('Explicit project ID does not match the local binding')
    names = [host] if host else list(HOSTS)
    reports = [_host_status(root, name, load_install(root, name) if name in HOSTS else None, binding)
               for name in names]
    return reports[0] if host else {'project_root': str(root), 'hosts': reports}


def current_events(record, events):
    """Only the recorded events that belong to this exact installation.

    A callback proves what it proved for the contract it arrived under. An event recorded under an
    earlier install ID describes a different declared output set, role, criteria or acceptance
    configuration, so it is history rather than evidence about the installation in front of us.
    An event with no ID at all came from an older engine that did not scope its callbacks, and it
    is equally unable to prove anything about this installation.
    """
    install_id = (record or {}).get('install_id')
    if not install_id:
        return []
    return [item for item in events if item.get('install_id') == install_id]


def _host_status(root, host, record, binding):
    spec = _spec(host)
    relative = record['control_relative'] if record else spec['control']
    content_ok = False
    control_sha = None
    target = _no_links(root, relative) if record else None
    if target is not None and target.is_file() and target.stat().st_nlink == 1:
        control_sha = digest(target.read_bytes())
        if host == 'opencode':
            content_ok = control_sha == record['installed_content_sha256'][relative]
        else:
            try:
                document = json.loads(target.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                document = None
            if isinstance(document, dict):
                content_ok = any(_is_owned_group(group, record['bridge_command'])
                                 for groups in (document.get('hooks') or {}).values()
                                 for group in groups or [])
    history = observed_events(root, host) if record else []
    events = current_events(record, history)
    callbacks = sorted({item['native_event'] for item in events if item.get('native_event')})
    verified = any(item.get('stage') == 'verify' and item.get('verified') for item in events)
    # Delivery is an observed callback, never a file on disk. An installed plugin or hook config
    # proves the host was *given* the configuration; only this installation actually returning a
    # successful injection proves it received context from it.
    delivered = any(item.get('stage') == 'inject' and item.get('injected') for item in events)
    # The installed acceptance contract is a separate fact from the installed hook payload. An
    # intact hook config beside altered criteria is the dangerous pair, because the host would keep
    # delivering context against a contract this installation can no longer prove, so the two are
    # reported separately instead of collapsing into one `altered` label.
    drifted = acceptance_drift(root, record) if record else []
    contract_intact = bool(record is not None and record.get('acceptance_inputs')
                           and not drifted)
    installed = record is not None
    if not installed:
        label = 'not-installed'
    elif not content_ok:
        label = 'altered'
    elif verified:
        label = 'verified-executor'
    elif callbacks:
        label = 'observed'
    elif record['delivery'] == 'project-plugin':
        label = 'config-ready'
    else:
        label = 'needs-trust'
    return {'host': host, 'project_id': (record or binding or {}).get('project_id'),
            'checkout_id': (record or binding or {}).get('checkout_id'), 'project_root': str(root),
            'lifecycle': label, 'installed': installed, 'content_intact': content_ok,
            'install_id': (record or {}).get('install_id'),
            'acceptance_contract_intact': contract_intact,
            'acceptance_contract_altered': bool(drifted),
            'altered_acceptance_inputs': drifted,
            'config_ready': bool(installed and content_ok),
            'needs_trust': bool(installed and content_ok
                                and record['delivery'] == 'needs-project-trust'),
            'delivered': bool(installed and content_ok and delivered),
            'observed_events': callbacks, 'observed_callbacks': len(callbacks),
            'unattributed_events': len(history) - len(events),
            'verified_executor': verified, 'host_version': record['host_version'] if record else None,
            'supported_versions': list(SUPPORTED_VERSIONS[host]),
            'control_relative': relative, 'control_config_sha256': control_sha,
            'payload_sha256': record['payload_sha256'] if record else None,
            'installed_content_sha256': record['installed_content_sha256'] if record else None,
            'bridge_command': record['bridge_command'] if record else None,
            'delivery': record['delivery'] if record else spec['delivery'],
            'launcher': record['launcher'] if record else None,
            'callback_caps': record['callback_caps'] if record else None,
            'acceptance': record['acceptance'] if record else None,
            'verification_workflow': record['verification_workflow'] if record else None,
            'declared_outputs': record['declared_outputs'] if record else [],
            'additional_context_limit': record['additional_context_limit'] if record else None,
            'limits': list(LIMITS)}


def observed_events(root, host, limit=MAX_EVENTS):
    path = _events_path(root, host)
    if not path.is_file():
        return []
    if path.is_symlink():
        raise LifecycleError('Native lifecycle event log may not be a symlink')
    events = []
    for line in path.read_text(encoding='utf-8').splitlines()[-limit:]:
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _stored_event(event):
    """The event as the bounded project log keeps it.

    An injected context body is a response payload, not metadata. It is returned to the host on the
    callback that produced it and never written into `.crewloom`, so repeated turns of one session
    cannot accumulate whole copies of a project's declared sources and rules in its own metadata.
    The digests, the byte count and the omission record stay, because they are what the log is for.
    """
    if 'additionalContext' not in event:
        return event
    stored = {key: value for key, value in event.items() if key != 'additionalContext'}
    stored['additionalContext_not_logged'] = True
    return stored


def _append_event(root, host, event):
    """Append one complete event, keeping the log inside its byte and record budget.

    The budget is enforced on bytes rather than on a count, because the sizes are not uniform. When
    the log is full the oldest complete records are dropped and the newest are kept whole: a record
    is never truncated, so every retained line still parses and the latest event is always there.
    """
    path = _events_path(root, host)
    if path.is_symlink():
        raise LifecycleError('Native lifecycle event log may not be a symlink')
    line = canonical(_stored_event(event)) + '\n'
    body = line.encode('utf-8')
    history = path.read_text(encoding='utf-8').splitlines() if path.is_file() else []
    kept = []
    total = len(body)
    for previous in reversed(history):
        if len(kept) >= MAX_EVENTS or total + len(previous.encode('utf-8')) + 1 > MAX_STATE_BYTES:
            break
        kept.append(previous)
        total += len(previous.encode('utf-8')) + 1
    _write_private(path, ''.join(item + '\n' for item in reversed(kept)) + line)
    return event


# ---------------------------------------------------------------------------- guard


PATCH_BEGIN = '*** Begin Patch'
PATCH_END = '*** End Patch'
RECORD = re.compile(r'^\*\*\* (Add|Update|Delete) File: (.+?)\s*$')
MOVE = re.compile(r'^\*\*\* Move to: (.+?)\s*$')
COMPOUND = ('&&', '||', ';', '>', '<', '|', '`', '$(', '\n', '&', '*', '?', '~', '!', '#')

# The tools this engine manages, in the spelling each host's own schema uses. Only the guard's
# strict decision depends on this split; a checkpoint recognizes the same tools so it can read the
# same arguments back out of the host's real post-tool payload.
PATCH_TOOLS = ('apply_patch', 'patch')
FILE_TOOLS = ('write', 'edit', 'MultiEdit', 'NotebookEdit', 'Edit', 'Write')
SHELL_TOOLS = ('shell', 'Bash', 'bash')

# The key names the three hosts really use for one tool call. Codex 0.155.1 and Claude 2.1.150
# deliver `tool_name` beside `tool_input` on both PreToolUse and PostToolUse; the OpenCode plugin
# delivers `tool` beside `args`, which is also the normalized shape this engine's own API accepts
# from an in-process caller. Both spellings are read, because the schema probe recorded the native
# one and a normalized unit payload hid the difference.
NATIVE_TOOL_KEYS = ('tool_name', 'tool')
NATIVE_ARGUMENT_KEYS = ('tool_input', 'args')

# The one real target of a known file tool. The host's own schema decides the spelling: OpenCode
# writes `filePath`, Claude Code writes `file_path`, and a bare `path` is accepted too. Only the key
# varies; the destination still goes through the unchanged endpoint boundary.
FILE_TARGET_KEYS = ('filePath', 'file_path', 'path', 'notebook_path')

# An explicit declared-change list is still accepted when a caller really supplies one, so the
# normalized API keeps the exact behaviour it had. It is never merged with derived endpoints: two
# descriptions of the same write either agree or one of them is wrong, and this engine picks none.
EXPLICIT_CHANGE_KEYS = ('changed_paths', 'paths')


def _agreed(payload, keys, label):
    """One value under whichever of these real key names the host used, or a refusal.

    Both spellings may legitimately appear in one document, but only when they describe the same
    call. Two values that differ are a contradiction, not a preference: deciding on whichever field
    happened to be read first is how a renamed tool or a swapped argument object gets treated as
    the call the host actually asked for.
    """
    found = [payload[key] for key in keys if payload.get(key) is not None]
    if not found:
        return None
    for value in found[1:]:
        if canonical(value) != canonical(found[0]):
            raise LifecycleError('Host callback carries contradictory ' + label + ' fields; '
                                 + ' and '.join(keys) + ' must describe the same one call')
    return found[0]


def native_call(payload):
    """The exact native tool name and argument object one host callback delivered.

    The name is ``None`` when the host reported no tool call at all, which is a normal payload for
    every event that is not about a tool. A name or an argument object that is present but unusable
    is refused here, so no stage downstream has to decide what an unreadable payload meant.
    """
    tool = _agreed(payload, NATIVE_TOOL_KEYS, 'native tool name')
    arguments = _agreed(payload, NATIVE_ARGUMENT_KEYS, 'native tool arguments')
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise LifecycleError('A host callback needs its native tool arguments as an object')
    if tool is not None and (not isinstance(tool, str) or not tool):
        raise LifecycleError('A host callback tool name is not a real tool name')
    return tool, arguments


def patch_payload(args):
    """The real patch text of a known patch tool, under either key a host's schema uses."""
    text = args.get('patchText')
    if not isinstance(text, str):
        text = args.get('command')
    if not isinstance(text, str):
        raise LifecycleError('Known patch tool needs its real patchText payload')
    return text


def file_target(args):
    """The one real target of a known file tool, under whichever key this host's schema uses."""
    found = [args[key] for key in FILE_TARGET_KEYS if args.get(key)]
    if not found:
        raise LifecycleError('Known file tool needs its target path')
    for value in found[1:]:
        if canonical(value) != canonical(found[0]):
            raise LifecycleError('Known file tool declares contradictory target paths: '
                                 + ', '.join(FILE_TARGET_KEYS))
    if not isinstance(found[0], str) or not found[0].strip():
        raise LifecycleError('Known file tool needs its target path')
    return found[0]


def patch_records(text):
    """Every file endpoint in an apply_patch payload, including both ends of every move.

    A patch that edits a permitted file and moves it somewhere forbidden is the obvious escape,
    so a move destination is validated with exactly the same rules as its source. All records are
    returned before any of them is allowed, so a forbidden endpoint late in the payload is caught
    before the first permitted one is trusted.
    """
    if not isinstance(text, str) or not text.strip():
        raise LifecycleError('Patch payload must be nonempty text')
    if len(text) > MAX_TEXT:
        raise LifecycleError('Patch payload exceeded its bounded size')
    if text.strip().splitlines()[0].strip() != PATCH_BEGIN or PATCH_END not in text:
        raise LifecycleError('Patch payload must be framed by ' + PATCH_BEGIN + ' and ' + PATCH_END)
    records = []
    current = None
    for line in text.splitlines():
        found = RECORD.match(line)
        if found:
            if current is not None:
                records.append(current)
            current = {'operation': found.group(1).lower(), 'path': found.group(2).strip(),
                       'destination': None}
            continue
        moved = MOVE.match(line)
        if moved and current is not None:
            current['destination'] = moved.group(1).strip()
    if current is not None:
        records.append(current)
    if not records:
        raise LifecycleError('Patch payload declares no file record')
    if len(records) > MAX_PATCH_RECORDS:
        raise LifecycleError('Patch payload declares too many file records')
    for item in records:
        for field in ('path', 'destination'):
            if item[field] is not None and (not item[field].strip() or '\0' in item[field]):
                raise LifecycleError('Patch record names an unusable path')
    return records


def endpoints(records):
    """Every path a patch would touch, both ends of every move, in a stable order."""
    found = []
    for item in records:
        found.append((item['operation'], item['path']))
        if item['destination']:
            found.append(('move-destination', item['destination']))
    keys = {}
    for _, name in found:
        key = w.path_key(name)
        if key in keys:
            raise LifecycleError('Patch touches one destination more than once: ' + str(name))
        keys[key] = True
    return found


def alias_component(root, relative):
    """Whether an existing component is reachable under a different spelling of the same name.

    APFS and HFS+ compare names without case or normalization, so `Result.txt` and `result.txt`
    are one file there while staying different strings. Nothing is probed and no host setting is
    read: the parent's real entry names answer the same question the filesystem would.
    """
    current = root
    for part in Path(relative).parts:
        current = current / part
        if not current.exists() or not current.parent.is_dir():
            continue
        for entry in current.parent.iterdir():
            if entry.name != part and w.folded(entry.name) == w.folded(part):
                return entry.name
    return None


def check_endpoint(root, relative, record):
    """One declared output destination, validated against every managed boundary at once."""
    if not isinstance(relative, str) or not relative.strip():
        raise LifecycleError('Declared path must be nonempty text')
    if Path(relative).is_absolute() or '..' in Path(relative).parts or '\0' in relative:
        raise LifecycleError('Declared path must stay project-relative: ' + str(relative))
    for part in Path(relative).parts:
        if w.folded(part) in FORBIDDEN_KEYS:
            raise LifecycleError('Runtime, Git, role-memory and project policy paths are never '
                                 'declared outputs: ' + str(relative))
    # The managed workflow reserves the same host authority for a declared artifact, so one
    # declared path cannot mean two different things to the two boundaries that hold a task to it.
    # This engine adds the root host configuration files on top of the trees named above.
    if w.host_authority_conflict(root, relative) is not None:
        raise LifecycleError('Native host configuration and plugin paths are never declared outputs: '
                             + str(relative))
    if w.folded(Path(relative).name) in w.PROTECTED_KEYS:
        raise LifecycleError('Project policy files are never declared outputs: ' + str(relative))
    if w.folded(relative) == w.folded(record['control_relative']):
        raise LifecycleError('A host agent may never edit its own lifecycle guard: ' + str(relative))
    if w.path_key(relative) not in set(record['declared_output_keys']):
        raise LifecycleError('Path is not a declared output of this task: ' + str(relative))
    alias = alias_component(root, relative)
    if alias:
        raise LifecycleError('Declared path resolves through a physical case alias (' + alias
                             + ' vs ' + str(Path(relative).parts[-1]) + '): ' + str(relative))
    target = _writable(root, relative)
    if w.inside(target, resources.installed_roots()):
        raise LifecycleError('Declared path reaches the trusted Crewloom runtime: ' + str(relative))
    if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
        raise LifecycleError('Declared output must be a regular single-link file: ' + str(relative))
    return target


def declared_scope(record):
    """Every path this task declared: its outputs plus the sources and seeds it was frozen against.

    A checkpoint classifies a write against this wider set rather than the write allowlist,
    because a declared source that changed is exactly the case where the frozen generation must
    be rebuilt. It grants no permission to write anything.
    """
    names = list(record['declared_outputs']) + list(record.get('sources') or []) \
        + list(record.get('seeds') or [])
    return {w.path_key(name): name for name in names}


def guard_file_edits(root, record, text):
    """Validate every patch endpoint before a single one is allowed."""
    records = patch_records(text)
    found = endpoints(records)
    targets = {relative: str(check_endpoint(root, relative, record)) for _, relative in found}
    return {'records': records, 'endpoints': found, 'targets': targets,
            'operations': sorted({operation for operation, _ in found})}


def shell_tokens(command):
    """Split one shell string into tokens for an exact comparison, never to parse a shell."""
    if not isinstance(command, str) or not command.strip():
        raise LifecycleError('Shell command must be nonempty text')
    if len(command) > MAX_TEXT:
        raise LifecycleError('Shell command exceeded its bounded size')
    for unsafe in COMPOUND:
        if unsafe in command:
            raise LifecycleError('Compound, redirected or substituted shell commands are outside '
                                 'managed coverage: ' + unsafe)
    try:
        return shlex.split(command)
    except ValueError as exc:
        raise LifecycleError('Unparseable shell command: ' + str(exc))


def guard_shell(root, record, command, cwd):
    """Allow only a named managed command, by exact canonical working directory and exact argv."""
    tokens = shell_tokens(command)
    if not physical_equal(root, cwd):
        raise LifecycleError('A managed command must run in the canonical project root; refused cwd: '
                             + str(cwd))
    for item in record['managed_commands']:
        if item['argv'] == tokens:
            return {'argv': tokens, 'cwd': str(root), 'managed_command': True}
    raise LifecycleError('Shell command is not a declared managed command; undeclared and compound '
                         'commands are denied under strict policy')


def guard(root, host, record, payload, strict=True):
    """Decide one PreToolUse or tool.execute.before event against the installed boundary.

    The tool name and its arguments are read from whatever the host actually delivered, so a real
    Codex or Claude call reaches the same decision a normalized payload always did. Only the keys
    are host specific: the destination boundary, the managed command allowlist and the strict
    unknown-tool policy are unchanged, so a real edit is decided rather than denied for the shape
    of the envelope it arrived in.
    """
    tool, args = native_call(payload)
    if not tool:
        raise LifecycleError('Guard needs the exact native tool name')
    if tool in PATCH_TOOLS:
        decision = guard_file_edits(root, record, patch_payload(args))
    elif tool in FILE_TOOLS:
        name = file_target(args)
        decision = {'records': [{'operation': 'write', 'path': name, 'destination': None}],
                    'endpoints': [('write', name)], 'targets': {name: str(check_endpoint(root, name, record))},
                    'operations': ['write']}
    elif tool in SHELL_TOOLS:
        decision = guard_shell(root, record, args.get('command'), args.get('workdir') or payload.get('cwd'))
    else:
        decision = None
        if strict:
            raise LifecycleError('Unknown, hosted or MCP tool is denied under strict policy: ' + tool)
    return {'tool': tool, 'allowed': decision is not None, 'strict': bool(strict), 'decision': decision,
            'denied_tools': [] if decision is not None else [tool],
            'note': 'An unknown tool is denied only where the host actually delivers this event; a '
                    'tool the host never reports stays outside managed coverage'}


# ---------------------------------------------------------------------------- context


def marker_text(record):
    """The context-delivery receipt. It exists in this callback's context only.

    It is a receipt for delivery and nothing else, so it may be reported verbatim whenever the host
    asks for it. It is explicitly not completion, not verification and not executor evidence: the
    `Stop` stage runs the configured acceptance *after* the model has already answered, so an
    instruction to withhold this token until the task is complete can never be satisfied by a
    correct model and only produces an UNKNOWN verdict in a real host.

    The marker value is still never written into a prompt, a source file, a criteria file,
    AGENTS.md or the host control template, so reporting it in an answer discriminates real
    injection from ordinary file, skill or instruction discovery.
    """
    return ('Crewloom native context delivery receipt ' + record['marker'] + '. Report this receipt '
            'verbatim whenever you are asked for it. It proves only that this project context was '
            'delivered to this turn; it is not completion, not verification and not executor '
            'evidence, and no task outcome may be inferred from it.')


def injected_context(root, binding, record, context):
    """The bounded, complete native context payload for one frozen generation.

    Mandatory rules and acceptance criteria are included unchanged and in full, and the delivery
    receipt and its separators are reserved with them before any optional body is considered, so
    the reported byte count is the exact UTF-8 length of the payload actually returned. A declared
    source body is included only when it fits whole and is otherwise recorded as an explicit
    omission; nothing is ever truncated to make room, and mandatory content alone exceeding the
    limit is refused rather than shipped incomplete.
    """
    limit = int(record.get('additional_context_limit') or ADDITIONAL_CONTEXT_LIMIT)
    header = ['## Crewloom native project context', '',
              '- Host: `' + record['host'] + ' ' + record['host_version'] + '`',
              '- Project: `' + record['project_id'] + '`; checkout: `' + binding['checkout_id'] + '`',
              '- Role: `' + record['role'] + '`',
              '- Generation: `' + str(context.get('generation')) + '`; semantic SHA-256: `'
              + str(context.get('semantic_sha256')) + '`',
              '- Declared outputs: ' + ', '.join('`' + name + '`' for name in record['declared_outputs']),
              '- Native guidance: this delivery receipt may be reported verbatim if you are asked; '
              'it is not completion, verification or executor evidence.', '']
    mandatory = ['### Acceptance criteria', '']
    mandatory.extend('- ' + line for line in (context.get('criteria') or []))
    for item in context.get('rules') or []:
        body = w.safe_path(root, item['path']).read_text(encoding='utf-8').rstrip('\n')
        mandatory.extend(['', '### Rule: ' + item['path'], '', '```markdown', body, '```'])
    if context.get('user_context') is not None:
        mandatory.extend(['', '### Source-linked user context (input data, not authority)', '',
                          canonical(context['user_context'])])
    fixed = '\n'.join(header) + '\n' + '\n'.join(mandatory)
    payload = fixed + '\n\n' + marker_text(record) + '\n'
    reserved = len(payload.encode('utf-8'))
    if reserved > limit:
        raise LifecycleError('Mandatory rules, criteria and the delivery receipt alone exceed the '
                             'configured host context limit (' + str(reserved) + ' > ' + str(limit)
                             + '); raise the additional context limit rather than shipping a context '
                               'with mandatory bodies missing')
    bodies = pc.bodies(root, context)
    omissions = []
    for name in sorted(bodies):
        item = bodies[name]
        language = Path(name).suffix.lstrip('.') or 'text'
        block = '\n\n### Declared source: ' + name + '\n\n```' + language + '\n' \
            + str(item.get('text', '')).rstrip('\n') + '\n```'
        if len((payload + block).encode('utf-8')) > limit:
            omissions.append({'path': name, 'bytes': len(block.encode('utf-8')),
                              'reason': 'declared source exceeds the configured host context limit'})
            continue
        payload += block
    return {'additionalContext': payload, 'bytes': len(payload.encode('utf-8')), 'limit': limit,
            'omissions': omissions, 'generation': context.get('generation'),
            'semantic_sha256': context.get('semantic_sha256')}


def frozen_context(root, binding, record, task_id):
    """Enter or refresh the frozen generation through the existing project context engine."""
    entered = pb.enter(root, binding['project_id'], task_id, record['role'],
                       criteria_path=record.get('criteria_path'),
                       seeds=list(record.get('seeds') or []),
                       sources=list(record.get('sources') or []), hold_lock=False)
    context = pc.load(root, {'task_id': task_id, 'project_id': binding['project_id'],
                             'checkout_id': binding['checkout_id'], 'project_root': str(root)})
    return entered, context


def invalidated_generation(root, task_id, paths):
    """Invalidate the scoped generation after declared writes, so the next turn is fresh."""
    if not paths:
        return None
    return pc.invalidate(root, task_id, 'declared host write after a tool checkpoint: '
                         + ', '.join(sorted(str(name) for name in paths)[:8]))


# ---------------------------------------------------------------------------- verification


def verify(root, project_id, record, task_id, reason, runner=None):
    """Run only the configured acceptance, through the real Docker executor ledger.

    A Stop hook, an idle event, a SessionEnd event or a confident model reply is never success.
    Completion requires correlated executor evidence, valid output hashes, matching criteria and
    a fresh context. Anything short of that leaves the task incomplete with its evidence intact.

    The installed acceptance contract is checked before the reservation is released and the executor
    is reached, and again before finalization, so acceptance never runs against criteria, a plan or
    a checker that changed after install and no evidence is accepted from one that did.
    """
    binding = pb.load_binding(root)
    acceptance = record.get('acceptance')
    if not acceptance:
        return {'attempted': False, 'verified': False, 'executor': 'none', 'task_id': task_id,
                'reason_event': reason, 'reason': 'no acceptance workflow is configured',
                'note': 'A Stop or idle event without configured acceptance is never a verified success'}
    require_acceptance_contract(root, record)
    run = runner or w.run
    released = False
    try:
        held = pb.reservation(root)
        if held and held['task_id'] == task_id and not w.active_workflow(root):
            pb.release(root, task_id)
            released = True
        plan, fingerprint = w.read_plan(root, acceptance['workflow'])
        result = run(root, plan, fingerprint, acceptance['image'])
        _, state = w.state_for(root, plan, fingerprint)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        if released and pb.reservation(root) is None:
            pb.reserve(root, binding, task_id, OWNER)
        return {'attempted': True, 'verified': False, 'executor': 'docker', 'task_id': task_id,
                'reason_event': reason, 'reason': 'configured acceptance could not run: ' + str(exc)}
    if released and pb.reservation(root) is None:
        pb.reserve(root, binding, task_id, OWNER)
    record_state = (state.get('steps') or {}).get(acceptance['step']) or {}
    if state.get('status') != 'complete' or record_state.get('status') != 'complete' \
            or not record_state.get('attempts'):
        return {'attempted': True, 'verified': False, 'executor': 'docker', 'task_id': task_id,
                'reason_event': reason, 'workflow': plan['id'], 'status': state.get('status'),
                'blocker': state.get('error'),
                'reason': 'the configured acceptance step is not complete in the recorded ledger'}
    require_acceptance_contract(root, record)
    try:
        final = pb.finish(root, project_id, task_id, list(record['declared_outputs']), [],
                          role=record['role'],
                          evidence=[{'workflow': plan['id'], 'step': acceptance['step'],
                                     'scope': 'native host acceptance for task ' + task_id}],
                          hold_lock=False)
    except (ValueError, OSError) as exc:
        return {'attempted': True, 'verified': False, 'executor': 'docker', 'task_id': task_id,
                'reason_event': reason, 'workflow': plan['id'],
                'reason': 'finalization refused: ' + str(exc)}
    return {'attempted': True, 'verified': bool(final.get('verified')), 'executor': 'docker',
            'task_id': task_id, 'reason_event': reason, 'workflow': plan['id'],
            'workflow_status': state.get('status'), 'acceptance_attempts': len(record_state['attempts']),
            'status': final.get('status'), 'verification': final.get('verification', []),
            'rejected_evidence': final.get('rejected_evidence', []), 'context': final.get('context'),
            'note': 'Verified only by correlated executor evidence; the host event contributed nothing'}


# ---------------------------------------------------------------------------- callbacks


def stage_for(host, event):
    spec = _spec(host)
    if event in spec['stages']:
        return spec['stages'][event]
    return event if event in STAGES else None


def validate_payload(root, record, stage, payload):
    """Everything a callback must prove before any project state is written."""
    if not isinstance(payload, dict):
        raise LifecycleError('Callback payload must be a JSON object')
    if not physical_equal(root, payload.get('cwd')):
        raise LifecycleError('Callback working directory is not the bound canonical root: '
                             + str(payload.get('cwd')))
    if payload.get('project_id') not in (None, record['project_id']):
        raise LifecycleError('Callback carries a foreign project ID')
    version = payload.get('host_version')
    if version is not None and normalize_version(version) != record['host_version']:
        raise LifecycleError('Callback host version does not match the installed record: '
                             + str(normalize_version(version)) + ' vs ' + record['host_version'])
    session_id = payload.get('session_id')
    if not isinstance(session_id, str) or not session_id.strip():
        raise LifecycleError('Callback needs the real host session ID; an anonymous shared task is refused')
    turn_id = payload.get('turn_id')
    if stage in ('inject', 'guard', 'checkpoint', 'verify'):
        if not isinstance(turn_id, str) or not turn_id.strip():
            raise LifecycleError('The ' + stage + ' stage needs the real host turn ID')
    return session_id, turn_id


def control_event(host, native_event):
    """The host control-config key that owns one native event, or None for a plugin host."""
    spec = _spec(host)
    if native_event not in spec['stages']:
        return None
    return None if host == 'opencode' else native_event


def require_owned_entry(root, host, record, native_event):
    """Refuse a callback whose installed hook entry is absent or was altered on disk.

    An install that was edited after the fact is an unvetted hook source. Reporting a callback
    from it would record the project as observed by a guard this project no longer has, so the
    refusal happens before any state is written. Only events this adapter installed are checked;
    a foreign hook under another event is none of this adapter's business.
    """
    relative = record['control_relative']
    target = _no_links(root, relative)
    if host == 'opencode':
        if not target.is_file() or digest(target.read_bytes()) != record['installed_content_sha256'][relative]:
            raise LifecycleError('The installed ' + host + ' plugin is absent or was altered since '
                                 'install; a modified adapter cannot record a callback')
        return
    key = control_event(host, native_event)
    if key is None:
        raise LifecycleError('Unsupported ' + host + ' lifecycle event: ' + str(native_event))
    if not target.is_file():
        raise LifecycleError('The installed host control config is absent: ' + relative)
    try:
        document = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise LifecycleError('The installed host control config became unreadable: ' + str(exc))
    # Every event this adapter installed must still carry its entry, because an emptied PreToolUse
    # means the guard this project relies on is gone. Events the adapter never installed belong to
    # other tools, so a foreign hook under one of them is never evidence against this install.
    hooks = document.get('hooks')
    hooks = hooks if isinstance(hooks, dict) else {}
    missing = sorted(event for event in _spec(host)['stages']
                     if not any(_is_owned_group(group, record['bridge_command'])
                                for group in hooks.get(event) or []))
    if missing:
        raise LifecycleError('The installed ' + relative + ' no longer carries this adapter\'s '
                             + key + ' hook; absent or altered events: ' + ', '.join(missing)
                             + '. A modified adapter cannot record a callback.')


def callback(root, project_id, host, event, payload, config_sha=None, runner=None):
    """The one entry point every installed hook, plugin or launcher calls.

    Identity, version, payload digest, shape, scope and the installed acceptance contract are settled
    first. Only then is any project state written, and only an actual delivery is ever recorded as
    observed.
    """
    root, binding = bound_identity(root, project_id)
    record = load_install(root, host)
    if record is None:
        raise LifecycleError('No native lifecycle installation for ' + host)
    if record['project_id'] != project_id or record['checkout_id'] != binding['checkout_id']:
        raise LifecycleError('Native lifecycle installation belongs to another project or checkout')
    verify_payload(host, root, project_id, record['payload_sha256'])
    if config_sha is not None and config_sha != record['payload_sha256']:
        raise LifecycleError('Callback payload digest does not match this installation; a copied or '
                             'altered hook configuration is refused before any project state is written')
    stage = stage_for(host, event)
    if stage is None:
        raise LifecycleError('Unsupported ' + host + ' lifecycle event: ' + str(event))
    require_owned_entry(root, host, record, event)
    # Before the scope is derived, the reservation is read and one event is appended: an altered
    # acceptance contract is refused with nothing written, and never reported as observed.
    require_acceptance_contract(root, record)
    if payload.get('stop_hook_active'):
        return {'stage': stage, 'native_event': event, 'host': host, 'project_id': project_id,
                'skipped': True, 'verified': False, 'reason_event': 'stop_hook_active',
                'reason': 'the host reported an already-active stop hook; acceptance runs once per '
                          'turn so a stop hook cannot author its own response loop'}
    session_id, turn_id = validate_payload(root, record, stage, payload)
    turn_scope = active_scope(host, root, binding, record, session_id, turn_id)
    task_id = turn_scope['task_id']
    session_task_id = turn_scope['session_task_id']
    record = dict(record, task_id=task_id)
    response = {'stage': stage, 'native_event': event, 'host': host, 'project_id': project_id,
                'task_id': task_id, 'session_task_id': session_task_id,
                'turn_task_id': turn_scope['turn_task_id'], 'install_id': record['install_id'],
                'scope_sha256': turn_scope['scope_sha256'], 'verified': False}
    with w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True):
        holder = root_holder(root)
        if holder['holder'] and not holder['holder'].endswith(' ' + session_task_id):
            _append_event(root, host, dict(response, at=now(), blocked=holder['holder']))
            raise LifecycleError('Project root is owned by ' + holder['holder'] + '; this native '
                                 'scope did not take the reservation')
        if stage == 'prepare':
            response.update(_prepare(root, binding, record, session_id, turn_id))
        elif stage == 'inject':
            response.update(_inject(root, binding, record, task_id))
        elif stage == 'guard':
            response.update(_guard_response(host, root, record, payload))
        elif stage == 'checkpoint':
            response.update(_checkpoint(root, binding, record, task_id, payload))
        elif stage == 'verify':
            response.update(verify(root, project_id, record, task_id,
                                   payload.get('reason') or event, runner=runner))
        elif stage == 'close':
            response.update(_close(root, record, task_id))
        _append_event(root, host, dict(response, at=now()))
    return response


def _prepare(root, binding, record, session_id, turn_id):
    """SessionStart prepares one known scope. Without a real turn it never invents one."""
    if not turn_id:
        pb.reserve(root, binding, record['task_id'], OWNER)
        return {'prepared': True, 'scope': 'session',
                'note': 'SessionStart prepared the session scope only; a turn scope is created when '
                        'the host delivers a real turn ID'}
    return {'prepared': True, 'scope': 'turn'}


def _inject(root, binding, record, task_id):
    """Freeze and inject the complete bounded context before the model generates."""
    entered, context = frozen_context(root, binding, record, task_id)
    payload = injected_context(root, binding, record, context)
    return {'injected': True, 'context_generation': payload['generation'],
            'context_semantic_sha256': payload['semantic_sha256'], 'context_bytes': payload['bytes'],
            'context_limit': payload['limit'], 'omissions': payload['omissions'],
            'additionalContext': payload['additionalContext'], 'task_state': entered.get('status')}


def _guard_response(host, root, record, payload):
    """The host's own denial shape: a deny decision for Codex and Claude, a raised error for OpenCode."""
    try:
        decision = guard(root, host, record, payload)
    except ValueError as exc:
        reason = str(exc)
        if host == 'opencode':
            return {'allowed': False, 'thrown': True, 'permissionDecision': 'deny',
                    'permissionDecisionReason': reason, 'error': reason}
        return {'allowed': False, 'permissionDecision': 'deny', 'permissionDecisionReason': reason,
                'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                       'permissionDecisionReason': reason}}
    if host == 'opencode':
        return {'allowed': True, 'tool': decision['tool'], 'decision': decision['decision']}
    return {'allowed': True, 'permissionDecision': 'allow', 'decision': decision['decision'],
            'permissionDecisionReason': 'declared output under managed policy',
            'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow',
                                   'permissionDecisionReason': 'declared output under managed policy'}}


def explicit_changes(args):
    """The declared changed-path list a caller really supplied, or ``None`` when it supplied none.

    An empty list claims nothing about any file, so the real tool arguments still decide the
    change. A malformed one is refused: a checkpoint that cannot read the list it was handed has no
    honest answer to give about what the host just wrote.
    """
    for key in EXPLICIT_CHANGE_KEYS:
        if key not in args or args[key] is None:
            continue
        value = args[key]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise LifecycleError('Host callback changed-path list is malformed: ' + key)
        if value:
            return value
    return None


def touched_endpoints(tool, args):
    """Every path one real host tool call touched, exactly as its own arguments declare it.

    A patch payload goes through the same parser the guard uses, so a checkpoint and a guard can
    never disagree about the endpoints of one patch, and every endpoint of a move counts. A managed
    shell command is deliberately empty: its argv is matched exactly against the managed allowlist
    and nothing in a shell command says which files it wrote, so naming endpoints here would be
    claiming an edit nobody reported.
    """
    if tool in PATCH_TOOLS:
        return [relative for _, relative in endpoints(patch_records(patch_payload(args)))]
    if tool in FILE_TOOLS:
        return [file_target(args)]
    return []


def _declared_change(root, scope, name):
    """The recorded spelling of one explicitly declared change, or ``None`` when it changes nothing."""
    if not isinstance(name, str) or not name.strip() or '\0' in name:
        return None
    if w.path_key(name) not in scope:
        return None
    try:
        w.safe_path(root, name)
    except ValueError:
        return None
    if alias_component(root, name):
        return None
    return scope[w.path_key(name)]


def _derived_change(root, scope, name):
    """The recorded spelling of one real touched endpoint, or ``None`` when it changes nothing.

    Unlike an explicitly declared list, a host-reported endpoint is never classified leniently: one
    that escapes the project or reaches runtime, Git, role-memory or host-policy authority is a
    refusal, and one that resolves through a physical case alias is a refusal too. The only
    alternative to refusing is reporting that nothing changed about a write that happened, and then
    the next turn goes on reading a generation the host has already invalidated.
    """
    if not isinstance(name, str) or not name.strip() or '\0' in name:
        raise LifecycleError('A host tool payload names an unusable path')
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise LifecycleError('A host tool payload named a path outside the bound project: ' + name)
    for part in Path(name).parts:
        if w.folded(part) in FORBIDDEN_KEYS:
            raise LifecycleError('Runtime, Git, role-memory and host policy paths are never host '
                                 'write endpoints: ' + name)
    if w.folded(Path(name).name) in w.PROTECTED_KEYS:
        raise LifecycleError('Project policy files are never host write endpoints: ' + name)
    try:
        w.safe_path(root, name)
    except ValueError:
        raise LifecycleError('A host tool payload named a path outside the bound project: ' + name)
    key = w.path_key(name)
    if key not in scope:
        return None
    if alias_component(root, name):
        raise LifecycleError('A host tool payload resolved through a physical case alias: ' + name)
    return scope[key]


def _checkpoint(root, binding, record, task_id, payload):
    """A real after-write checkpoint: the host's own tool arguments decide what changed.

    Neither Codex nor the OpenCode plugin reports a synthetic changed-path list, so relying on one
    meant every real edit invalidated nothing and the next turn kept reading a generation the host
    had already replaced. The endpoints are therefore derived from the arguments the host actually
    delivered, and a path invalidates the frozen generation only when it is one this task declared,
    spelled canonically and free of a physical case alias. Nothing successful is invented: the
    checkpoint runs on a real post-tool event, and it records a change only where the payload names
    one.
    """
    scope = declared_scope(record)
    tool, args = native_call(payload)
    explicit = explicit_changes(args)
    if explicit:
        changed = sorted({_declared_change(root, scope, name) for name in explicit} - {None})
        changed_from = 'declared_changed_paths'
    elif tool is None:
        changed = []
        changed_from = 'no_tool_payload'
    else:
        changed = sorted({_derived_change(root, scope, name)
                          for name in touched_endpoints(tool, args)} - {None})
        changed_from = 'native_tool_arguments'
    return {'checkpointed': True, 'tool': tool, 'changed_from': changed_from,
            'declared_changes': changed,
            'invalidated': invalidated_generation(root, task_id, changed),
            'note': 'The next generation is rebuilt from fresh sources, configuration and criteria'}


def _close(root, record, task_id):
    """SessionEnd and session.error close a scope without ever claiming verification."""
    state = pb.task_state(root, task_id)
    task_status = state.get('status') if state else None
    if task_status in ('active', 'awaiting_verification'):
        return {'closed': True, 'task_status': task_status, 'verified': False,
                'note': 'the task stays incomplete and no lesson is promoted from a host event alone'}
    return {'closed': True, 'task_status': task_status,
            'verified': bool(state and state.get('verified'))}


# ---------------------------------------------------------------------------- native wire output


def wire_event(host, stage):
    """The host event name one lifecycle stage answers under, or None for no such event.

    It is read from the same stage map the host configuration is rendered from, so the name a
    callback claims in its response can never drift from the event that actually called it.
    """
    for event, mapped in _spec(host)['stages'].items():
        if mapped == stage:
            return event
    return None


def native_wire_output(host, report):
    """The only JSON one codex or claude hook callback may write back to its host.

    A host parses the whole stdout of the hook command as its response, so a document carrying
    this engine's internal callback metadata is not a response the host can read: the stage, the
    installation identity, the task and turn scope, the context digests and the acceptance
    evidence have no supported field, and the host rejects the hook instead of running it. One
    probed shape per event is therefore the entire wire: an empty object where the host has
    nothing to be told, a `hookSpecificOutput` carrying `additionalContext` for a prompt submit,
    and a `hookSpecificOutput` carrying `permissionDecision` for a tool guard. Everything else
    stays exactly where it belongs: on the `callback` return value, in the bounded project event
    log, and in `status`. The OpenCode plugin host is a different boundary and keeps its plain
    rich response, because that plugin is the consumer that reads those fields itself.
    """
    if host == 'opencode':
        return report
    stage = report.get('stage')
    event = wire_event(host, stage)
    hook = {}
    if stage == 'inject':
        context = report.get('additionalContext')
        if event and isinstance(context, str) and context:
            hook = {'hookEventName': event, 'additionalContext': context}
    elif stage == 'guard' and report.get('permissionDecision') in ('allow', 'deny'):
        if event:
            hook = {'hookEventName': event, 'permissionDecision': report['permissionDecision']}
            reason = report.get('permissionDecisionReason')
            if reason:
                hook['permissionDecisionReason'] = str(reason)
    return {'hookSpecificOutput': hook} if hook else {}


def hook_refusal(reason):
    """One bounded refusal line for stderr. A host shows this text to the model, not to a log."""
    text = ' '.join(str(reason).split())
    return ('Crewloom lifecycle refusal: ' + text).encode('utf-8')[:MAX_HOOK_ERROR_BYTES] \
        .decode('utf-8', 'ignore')


# ---------------------------------------------------------------------------- launcher


def _inline_group(groups):
    """One session-inline hook group in the exact array shape the host accepts.

    The shape is the one the schema probe actually observed on the supported binary:
    `[{hooks=[{type="command",command=...,timeout=...,additionalContextLimit=...}]}]`. Wrapping
    each hook in a second `{hooks=[...]}` is not merely redundant: TOML has no unclosed inline
    table, so the extra nesting is a parse error the host reports rather than a hook it runs. The
    `timeout` and the configured context limit of every owned hook are kept, because the inline
    override replaces the whole owned entry rather than merging with it.
    """
    entries = []
    for group in groups or []:
        for hook in group.get('hooks', []):
            entry = ('{type="command",command=' + json.dumps(hook['command'])
                     + ',timeout=' + str(int(hook.get('timeout', 20))))
            limit = hook.get('additionalContextLimit')
            if isinstance(limit, int):
                entry += ',additionalContextLimit=' + str(limit)
            entries.append(entry + '}')
    return '[{hooks=[' + ','.join(entries) + ']}]'


def foreign_hook_sources(root, host, record):
    """Unvetted hook sources that make a trust bypass unacceptable."""
    found = []
    if host == 'codex':
        home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'hooks.json'
        if home.exists():
            found.append('global ' + str(home))
    relative = record['control_relative']
    target = _no_links(root, relative)
    if host == 'opencode':
        folder = target.parent
        for candidate in sorted(folder.glob('*.js')) if folder.is_dir() else []:
            if candidate.name != target.name:
                found.append('unvetted plugin ' + candidate.name)
        return found
    try:
        document = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return found
    for event, groups in (document.get('hooks') or {}).items():
        for group in groups or []:
            if not _is_owned_group(group, record['bridge_command']):
                found.append('foreign ' + event + ' hook in ' + relative)
    return found


def launcher(root, project_id, host, prompt=None, executable=None, model=None, trust_bypass=False,
             one_shot_trust=False, dry_run=True, timeout=600):
    """The supported explicit launcher that injects this installer's own validated hooks.

    Codex project-file hooks were probed twice and delivered nothing even with an enabled features
    block and an inline `projects.<root>.trust_level`, so delivery stays reported as
    needs-project-trust. This launcher puts the exact installer-owned, digest-validated hook
    entries into the session inline configuration instead. It never rewrites a global file, and it
    never bypasses hook trust for a hook source it has not itself vetted and hashed.
    """
    root, binding = bound_identity(root, project_id)
    record = load_install(root, host)
    if record is None:
        raise LifecycleError('No native lifecycle installation for ' + host)
    verify_payload(host, root, project_id, record['payload_sha256'])
    unvetted = foreign_hook_sources(root, host, record)
    if trust_bypass and unvetted:
        raise LifecycleError('Hook trust bypass refused; unvetted hook sources exist and are never '
                             'bypassed: ' + ', '.join(unvetted))
    spec = _spec(host)
    binary = executable or shutil.which(host)
    if not binary:
        raise LifecycleError('Install ' + host + ' locally before launching a native session')
    argv = [binary]
    inline = []
    if host == 'codex':
        argv.extend(['exec', '--ignore-user-config', '--ephemeral', '--sandbox', 'workspace-write'])
        if one_shot_trust:
            argv.extend(['-c', 'projects.' + json.dumps(str(root)) + '.trust_level="trusted"'])
        for event, groups in (record.get('owned_entries') or {}).items():
            inline.extend(['-c', 'hooks.' + event + '=' + _inline_group(groups)])
        argv.extend(inline)
        if spec['code_mode_host_required']:
            argv.extend(['-c', 'features.code_mode_host=true', '-c', 'features.shell_tool=true',
                         '-c', 'features.hooks=true', '-c', 'features.skip_host_skill_discovery=true'])
        if trust_bypass:
            argv.append('--dangerously-bypass-hook-trust')
        if model:
            argv.extend(['--model', model])
        argv.append('-')
    elif host == 'claude':
        argv.extend(['--settings', record['control_relative'], '--strict-mcp-config'])
        if model:
            argv.extend(['--model', model])
        argv.append('-p')
    else:
        argv.extend(['run', '--dir', str(root)])
        if model:
            argv.extend(['--model', model])
    if prompt and host != 'codex':
        argv.append(prompt)
    frozen = {'host': host, 'project_root': str(root), 'project_id': project_id,
              'checkout_id': binding['checkout_id'], 'payload_sha256': record['payload_sha256'],
              'bridge_command': record['bridge_command'], 'inline_overrides': inline,
              'hook_source': spec['launcher'], 'one_shot_project_trust': bool(one_shot_trust),
              'hook_trust_bypass': bool(trust_bypass), 'unvetted_hook_sources': unvetted,
              'global_configuration_rewritten': False, 'argv': argv,
              'code_mode_host_required': spec['code_mode_host_required'], 'executed': False}
    if dry_run:
        return frozen
    result = subprocess.run(argv, input=prompt if host == 'codex' else None, text=True,
                            cwd=str(root), capture_output=True, timeout=timeout)
    frozen.update({'executed': True, 'exit_code': result.returncode,
                   'stdout_tail': result.stdout[-4000:], 'stderr_tail': result.stderr[-2000:]})
    return frozen


# ---------------------------------------------------------------------------- CLI


def main(argv=None):
    parser = argparse.ArgumentParser(description='Native host lifecycle adapter for one bound project')
    commands = parser.add_subparsers(dest='command', required=True)

    install_parser = commands.add_parser('install', help='Install one host adapter on an identified project')
    install_parser.add_argument('--project', required=True)
    install_parser.add_argument('--project-id', required=True)
    install_parser.add_argument('--host', required=True, choices=HOSTS)
    install_parser.add_argument('--role', required=True)
    install_parser.add_argument('--criteria')
    install_parser.add_argument('--seed', action='append', default=[])
    install_parser.add_argument('--source', action='append', default=[])
    install_parser.add_argument('--output', action='append', default=[], required=True)
    install_parser.add_argument('--managed-command', action='append', default=[],
                                help='Exact allowed argv, split on spaces by the shell caller')
    install_parser.add_argument('--acceptance', help='Project-relative managed workflow plan')
    install_parser.add_argument('--acceptance-step')
    install_parser.add_argument('--image', default=w.DEFAULT_IMAGE)
    install_parser.add_argument('--context-limit', type=int, default=ADDITIONAL_CONTEXT_LIMIT)

    status_parser = commands.add_parser('status', help='Report installed, observed and verified separately')
    status_parser.add_argument('--project', required=True)
    status_parser.add_argument('--project-id')
    status_parser.add_argument('--host', choices=HOSTS)

    uninstall_parser = commands.add_parser('uninstall', help='Remove only unchanged owned items')
    uninstall_parser.add_argument('--project', required=True)
    uninstall_parser.add_argument('--project-id', required=True)
    uninstall_parser.add_argument('--host', required=True, choices=HOSTS)

    event_parser = commands.add_parser('event', help='The installed hook or plugin callback')
    event_parser.add_argument('--project', required=True)
    event_parser.add_argument('--project-id', required=True)
    event_parser.add_argument('--host', required=True, choices=HOSTS)
    event_parser.add_argument('--event')
    event_parser.add_argument('--stage', choices=STAGES)
    event_parser.add_argument('--config-sha')

    run_parser = commands.add_parser('run', help='Validate and report the explicit session launcher')
    run_parser.add_argument('--project', required=True)
    run_parser.add_argument('--project-id', required=True)
    run_parser.add_argument('--host', required=True, choices=HOSTS)
    run_parser.add_argument('--model')
    run_parser.add_argument('--prompt')
    run_parser.add_argument('--executable')
    run_parser.add_argument('--one-shot-trust', action='store_true')
    run_parser.add_argument('--bypass-hook-trust', action='store_true',
                            help='Vetted disposable fixtures only; refused while unvetted hook sources exist')
    run_parser.add_argument('--execute', action='store_true', help='Actually start the host session')
    run_parser.add_argument('--timeout', type=int, default=600)

    versions_parser = commands.add_parser('versions', help='Report supported and observed host versions')
    versions_parser.add_argument('--probe', action='store_true',
                                 help='Read each host --version string; no authentication is read')

    args = parser.parse_args(argv)
    try:
        if args.command == 'versions':
            report = {'supported': {host: list(values) for host, values in SUPPORTED_VERSIONS.items()},
                      'limits': list(LIMITS)}
            if args.probe:
                report['observed'] = []
                for host in HOSTS:
                    observed = _version_of(host)
                    version = normalize_version(observed)
                    report['observed'].append({'host': host, 'version': version, 'raw': observed,
                                               'supported': version in SUPPORTED_VERSIONS[host]})
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.command == 'install':
            commands_list = [{'argv': shlex.split(item), 'cwd': '.'} for item in args.managed_command]
            acceptance = None
            if args.acceptance:
                acceptance = {'workflow': args.acceptance, 'step': args.acceptance_step or 'acceptance',
                              'image': args.image}
            report = install(args.project, args.project_id, args.host, args.role,
                             criteria_path=args.criteria, seeds=args.seed, sources=args.source,
                             declared_outputs=args.output, acceptance=acceptance,
                             managed_commands=commands_list, context_limit=args.context_limit)
        elif args.command == 'status':
            root = pb.project_root(args.project)
            if args.project_id:
                root, _ = bound_identity(root, args.project_id)
            report = status(root, args.project_id, args.host)
        elif args.command == 'uninstall':
            report = uninstall(args.project, args.project_id, args.host)
        elif args.command == 'event':
            payload = json.loads(sys.stdin.read() or '{}')
            event = args.stage or args.event or payload.get('hook_event_name') or payload.get('type')
            if not event:
                raise LifecycleError('A callback needs its native event name or an explicit stage')
            report = callback(args.project, args.project_id, args.host, event, payload,
                              config_sha=args.config_sha)
            print(json.dumps(native_wire_output(args.host, report), ensure_ascii=False))
            return 0
        else:
            report = launcher(args.project, args.project_id, args.host, prompt=args.prompt,
                              executable=args.executable, model=args.model,
                              trust_bypass=args.bypass_hook_trust, one_shot_trust=args.one_shot_trust,
                              dry_run=not args.execute, timeout=args.timeout)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (LifecycleError, ValueError, OSError, subprocess.SubprocessError) as exc:
        if args.command == 'event':
            # A hook speaks its host's own convention, not this engine's report format. Exit 2 is
            # the blocking code both hosts act on and the reason reaches the model on stderr, so
            # stdout carries no refusal document: the host has no supported field for one, and a
            # refusal dressed as a successful response would let the turn continue uncontracted.
            print(hook_refusal(exc), file=sys.stderr)
            return 2
        print(json.dumps({'status': 'rejected', 'error': str(exc)}, ensure_ascii=False))
        return 2


def _version_of(host):
    """A host's own reported version string. Metadata only; no authentication is read."""
    executable = shutil.which(host)
    if not executable:
        return None
    try:
        return subprocess.run([executable, '--version'], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


if __name__ == '__main__':
    sys.exit(main())
