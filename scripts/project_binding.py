"""Portable project identity, local checkout binding, safe bootstrap and lifecycle.

Two identities are always required: a portable project ID in `crewloom.project.json`
and a machine-local checkout ID in `.crewloom/binding.json`. A remote URL, folder
name or last chat message is never accepted as identity. Bootstrap preflights
every writable path before the first write, checks only the selected Git index, and never runs dependency, network or
deployment steps, and never overwrites customer instructions or installed memory.

The agency adapter validates the existing project-control ledger exactly as that
ledger's own validator does; it never keeps a second client list.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import workflow as w

CONFIG_NAME = 'crewloom.project.json'
BINDING_RELATIVE = '.crewloom/binding.json'
RESERVATION_RELATIVE = '.crewloom/active_task.json'
SCHEMA_VERSION = 1
MODES = ('off', 'observe', 'enforced')
REVIEW_MODES = ('label', 'verified')
LIFECYCLES = ('managed-runner', 'instruction-assisted', 'manual')
TASK_STATES = ('active', 'awaiting_verification', 'complete', 'failed', 'cancelled', 'interrupted')
TERMINAL_STATES = ('complete', 'failed')
AGENCY_STATUSES = ('needs_reconciliation', 'blocked', 'in_progress', 'ready_for_review', 'approved')
AGENCY_EVIDENCE_ONLY = ('needs_reconciliation', 'blocked')
AGENCY_EVIDENCE_SOURCES = ('client_confirmation', 'staging_observation', 'repository_review', 'internal_decision')
AGENCY_FIELDS = {'id', 'active_dir', 'context_snapshot', 'delivery_owner', 'control_status',
                 'last_verified_at', 'next_action', 'state_evidence'}
LANGUAGES = ('en', 'ar')
PROJECT_ID = re.compile(r'[a-z0-9][a-z0-9._-]{2,63}$')
INSTRUCTION_FILES = ('AGENTS.md', 'CLAUDE.md')
MARKER_START = '<!-- crewloom:managed-context:start -->'
MARKER_END = '<!-- crewloom:managed-context:end -->'
MAX_INSTRUCTION_BYTES = 4096
LOCAL_DIRS = ('index', 'context', 'tasks', 'lessons')
METADATA_PATHS = (CONFIG_NAME, BINDING_RELATIVE, '.gitignore', '.crewloom/index', '.crewloom/context',
                  '.crewloom/tasks', '.crewloom/lessons')
LOCAL_IGNORE = '.crewloom/'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class _held:
    """The caller already owns the shared project lock; never take a second one."""

    def __enter__(self):
        return None

    def __exit__(self, *exception):
        return False


def digest(value):
    return w.digest(value)


def file_digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def project_root(value):
    """Bind one canonical root; a relative or missing path is not project identity."""
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Explicit canonical project root is required')
    root = Path(value).resolve()
    if not root.is_dir():
        raise ValueError('Project root must be an existing directory: ' + value)
    if w.LIBRARY.resolve() in root.parents:
        raise ValueError('The trusted Crewloom runtime is not a project workspace')
    return root


def no_links(root, relative):
    """Reject symlinked path components before anything resolves them."""
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Project metadata path may not use symlinks: ' + relative)
    return current


def writable(root, relative):
    """Every writable metadata path is validated before a single file is created."""
    target = no_links(root, relative)
    path = w.safe_path(root, relative, internal=relative.startswith('.crewloom'))
    if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
        raise ValueError('Project metadata must be a regular file without hardlinks: ' + relative)
    return target


def preflight(root, relatives):
    """Validate every planned metadata path before bootstrap writes anything at all."""
    folder = root / '.crewloom'
    if folder.is_symlink():
        raise ValueError('.crewloom may not be a symlink')
    if folder.exists() and not folder.is_dir():
        raise ValueError('.crewloom must be a directory')
    for relative in relatives:
        target = no_links(root, relative)
        if relative == CONFIG_NAME:
            writable(root, relative)
            continue
        if target.exists() and not (target.is_dir() or target.is_file()):
            raise ValueError('Project metadata path is not a regular file or directory: ' + relative)
        if target.is_file() and target.stat().st_nlink != 1:
            raise ValueError('Project metadata must not be a hardlink: ' + relative)


def write_json(root, relative, value):
    path = writable(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    os.replace(temporary, path)
    return path


def read_json(path, label):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(label + ' must be a regular file')
    if path.exists() and path.stat().st_nlink != 1:
        raise ValueError(label + ' must not be a hardlink')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('Malformed ' + label + ': ' + str(exc))
    if not isinstance(value, dict):
        raise ValueError('Malformed ' + label)
    return value


def default_config(project_id, mode='observe'):
    """Bounded, portable, intentionally reviewable; no machine paths or client history."""
    if mode not in MODES:
        raise ValueError('Policy mode must be one of: ' + ', '.join(MODES))
    return {
        'schema_version': SCHEMA_VERSION,
        'project_id': project_id,
        'tooling': {'vendor': 'Rumuze', 'tool': 'Crewloom', 'role': 'tooling', 'owns_client_code': False},
        'policy': {'mode': mode, 'managed_lifecycle': mode == 'enforced', 'evidence_only': False},
        'source_roots': ['.'],
        'exclude': ['.git', '.crewloom', '.agents', '.claude', 'node_modules', 'dist', 'build',
                    '.venv', 'vendor', '__pycache__'],
        'language': 'en',
        'budgets': {'map_bytes': 8192, 'context_bytes': 32768, 'lesson_budget_bytes': 4096,
                    'range_bytes': 8192},
        'host_adapter': {'enabled': False, 'files': ['AGENTS.md']},
    }


def _relative_list(value, label, allow_dot=False):
    if not isinstance(value, list) or not value or len(value) > 64:
        raise ValueError(label + ' must be a nonempty list of at most 64 entries')
    for item in value:
        if not isinstance(item, str) or not item.strip() or '\0' in item:
            raise ValueError(label + ' entries must be nonempty text')
        candidate = Path(item)
        if candidate.is_absolute() or '..' in candidate.parts:
            raise ValueError(label + ' entries must be project-relative without parent traversal')
        if not allow_dot and candidate.parts == ('.',):
            raise ValueError(label + ' entries must name a subdirectory')
    return list(value)


def _budget(value, label, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(label + ' must be an integer from ' + str(low) + ' to ' + str(high))
    return value


def _validate_review(block):
    """Opt-in manual-review policy. An absent block keeps the compatible declared-label mode."""
    if block is None:
        return
    if not isinstance(block, dict) or set(block) - {'mode', 'allow_self_review'}:
        raise ValueError('Policy review needs a mode and allow_self_review')
    if block.get('mode') not in REVIEW_MODES:
        raise ValueError('Policy review mode must be one of: ' + ', '.join(REVIEW_MODES))
    if not isinstance(block.get('allow_self_review'), bool):
        raise ValueError('Policy review allow_self_review must be true or false')
    if block['mode'] == 'label' and block['allow_self_review']:
        raise ValueError('A declared label cannot be the owning role, so allow_self_review only applies to verified mode')


def validate_config(value, root):
    """Strict schema: an unknown or malformed field blocks the project instead of guessing."""
    unknown = set(value) - {'schema_version', 'project_id', 'tooling', 'policy', 'source_roots',
                            'exclude', 'language', 'budgets', 'host_adapter'}
    if unknown:
        raise ValueError('Unknown project configuration fields: ' + ', '.join(sorted(unknown)))
    if value.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Project configuration requires schema_version ' + str(SCHEMA_VERSION))
    project_id = value.get('project_id')
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise ValueError('Project configuration needs an explicit lowercase project_id')
    tooling = value.get('tooling')
    if not isinstance(tooling, dict) or set(tooling) - {'vendor', 'tool', 'role', 'owns_client_code'}:
        raise ValueError('Project configuration needs Crewloom tooling attribution')
    if tooling.get('tool') != 'Crewloom' or tooling.get('role') != 'tooling':
        raise ValueError('Tooling attribution describes the tool, not ownership of client code')
    if not isinstance(tooling.get('vendor'), str) or not tooling['vendor'].strip():
        raise ValueError('Tooling attribution needs a named vendor')
    if tooling.get('owns_client_code') is not False:
        raise ValueError('Tooling attribution must declare owns_client_code false')
    policy = value.get('policy')
    if not isinstance(policy, dict) or set(policy) - {'mode', 'managed_lifecycle', 'evidence_only', 'review'}:
        raise ValueError('Project configuration needs a policy block')
    if policy.get('mode') not in MODES:
        raise ValueError('Policy mode must be one of: ' + ', '.join(MODES))
    for field in ('managed_lifecycle', 'evidence_only'):
        if not isinstance(policy.get(field), bool):
            raise ValueError('Policy field must be true or false: ' + field)
    if policy['mode'] == 'off' and policy['managed_lifecycle']:
        raise ValueError('Policy mode off cannot enable a managed lifecycle')
    if policy['mode'] == 'enforced' and not policy['managed_lifecycle']:
        raise ValueError('Enforced context requires the managed lifecycle to be enabled explicitly')
    _validate_review(policy.get('review'))
    _relative_list(value.get('source_roots'), 'source_roots', allow_dot=True)
    _relative_list(value.get('exclude'), 'exclude')
    if value.get('language') not in LANGUAGES:
        raise ValueError('Project language must be en or ar')
    budgets = value.get('budgets')
    if not isinstance(budgets, dict) or set(budgets) - {'map_bytes', 'context_bytes', 'lesson_budget_bytes',
                                                        'range_bytes'}:
        raise ValueError('Project configuration needs explicit byte budgets')
    _budget(budgets.get('map_bytes'), 'map_bytes', 1024, 65536)
    _budget(budgets.get('context_bytes'), 'context_bytes', 4096, 262144)
    _budget(budgets.get('lesson_budget_bytes'), 'lesson_budget_bytes', 0, 65536)
    # Optional ranges are a navigation hint, so they get their own modest allowance
    # instead of whatever the global context ceiling happens to leave over. A configuration
    # written before this key existed falls back to the map allocation it always implied.
    if 'range_bytes' in budgets:
        _budget(budgets['range_bytes'], 'range_bytes', 0, 65536)
    adapter = value.get('host_adapter')
    if not isinstance(adapter, dict) or set(adapter) - {'enabled', 'files'}:
        raise ValueError('Project configuration needs a host_adapter block')
    if not isinstance(adapter.get('enabled'), bool):
        raise ValueError('host_adapter.enabled must be true or false')
    files = adapter.get('files')
    if not isinstance(files, list) or not files or any(item not in INSTRUCTION_FILES for item in files):
        raise ValueError('host_adapter.files must name ' + ' or '.join(INSTRUCTION_FILES))
    if not adapter['enabled'] and files != ['AGENTS.md']:
        raise ValueError('host_adapter.files needs no entries while the adapter is disabled')
    if adapter['enabled']:
        for name in files:
            path = writable(root, name)
            text = path.read_text(encoding='utf-8') if path.exists() else ''
            if MARKER_START in text and MARKER_END not in text:
                raise ValueError('Unbalanced managed context markers in ' + name)
    for entry in value['source_roots']:
        if entry in ('.', './'):
            continue
        target = no_links(root, entry)
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise ValueError('source_roots entries must be plain directories: ' + entry)
    return value


def load_config(root, config_path=None):
    relative = config_path or CONFIG_NAME
    path = w.safe_path(root, relative)
    if not path.is_file():
        return None, relative
    return validate_config(read_json(path, 'project configuration'), root), relative


def default_mode():
    requested = os.environ.get('CREWLOOM_CONTEXT_MODE')
    return requested if requested in MODES else 'observe'


def _agency_path(agency_root, value, label, problems):
    if not isinstance(value, str) or not value or value.startswith('/') or '\0' in value:
        problems.append(label + ': must be a non-empty relative path')
        return None
    path = (agency_root / value).resolve()
    if agency_root not in path.parents:
        problems.append(label + ': escapes the agency workspace root')
        return None
    return path


def _agency_skill(name, agency_root, project_root, label, problems):
    if not isinstance(name, str) or not PROJECT_ID.fullmatch(name):
        problems.append(label + ': must name an installed role')
        return
    roots = [agency_root, project_root]
    for base in roots:
        for host in ('.agents', '.claude'):
            if (base / host / 'skills' / name / 'SKILL.md').is_file():
                return
    problems.append(label + ': must name an installed role')


def validate_agency_registry(registry, agency_root, project_root, problems=None):
    """Faithful reimplementation of the agency ledger contract; problems accumulate, never guess."""
    problems = problems if problems is not None else []
    if not registry.is_file():
        problems.append('registry: file not found')
        return []
    try:
        data = json.loads(registry.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        problems.append('registry: unreadable (' + str(exc) + ')')
        return []
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION:
        problems.append('registry: schema_version 1 required')
        return []
    if set(data) - {'schema_version', 'projects'}:
        problems.append('registry: unknown top-level fields')
    projects = data.get('projects')
    if not isinstance(projects, list) or not projects:
        problems.append('projects must be a nonempty list')
        return []
    matched = []
    seen = set()
    for index, item in enumerate(projects):
        label = 'projects[' + str(index) + ']'
        if not isinstance(item, dict):
            problems.append(label + ': must be an object')
            continue
        if set(item) - AGENCY_FIELDS:
            problems.append(label + ': unknown fields')
        ident = item.get('id')
        if not isinstance(ident, str) or not PROJECT_ID.fullmatch(ident) or ident in seen:
            problems.append(label + '.id: must be a unique lowercase identifier')
        else:
            seen.add(ident)
        active = _agency_path(agency_root, item.get('active_dir'), label + '.active_dir', problems)
        snapshot = _agency_path(agency_root, item.get('context_snapshot'), label + '.context_snapshot', problems)
        if snapshot is not None and (not snapshot.is_file() or (active and active not in snapshot.parents)):
            problems.append(label + '.context_snapshot: missing or outside its active_dir')
        _agency_skill(item.get('delivery_owner'), agency_root, project_root, label + '.delivery_owner', problems)
        status = item.get('control_status')
        if status not in AGENCY_STATUSES:
            problems.append(label + '.control_status: must be one of ' + ', '.join(AGENCY_STATUSES))
        verified = item.get('last_verified_at')
        if status == 'needs_reconciliation':
            if verified is not None:
                problems.append(label + '.last_verified_at: needs_reconciliation requires null')
        elif not _timestamp(verified):
            problems.append(label + '.last_verified_at: operational state requires ISO-8601')
        if status != 'needs_reconciliation':
            evidence = item.get('state_evidence')
            if not isinstance(evidence, dict):
                problems.append(label + '.state_evidence: required for an operational state')
            else:
                evidence_path = _agency_path(agency_root, evidence.get('path'),
                                             label + '.state_evidence.path', problems)
                if evidence_path is not None:
                    if not evidence_path.is_file() or (active and active not in evidence_path.parents):
                        problems.append(label + '.state_evidence.path: missing or outside its active_dir')
                    elif not evidence_path.stat().st_size:
                        problems.append(label + '.state_evidence.path: is empty')
                    else:
                        recorded = evidence.get('sha256')
                        if not isinstance(recorded, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', recorded):
                            problems.append(label + '.state_evidence.sha256: requires a SHA-256 digest')
                        elif file_digest(evidence_path) != recorded.lower():
                            problems.append(label + '.state_evidence: changed since observation')
                if evidence.get('source_type') not in AGENCY_EVIDENCE_SOURCES:
                    problems.append(label + '.state_evidence.source_type: must be one of '
                                    + ', '.join(AGENCY_EVIDENCE_SOURCES))
                if not _timestamp(evidence.get('observed_at')):
                    problems.append(label + '.state_evidence.observed_at: requires ISO-8601')
        action = item.get('next_action')
        if not isinstance(action, dict):
            problems.append(label + '.next_action: required')
        else:
            _agency_skill(action.get('owner'), agency_root, project_root, label + '.next_action.owner', problems)
            for key in ('output', 'acceptance'):
                if not isinstance(action.get(key), str) or not action[key].strip():
                    problems.append(label + '.next_action.' + key + ': required')
        if active is not None and active == project_root and isinstance(ident, str):
            matched.append(item)
    return matched


def _timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return True


def run_agency_validator(validator, registry, timeout=60):
    """Run an explicitly selected agency validator; a failure blocks rather than degrades."""
    script = Path(validator).resolve()
    if not script.is_file():
        raise ValueError('Agency validator not found: ' + str(validator))
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('Agency project-control validator blocked: '
                         + ' '.join((result.stdout or result.stderr).split())[:400])
    return {'validator': str(script), 'exit_code': 0}


def agency_registry(registry, agency_root, project_root):
    """Validate the existing ledger, then read this project's control status from it."""
    if isinstance(agency_root, Path):
        agency_root = str(agency_root)
    if not isinstance(agency_root, str) or not agency_root.strip():
        raise ValueError('Explicit agency workspace root is required to resolve registry paths')
    base = Path(agency_root).resolve()
    if not base.is_dir():
        raise ValueError('Agency workspace root does not exist: ' + agency_root)
    path = Path(registry) if isinstance(registry, Path) else None
    path = path.resolve() if path and path.is_absolute() else (base / str(registry)).resolve()
    problems = []
    matched = validate_agency_registry(path, base, project_root, problems)
    if problems:
        raise ValueError('Agency project-control registry is invalid: ' + '; '.join(problems[:6]))
    if not matched:
        raise ValueError('This project root is not registered in the agency project-control registry')
    entry = matched[0]
    status = entry['control_status']
    return {'registered': True, 'source': str(path), 'project_id': entry['id'],
            'delivery_owner': entry.get('delivery_owner'), 'control_status': status,
            'evidence_only': status in AGENCY_EVIDENCE_ONLY,
            'context_snapshot': entry.get('context_snapshot'),
            'next_action': entry.get('next_action'), 'last_verified_at': entry.get('last_verified_at')}


def resolve_identity(root, config, requested, registry_path, agency_root=None, validator=None, bound=None):
    """One explicit identity; conflicting sources are reported instead of guessed."""
    registry = None
    if registry_path:
        if validator:
            run_agency_validator(validator, registry_path)
        registry = agency_registry(registry_path, agency_root, root)
    if config is not None and requested and config['project_id'] != requested:
        raise ValueError('Requested project identity does not match the portable configuration')
    candidates = {value for value in (config.get('project_id') if config else None, requested,
                                      (bound or {}).get('project_id'),
                                      registry['project_id'] if registry else None) if value}
    if not candidates:
        raise ValueError('Explicit project identity is required: supply --project-id or --agency-registry')
    if len(candidates) > 1:
        raise ValueError('Conflicting project identity: ' + ', '.join(sorted(candidates)))
    project_id = candidates.pop()
    if not PROJECT_ID.fullmatch(project_id):
        raise ValueError('Project identity must be an explicit lowercase identifier')
    return project_id, registry


def load_binding(root, required=True, allow_moved=False):
    path = w.safe_path(root, BINDING_RELATIVE, internal=True)
    if not path.exists():
        if required:
            raise ValueError('Project is not bound; run crewloom project enter first')
        return None
    value = read_json(path, 'local project binding')
    if value.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Local binding requires schema_version ' + str(SCHEMA_VERSION))
    if value.get('project_root') != str(root) and not allow_moved:
        raise ValueError('Local binding belongs to another checkout; relink it explicitly with crewloom project rebind')
    for field, pattern in (('project_id', PROJECT_ID), ('checkout_id', re.compile(r'[0-9a-f]{32}$'))):
        if not isinstance(value.get(field), str) or not pattern.fullmatch(value[field]):
            raise ValueError('Local binding needs a valid ' + field)
    if not isinstance(value.get('relocations'), list):
        raise ValueError('Malformed local binding relocation history')
    return value


def ensure_layout(root):
    folder = root / '.crewloom'
    if folder.is_symlink():
        raise ValueError('.crewloom may not be a symlink')
    folder.mkdir(exist_ok=True)
    for name in LOCAL_DIRS:
        directory = folder / name
        if directory.is_symlink():
            raise ValueError('.crewloom/' + name + ' may not be a symlink')
        directory.mkdir(exist_ok=True)
    return folder


def library_source(root):
    """Only the actual distributed toolkit may carry public role-memory templates."""
    import crewloom_resources
    root = Path(root).resolve()
    source = crewloom_resources.distribution_root().resolve()
    if root == source:
        return True
    # A genuine linked checkout of the same toolkit repository also holds public templates.
    if not all((folder / '.git').exists() and not (folder / '.git').is_symlink()
               for folder in (root, source)):
        return False
    import repo_map
    def common(folder):
        result = subprocess.run(['git', '-C', str(folder), 'rev-parse', '--git-common-dir'],
                                env=repo_map.git_environment(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10)
        if result.returncode:
            return None
        return (folder / os.fsdecode(result.stdout).strip()).resolve()
    reference = common(source)
    return reference is not None and common(root) == reference


def private_project_path(relative, role_memory=False):
    """Classify reserved local state by path, never by reading customer file bodies."""
    parts = Path(relative).parts
    if any(part.casefold() in ('.crewloom', '.venv', '__pycache__', 'node_modules', '.next', 'build', 'dist')
           or part.casefold().endswith('.egg-info') for part in parts):
        return True
    name = parts[-1].casefold() if parts else ''
    if name.endswith(('.pyc', '.pyo', '.log', '.tsbuildinfo')):
        return True
    if name == '.env' or (name.startswith('.env.') and name not in ('.env.example', '.env.template')):
        return True
    if role_memory:
        if len(parts) >= 5 and parts[0] in ('.agents', '.claude') and parts[1] == 'skills' and parts[3] == 'brain':
            return True
        if tuple(parts) in (('.codex', 'hooks.json'), ('.claude', 'settings.json'),
                            ('.claude', 'settings.local.json'), ('.opencode', 'plugins', 'crewloom-lifecycle.js')):
            return True
    return False


def tracked_private_paths(root, role_memory=False, private_files=()):
    """Inspect this exact Git index, including forced additions; never use a parent index."""
    root = Path(root).resolve()
    marker = root / '.git'
    if marker.is_symlink():
        raise ValueError('Project Git marker may not be a symlink')
    if not marker.exists():
        return []  # A plain application directory/archive has no index to publish.
    import repo_map
    environment = repo_map.git_environment()
    def git(arguments):
        result = subprocess.run(['git', '-C', str(root), *arguments], env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        if result.returncode:
            raise ValueError('Cannot verify the selected project Git index')
        if len(result.stdout) > 8 * 1024 * 1024:
            raise ValueError('Project Git index exceeds privacy scan budget')
        return result.stdout
    top = Path(os.fsdecode(git(['rev-parse', '--show-toplevel'])).strip()).resolve()
    if top != root:
        raise ValueError('Git index does not belong to the canonical project root')
    names = git(['ls-files', '--cached', '-z']).split(b'\0')
    if len(names) > 50001:
        raise ValueError('Project Git index exceeds privacy path budget')
    exact = set(private_files)
    private = {os.fsdecode(name) for name in names if name and
               (os.fsdecode(name) in exact or private_project_path(os.fsdecode(name), role_memory))}
    # Honor arbitrary project-owned private paths too: forced/stale ignored index entries fail.
    ignored = git(['ls-files', '--cached', '--ignored', '--exclude-standard', '-z']).split(b'\0')
    private.update(os.fsdecode(name) for name in ignored if name)
    return sorted(private)


def ignore_local_state(root, role_memory=False):
    """Append a final owned ignore block; preserve user rules and private local files."""
    path = writable(root, '.gitignore')
    original = path.read_text(encoding='utf-8') if path.exists() else ''
    if len(original.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Project ignore file exceeds privacy policy budget')
    patterns = [LOCAL_IGNORE, '.env', '.env.*', '!.env.example', '!.env.template',
                '__pycache__/', '*.pyc', '*.pyo', '*.log',
                '.venv/', 'node_modules/', '.next/', 'build/', 'dist/', '*.egg-info/', '*.tsbuildinfo']
    if role_memory:
        patterns += ['/.agents/skills/*/brain/', '/.claude/skills/*/brain/',
                     '/.codex/hooks.json', '/.claude/settings.json', '/.claude/settings.local.json',
                     '/.opencode/plugins/crewloom-lifecycle.js']
    block = '# Crewloom project-local privacy\n' + '\n'.join(patterns) + '\n'
    # Existing negations cannot re-include our reserved state because the owned block is last.
    if original.endswith(block):
        return None
    candidate = original + ('' if not original or original.endswith('\n') else '\n') + block
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(candidate)
        writable(root, '.gitignore')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return '.gitignore'


def privacy_report(root):
    """Read-only publication preflight for a selected project, suitable for its CI/hook."""
    root = project_root(root)
    local_memory = not library_source(root)
    private = tracked_private_paths(root, role_memory=local_memory)
    checked = (root / '.git').exists()
    probes = ['.crewloom/privacy-check.json', '.env.local', '__pycache__/privacy-check.pyc',
              'node_modules/privacy-check/index.js', 'dist/privacy-check.json']
    if local_memory:
        probes += ['.agents/skills/privacy-check/brain/COMPLETED.md',
                   '.claude/skills/privacy-check/brain/COMPLETED.md', '.codex/hooks.json',
                   '.claude/settings.json', '.opencode/plugins/crewloom-lifecycle.js']
    missing, portable_missing, local_only, unmerged, nested = [], [], [], [], []
    if checked:
        import repo_map
        for name in probes:
            result = subprocess.run(['git', '-C', str(root), 'check-ignore', '--no-index', '-q', '--', name],
                                    env=repo_map.git_environment(), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=10)
            if result.returncode == 1:
                missing.append(name)
            elif result.returncode != 0:
                raise ValueError('Cannot verify selected project ignore policy')
        policy = staged_ignore_policy(root, probes)
        portable_missing = policy['missing']
        unmerged, nested = policy['unmerged'], policy['nested_negations']
        local_only = [name for name in probes if name in portable_missing and name not in missing]
    ready = checked and not private and not missing and not portable_missing and not unmerged and not nested
    return {'project_root': str(root), 'status': 'ready' if ready else 'not_ready',
            'git_index_checked': checked, 'tracked_private_paths': private, 'missing_ignore_probes': missing,
            'missing_portable_ignore_probes': portable_missing, 'local_only_ignore_probes': local_only,
            'unmerged_ignore_files': unmerged, 'nested_negation_gaps': nested,
            'role_memory_private': local_memory,
            'scope': 'Reserved project-local paths and representative ignore rules evaluated from the staged '
                     'ignore files only; .git/info/exclude, global excludes and unstaged edits do not count. '
                     'Not a content-secret scanner or an OS sandbox'}


def staged_ignore_policy(root, probes):
    """Evaluate the ignore files in the selected project's index, and only those.

    Returns `missing` (root probes not ignored), `unmerged` (ignore files with conflict stages,
    whose effective content is undefined) and `nested_negations` (private names that a staged
    nested ignore file re-includes under its own directory). Staged blobs are rebuilt at their
    own paths inside a scratch repository with system/global Git configuration disabled, so
    nested rules and negations are honoured while `.git/info/exclude`, `core.excludesFile` and
    unstaged working-tree edits cannot contribute. Index and working tree are never touched."""
    import repo_map
    entries = repo_map.git(root, ['ls-files', '--stage', '-z']).split(b'\0')
    staged, unmerged = {}, set()
    for entry in entries:
        if not entry:
            continue
        meta, _, name = entry.decode('utf-8', 'surrogateescape').partition('\t')
        mode, blob, stage = meta.split()
        if mode == '120000' or (name != '.gitignore' and not name.endswith('/.gitignore')):
            continue
        if stage != '0':
            unmerged.add(name)
        else:
            staged[name] = blob
    with tempfile.TemporaryDirectory(prefix='crewloom-staged-ignore-') as scratch:
        scratch = Path(scratch)
        env = repo_map.git_environment()
        env.update({'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                    'HOME': str(scratch), 'XDG_CONFIG_HOME': str(scratch)})
        subprocess.run(['git', '-C', str(scratch), 'init', '-q'], env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        for name, blob in staged.items():
            if name in unmerged:
                continue
            target = scratch / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(repo_map.git(root, ['cat-file', 'blob', blob]))

        def evaluate(base):
            def ignored(name):
                result = subprocess.run(['git', '-C', str(base), 'check-ignore', '--no-index', '-q', '--', name],
                                        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                if result.returncode not in (0, 1):
                    raise ValueError('Cannot verify staged project ignore policy')
                return result.returncode == 0
            return ignored
        ignored = evaluate(scratch)
        missing = [name for name in probes if not ignored(name)]
        nested = []
        if any(name != '.gitignore' and name not in unmerged for name in staged):
            # Baseline: the same root policy without any nested file. A nested gap is a private name
            # the root policy ignores there but a staged nested ignore file re-includes.
            baseline_root = scratch / '.baseline'
            baseline_root.mkdir()
            subprocess.run(['git', '-C', str(baseline_root), 'init', '-q'], env=env, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if '.gitignore' in staged and '.gitignore' not in unmerged:
                (baseline_root / '.gitignore').write_bytes((scratch / '.gitignore').read_bytes())
            baseline = evaluate(baseline_root)
            for name in sorted(staged):
                folder = name[:-len('.gitignore')]
                if not folder or name in unmerged:
                    continue
                nested += [folder + probe for probe in probes
                           if baseline(folder + probe) and not ignored(folder + probe)]
        return {'missing': missing, 'unmerged': sorted(unmerged), 'nested_negations': nested}


def bootstrap(root, project_id=None, config_path=None, registry_path=None, mode=None,
              agency_root=None, agency_validator=None):
    """Preflight everything, then create only what is missing; existing metadata is validated."""
    config, relative = load_config(root, config_path)
    binding = load_binding(root, required=False)
    project_id, registry = resolve_identity(root, config, project_id, registry_path, agency_root,
                                            agency_validator, binding)
    if config is None:
        config = validate_config(default_config(project_id, mode or default_mode()), root)
    elif project_id != config['project_id']:
        raise ValueError('Requested project identity does not match the portable configuration')
    local_memory = not library_source(root)
    private = tracked_private_paths(root, role_memory=local_memory)
    if private:
        raise ValueError('Private project data is already tracked; preserve local files and remove '
                         'them from this project index before entry: ' + ', '.join(private[:20]))
    writable(root, '.gitignore')
    preflight(root, [relative, BINDING_RELATIVE] + [item for item in METADATA_PATHS if item != relative])
    if binding is not None and binding['project_id'] != project_id:
        raise ValueError('Local binding identity does not match the requested project')
    created = []
    ignored = ignore_local_state(root, role_memory=local_memory)
    if ignored:
        created.append(ignored)
    if not (root / relative).is_file():
        write_json(root, relative, config)
        created.append(relative)
    if binding is None:
        config_sha = digest(json.dumps(config, sort_keys=True, ensure_ascii=False).encode())
        binding = {'schema_version': SCHEMA_VERSION, 'project_id': project_id,
                   'checkout_id': uuid.uuid4().hex, 'project_root': str(root),
                   'config_path': relative, 'config_sha256': config_sha,
                   'created_at': now(), 'relocations': []}
        write_json(root, BINDING_RELATIVE, binding)
        created.append(BINDING_RELATIVE)
    else:
        config_sha = digest(json.dumps(config, sort_keys=True, ensure_ascii=False).encode())
        if binding.get('config_sha256') != config_sha:
            write_json(root, BINDING_RELATIVE, dict(binding, config_sha256=config_sha))
    ensure_layout(root)
    return {'config': config, 'config_path': relative, 'binding': binding, 'created': created,
            'registry': registry, 'roles': installed_roles(root),
            'instructions_preserved': [name for name in INSTRUCTION_FILES if (root / name).is_file()]}


def installed_roles(root):
    """Existing installed role memory is reused through the selector, never migrated or replaced."""
    found = {}
    for host in ('.agents', '.claude'):
        directory = root / host / 'skills'
        for guide in sorted(directory.glob('*/SKILL.md')) if directory.is_dir() else []:
            found.setdefault(guide.parent.name, []).append(str(guide.relative_to(root)))
    return found



def role_acceptance(root, role):
    """Resolve role acceptance from current scoped executor evidence, never a self-reported exit code.

    Dashboard schema1 command/pass records remain historical attestations. Schema2
    binds role/project/checkout and existing workflow references; no command is run.
    """
    try:
        root = project_root(root)
        if not isinstance(role, str) or not PROJECT_ID.fullmatch(role):
            raise ValueError('Invalid role identifier')
        binding = load_binding(root)
        path = w.safe_path(root, '.crewloom/acceptance/' + role + '.json', internal=True)
        if not path.is_file() or path.stat().st_size > 8192:
            raise ValueError('Missing or oversized role acceptance')
        value = read_json(path, 'role acceptance')
        if value.get('schema_version') != 2 or value.get('role') != role or \
                value.get('project_id') != binding['project_id'] or value.get('checkout_id') != binding['checkout_id']:
            raise ValueError('Acceptance identity is not current')
        references = value.get('references')
        if not isinstance(references, list) or not 1 <= len(references) <= 16:
            raise ValueError('Acceptance needs 1..16 executed references')
        import project_lessons
        evidence = project_lessons.executor_evidence(root, references, binding, 'Role acceptance')
        for item in evidence:
            state = read_json(w.safe_path(root, '.crewloom/workflows/' + item['workflow'] + '/state.json', internal=True), 'workflow evidence')
            if state['steps'][item['step']].get('role') != role:
                raise ValueError('Acceptance step belongs to another role')
        return {'verified': bool(evidence) and all(item['passed'] for item in evidence),
                'basis': 'current executor references and artifact hashes; tested scope only'}
    except (ValueError, OSError, KeyError, TypeError):
        return {'verified': False, 'basis': 'missing, stale, unscoped or self-reported acceptance'}



def task_acceptance(root, task_id):
    """Recheck a completed task's recorded executor references against current artifacts."""
    try:
        root = project_root(root)
        if not isinstance(task_id, str) or not PROJECT_ID.fullmatch(task_id):
            raise ValueError('Invalid task identifier')
        binding = load_binding(root)
        state = task_state(root, task_id)
        if not state or state['status'] != 'complete' or state.get('project_root') != str(root) or \
                state.get('project_id') != binding['project_id'] or state.get('checkout_id') != binding['checkout_id']:
            raise ValueError('Task identity or completion is not current')
        checks = state.get('verification') or []
        if not isinstance(checks, list) or not 1 <= len(checks) <= 64:
            raise ValueError('Task needs bounded executor references')
        references = [{key: value[key] for key in ('workflow', 'step', 'scope') if key in value}
                      for value in checks if isinstance(value, dict)]
        import project_lessons
        evidence = project_lessons.executor_evidence(root, references, binding, 'Current task acceptance')
        return {'verified': len(evidence) == len(checks) and all(value['passed'] for value in evidence),
                'basis': 'current executor references and artifact hashes; historical state preserved'}
    except (ValueError, OSError, KeyError, TypeError):
        return {'verified': False, 'basis': 'missing, stale, unscoped or self-reported task acceptance'}


def task_state(root, task_id):
    path = w.safe_path(root, '.crewloom/tasks/' + task_id + '/state.json', internal=True)
    if not path.exists():
        return None
    value = read_json(path, 'project task state')
    if value.get('schema_version') != SCHEMA_VERSION or value.get('task_id') != task_id:
        raise ValueError('Malformed project task state: ' + task_id)
    if value.get('status') not in TASK_STATES:
        raise ValueError('Malformed project task status')
    return value


def save_task_state(root, state):
    return write_json(root, '.crewloom/tasks/' + state['task_id'] + '/state.json', state)


def reservation(root):
    path = w.safe_path(root, RESERVATION_RELATIVE, internal=True)
    if not path.exists():
        return None
    value = read_json(path, 'project task reservation')
    if (value.get('schema_version') != SCHEMA_VERSION or value.get('project_root') != str(root)
            or not PROJECT_ID.fullmatch(str(value.get('project_id', '')))
            or not PROJECT_ID.fullmatch(str(value.get('task_id', '')))):
        raise ValueError('Invalid or cross-project task reservation')
    return value


def reserve(root, binding, task_id, owner):
    """Same root, same lock, same reservation discipline as managed workflows, both directions."""
    current = reservation(root)
    if current and current['task_id'] != task_id:
        raise ValueError('Project already has an active context task: ' + current['task_id'])
    pending = w.active_workflow(root)
    if pending and pending['workflow'] != task_id:
        raise ValueError('Project has an unfinished managed workflow: ' + pending['workflow']
                         + '; finish or cancel it before entering another context task')
    write_json(root, RESERVATION_RELATIVE, {'schema_version': SCHEMA_VERSION, 'project_root': str(root),
                                            'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
                                            'task_id': task_id, 'owner': owner, 'reserved_at': now()})
    return reservation(root)


def preflight_ownership(root, task_id):
    """Read-only ownership check, before any snapshot, instruction or task record is written.

    A task that will be refused for conflicting ownership must not alter the owner's
    context, instruction or reservation files.
    """
    current = reservation(root)
    if current and current['task_id'] != task_id:
        raise ValueError('Project already has an active context task: ' + current['task_id'])
    pending = w.active_workflow(root)
    if pending and pending['workflow'] != task_id:
        raise ValueError('Project has an unfinished managed workflow: ' + pending['workflow']
                         + '; finish or cancel it before entering another context task')
    return current


def release(root, task_id):
    current = reservation(root)
    if current and current['task_id'] == task_id:
        w.safe_path(root, RESERVATION_RELATIVE, internal=True).unlink(missing_ok=True)


def instruction_block(config, binding):
    """A bounded managed reference; the host still decides whether to read it.

    Every command is one runnable shell line: the exit evidence is a real shell-quoted
    JSON argument, not text that loses its double quotes or swallows the next line.
    """
    command = shutil.which('crewloom') or 'crewloom'
    evidence = shlex.quote(json.dumps([{'workflow': '<managed-workflow-id>',
                                        'step': '<acceptance-step-id>',
                                        'scope': '<acceptance command step>'}]))
    return (
        MARKER_START + '\n'
        '## Crewloom managed project context\n\n'
        'This project enables Crewloom project context (' + config['policy']['mode'] + ' mode).\n'
        '- Project ID: `' + binding['project_id'] + '`; checkout ID: `' + binding['checkout_id'] + '`.\n'
        '- Entry: `' + command + ' project enter --project <project-root> --project-id '
        + binding['project_id'] + ' --task-id <task-id> --role <installed-role> '
        '--criteria <criteria.md> --seed <seed-path> --source <source-path>`.\n'
        '- Entry needs `--task-id` and `--role`; add `--criteria`, `--seed` and `--source` for this task.\n'
        '- Existing footprint: the same command refreshes navigation; it never rewrites this block or role memory.\n'
        '- Exit: `' + command + ' project finish --project <project-root> --project-id '
        + binding['project_id'] + ' --task-id <task-id> --evidence ' + evidence + '`.\n'
        '- Finish requires recorded executor evidence. `--verification` is only an attestation and '
        'keeps the task awaiting verification.\n'
        '- Lifecycle here is instruction-assisted. Opening a folder does not invoke anything by itself.\n'
        '- Never change global host settings, never guess project identity, never claim executed checks.\n'
        + MARKER_END + '\n')


def update_instructions(root, config, binding):
    """Idempotent managed reference inside authorized files only; original text is preserved."""
    if not config['host_adapter']['enabled']:
        return []
    block = instruction_block(config, binding)
    if len(block.encode()) > MAX_INSTRUCTION_BYTES:
        raise ValueError('Managed instruction reference exceeds its own budget')
    updated = []
    for name in config['host_adapter']['files']:
        path = writable(root, name)
        original = path.read_text(encoding='utf-8') if path.exists() else ''
        if MARKER_START in original and MARKER_END in original:
            head = original.split(MARKER_START)[0]
            tail = original.split(MARKER_END, 1)[1]
            candidate = (head.rstrip('\n') + '\n\n' if head.strip() else '') + block + tail.lstrip('\n')
            candidate = candidate.rstrip('\n') + '\n'
        elif MARKER_START in original or MARKER_END in original:
            raise ValueError('Unbalanced managed context markers in ' + name)
        else:
            candidate = (original.rstrip('\n') + '\n\n' if original.strip() else '') + block
        if candidate != original:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(candidate)
            os.replace(temporary, path)
        updated.append(name)
    return updated


def lifecycle_for(config):
    mode = config['policy']['mode']
    if mode == 'off':
        return 'manual'
    return 'managed-runner' if config['policy']['managed_lifecycle'] else 'instruction-assisted'


def record_metrics(state, values):
    metrics = state.setdefault('metrics', {})
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool):
            metrics[key] = value
        elif isinstance(value, int):
            metrics[key] = metrics.get(key, 0) + value if isinstance(metrics.get(key), int) else value
        elif isinstance(value, dict):
            metrics[key] = {**(metrics.get(key) or {}), **{k: v for k, v in value.items() if v is not None}}
        else:
            metrics[key] = value
    return metrics


def read_criteria(root, criteria_path):
    if not criteria_path:
        return []
    path = w.safe_path(root, criteria_path)
    if path.is_symlink() or path.stat().st_nlink != 1:
        raise ValueError('Acceptance criteria must be a regular file without hardlinks')
    text = path.read_text(encoding='utf-8')
    return [line.strip() for line in text.splitlines() if line.strip()][:64]


def enter(root, project_id=None, task_id=None, role=None, config_path=None, registry_path=None,
          criteria_path=None, seeds=(), language=None, sources=(), hold_lock=True,
          agency_root=None, agency_validator=None):
    """Idempotent entry: create a missing footprint, refresh an existing one, reserve the root."""
    root = project_root(root)
    if not isinstance(task_id, str) or not PROJECT_ID.fullmatch(task_id):
        raise ValueError('Explicit kebab-case --task-id is required; chat context is not task identity')
    if not isinstance(role, str) or not PROJECT_ID.fullmatch(role):
        raise ValueError('Explicit kebab-case --role is required')
    no_links(root, '.crewloom')
    with (w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True) if hold_lock else _held()):
        state = bootstrap(root, project_id, config_path, registry_path, None, agency_root, agency_validator)
        config, binding, registry = state['config'], state['binding'], state['registry']
        interrupted = reconcile(root)
        previous = task_state(root, task_id)
        if previous and previous.get('status') == 'complete':
            return {'status': 'complete', 'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
                    'project_root': str(root), 'task_id': task_id, 'role': role,
                    'policy_mode': config['policy']['mode'], 'lifecycle': previous['lifecycle'],
                    'evidence_only': bool(previous.get('evidence_only')),
                    'created': [], 'instructions_updated': [], 'reentered_complete': True,
                    'instructions_preserved': state['instructions_preserved'],
                    'context': previous.get('context'), 'verified': previous.get('verified'),
                    'verification': previous.get('verification', []), 'metrics': previous.get('metrics', {}),
                    'roles': sorted(state['roles']), 'recovered_publications': [],
                    'instruction': 'This task was already finalized; its evidence and context are unchanged.'}
        evidence_only = bool(registry and registry['evidence_only']) or config['policy']['evidence_only']
        if evidence_only and config['policy']['mode'] == 'enforced':
            raise ValueError('needs_reconciliation allows evidence gathering only; enforced context is not authorized')
        preflight_ownership(root, task_id)
        recovered_publications = reconcile_publications(root)
        criteria = read_criteria(root, criteria_path)
        # The bounded managed block is written before the freeze, never after: a generation
        # that hashes the pre-write instructions file is stale the moment entry returns.
        instructions = update_instructions(root, config, binding)
        context = None
        if config['policy']['mode'] != 'off':
            import project_context as pc
            context, written = pc.freeze(root, pc.snapshot(root, binding, task_id, role, config,
                                                           criteria, seeds, language, sources,
                                                           criteria_path=criteria_path))
        reserve(root, binding, task_id, 'project-context')
        record = dict(previous or {})
        record.update({'schema_version': SCHEMA_VERSION, 'task_id': task_id, 'role': role,
                       'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
                       'project_root': str(root), 'policy_mode': config['policy']['mode'],
                       'lifecycle': lifecycle_for(config), 'status': 'active',
                       'evidence_only': evidence_only,
                       'registry_control_status': registry['control_status'] if registry else None,
                       'created_at': (previous or {}).get('created_at') or now(),
                       'updated_at': now(), 'criteria': criteria, 'interrupted_tasks': interrupted,
                       'recovered_publications': recovered_publications})
        if context:
            record['context'] = {'generation': context['generation'], 'sha256': context['sha256'],
                                 'semantic_sha256': context['semantic_sha256'],
                                 'path': str(Path('.crewloom/context') / (task_id + '.json')),
                                 'written': written, 'bytes': context['bytes'],
                                 'omissions': len(context['omissions'])}
            record_metrics(record, {'context_bytes': context['bytes'],
                                    'omissions': len(context['omissions']),
                                    'lessons_included': len(context['lessons'])})
        elif record.get('context'):
            record['context_before_disable'] = record.pop('context')
            record['context'] = None
        save_task_state(root, record)
    return {'status': record['status'], 'project_id': binding['project_id'], 'checkout_id': binding['checkout_id'],
            'project_root': str(root), 'task_id': task_id, 'role': role, 'policy_mode': config['policy']['mode'],
            'lifecycle': record['lifecycle'], 'evidence_only': record['evidence_only'],
            'created': state['created'], 'instructions_updated': instructions,
            'instructions_preserved': state['instructions_preserved'], 'context': record.get('context'),
            'omissions': (record.get('context') or {}).get('omissions', 0), 'roles': sorted(state['roles']),
            'interrupted_tasks': interrupted, 'recovered_publications': recovered_publications}


def finish(root, project_id, task_id, changed=(), verification=(), role=None, lessons=(), hold_lock=True,
           evidence=()):
    """Finalization needs recorded executor evidence; operator JSON stays an attestation."""
    root = project_root(root)
    binding = load_binding(root)
    if binding['project_id'] != project_id:
        raise ValueError('Project identity does not match the local binding')
    with (w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True) if hold_lock else _held()):
        state = task_state(root, task_id)
        if state is None:
            raise ValueError('Unknown project task: ' + task_id)
        if state['project_root'] != str(root) or state['checkout_id'] != binding['checkout_id']:
            raise ValueError('Task state belongs to another root or checkout')
        if state['status'] in ('complete', 'failed'):
            return _final_report(state, True)
        if state['status'] == 'cancelled':
            raise ValueError('Cancelled task cannot be finalized; enter a new task ID')
        attested = []
        for item in verification:
            if not isinstance(item, dict) or not isinstance(item.get('command'), list) or not item['command']:
                raise ValueError('Verification attestation needs the claimed command list')
            if type(item.get('exit_code')) is not int:
                raise ValueError('Verification attestation needs a claimed integer exit code')
            attested.append({'command': [str(part) for part in item['command']],
                             'claimed_exit_code': item['exit_code'],
                             'scope': str(item.get('scope', 'unstated'))[:200],
                             'attested_by': str(item.get('attested_by', 'operator'))[:100],
                             'kind': 'attestation', 'executed': False, 'recorded_at': now()})
        executed = []
        rejected = []
        if evidence:
            import project_lessons
            try:
                executed = project_lessons.executor_evidence(root, list(evidence), binding, 'Finalization')
            except ValueError as exc:
                rejected.append(str(exc))
        failures = [item for item in executed if not item['passed']]
        config, _ = load_config(root)
        refresh = {'navigation': 'skipped'}
        if config and config['policy']['mode'] != 'off':
            import repo_map
            _, stats = repo_map.build(root, config=config)
            refresh = {'navigation': 'refreshed', 'parsed': stats['parsed'], 'reused': stats['reused'],
                       'files': stats['files'], 'duration_ms': stats['duration_ms'],
                       'graph_complete': stats['graph_complete']}
            record_metrics(state, {'scan_parsed': stats['parsed'], 'scan_reused': stats['reused'],
                                   'scan_duration_ms': stats['duration_ms']})
        recorded = []
        if lessons:
            import project_lessons
            recorded = project_lessons.record_from_task(root, binding, task_id, lessons,
                                                         executed or attested, role=role or state.get('role'))
        record_metrics(state, {'executed_checks': len(executed), 'attestations': len(attested),
                           'executed_checks_passed': sum(1 for item in executed if item['passed']),
                           'lessons_recorded': len(recorded)})
        # An attestation is an operator claim: it can only move the outcome away from success.
        # Only correlated executor evidence completes a task, and a claimed failure fails closed.
        claimed_failures = [item for item in attested if item['claimed_exit_code']]
        if executed and failures:
            outcome = 'failed'
        elif executed:
            outcome = 'complete'
        elif claimed_failures:
            outcome = 'failed'
        else:
            outcome = 'awaiting_verification'
        state.update({'status': outcome, 'updated_at': now(), 'role': role or state.get('role'),
                      'changed_files': sorted({str(item) for item in changed})[:256],
                      'verification': executed, 'attestations': attested,
                      'rejected_evidence': rejected, 'refresh': refresh, 'verified': outcome == 'complete',
                      'lessons': (state.get('lessons') or []) + recorded})
        if outcome in TERMINAL_STATES:
            state['finalized_at'] = now()
        save_task_state(root, state)
        if outcome in TERMINAL_STATES:
            release(root, task_id)
    return _final_report(state, False)


def _final_report(state, idempotent):
    executed = state.get('verification') or []
    return {'status': state['status'], 'task_id': state['task_id'], 'idempotent': idempotent,
            'verified': state.get('verified', False), 'relabelled': False,
            'changed_files': state.get('changed_files', []), 'verification': executed,
            'failed_commands': [item.get('command') or item['workflow'] + '/' + item['step']
                                 for item in executed if not item['passed']]
                            + [item['command'] for item in state.get('attestations', [])
                               if item.get('claimed_exit_code')],
            'attestations': state.get('attestations', []),
            'rejected_evidence': state.get('rejected_evidence', []),
            'lessons': state.get('lessons', []), 'refresh': state.get('refresh'),
            'metrics': state.get('metrics', {}),
            'instruction': 'Only recorded executor evidence completes a task; an attestation alone keeps it awaiting verification.'}


def cancel(root, project_id, task_id, reason, hold_lock=True):
    """Explicit cancellation preserves artifacts, evidence and history."""
    root = project_root(root)
    binding = load_binding(root)
    if binding['project_id'] != project_id:
        raise ValueError('Project identity does not match the local binding')
    with (w.project_lock(w.safe_path(root, '.crewloom', internal=True), reentrant=True) if hold_lock else _held()):
        state = task_state(root, task_id)
        if state is None:
            raise ValueError('Unknown project task: ' + task_id)
        if state['status'] == 'complete':
            raise ValueError('Completed task does not need cancellation')
        if state['status'] == 'cancelled':
            return {'status': 'cancelled', 'task_id': task_id, 'idempotent': True}
        state.update({'status': 'cancelled', 'updated_at': now(), 'cancelled_at': now(),
                      'cancel_reason': str(reason)[:400], 'verified': False})
        save_task_state(root, state)
        release(root, task_id)
    return {'status': 'cancelled', 'task_id': task_id, 'idempotent': False,
            'changed_files': state.get('changed_files', []),
            'instruction': 'Cancellation preserves files, evidence and lesson history; start new work under a new task ID.'}


def reconcile_publications(root):
    """Undo an interrupted grouped publication before this task builds any frozen context.

    Identity and ownership are already proven by `preflight_ownership`, so this is the first
    point at which writing is safe. It runs before the criteria, instruction and context files
    are touched and before the root is reserved, so a half-published group from a writer that
    was killed can never be read as the starting state of a new task or gate its freshness.
    """
    import execution_policy as broker
    return broker.recover(root)


def reconcile(root):
    """Interrupted work is marked incomplete and rebuilt before any reuse."""
    folder = w.safe_path(root, '.crewloom/tasks', internal=True)
    recovered = []
    if not folder.is_dir():
        return recovered
    for path in sorted(folder.glob('*/state.json')):
        value = read_json(path, 'project task state')
        task_id = value.get('task_id')
        if not isinstance(task_id, str) or value.get('project_root') != str(root):
            raise ValueError('Foreign project task state in this checkout: ' + str(path))
        if value.get('status') == 'active' and not (reservation(root) or {}).get('task_id') == task_id:
            value.update({'status': 'interrupted', 'updated_at': now(), 'interrupted_at': now(),
                          'verified': False})
            write_json(root, '.crewloom/tasks/' + task_id + '/state.json', value)
            recovered.append(task_id)
    return recovered


def rebind(root, project_id, reason):
    """Explicit relocation rebinds a moved checkout and rebuilds rebuildable caches."""
    root = project_root(root)
    with w.lock(w.safe_path(root, '.crewloom', internal=True)):
        config, relative = load_config(root)
        binding = load_binding(root, required=False, allow_moved=True)
        if binding is None and config is None:
            raise ValueError('Nothing to rebind: this project has no portable or local identity')
        if config is not None and project_id and config['project_id'] != project_id:
            raise ValueError('Relocation cannot change project identity; create a new project instead')
        if binding is not None and project_id and binding['project_id'] != project_id:
            raise ValueError('Relocation cannot change project identity; create a new project instead')
        preflight(root, list(METADATA_PATHS))
        if binding is None:
            moved = bootstrap(root, binding_project_id(project_id, config))['binding']
            previous_root = None
        else:
            previous_root = binding['project_root']
            config_sha = digest(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()) if config else binding.get('config_sha256')
            write_json(root, BINDING_RELATIVE, dict(
                binding, project_root=str(root), config_sha256=config_sha,
                relocations=[*(binding.get('relocations') or []),
                             {'from': previous_root, 'to': str(root), 'at': now()}][-8:]))
            moved = load_binding(root, required=False)
        removed = []
        for name in ('.crewloom/index', '.crewloom/context'):
            folder = root / name
            if folder.is_symlink():
                raise ValueError(name + ' may not be a symlink')
            if folder.is_dir():
                for path in sorted(folder.rglob('*'), reverse=True):
                    if path.is_file() or path.is_symlink():
                        path.unlink();removed.append(str(path.relative_to(root)))
                    elif path.is_dir():
                        path.rmdir()
                folder.rmdir();removed.append(name)
        reservation_file = w.safe_path(root, RESERVATION_RELATIVE, internal=True)
        if reservation_file.is_file():
            try:
                stale = read_json(reservation_file, 'project task reservation')
            except ValueError:
                stale = {}
            if stale.get('checkout_id') in (moved['checkout_id'], binding['checkout_id'] if binding else None):
                reservation_file.unlink()
        relocated_tasks = []
        task_folder = w.safe_path(root, '.crewloom/tasks', internal=True)
        for path in sorted(task_folder.glob('*/state.json')) if task_folder.is_dir() else []:
            value = read_json(path, 'project task state')
            if value.get('checkout_id') != moved['checkout_id']:
                continue
            value['project_root'] = str(root)
            value['project_root_history'] = (value.get('project_root_history') or [])[-8:] + [
                {'from': previous_root, 'at': now()}]
            write_json(root, '.crewloom/tasks/' + value['task_id'] + '/state.json', value)
            relocated_tasks.append(value['task_id'])
        relocated_lessons = []
        lesson_folder = w.safe_path(root, '.crewloom/lessons', internal=True)
        for path in sorted(lesson_folder.glob('*.json')) if lesson_folder.is_dir() else []:
            value = read_json(path, 'lesson record')
            if value.get('scope', {}).get('project_root') == str(root):
                continue
            if value.get('scope', {}).get('checkout_id') != moved['checkout_id']:
                continue
            value['scope']['project_root'] = str(root)
            value['scope']['project_root_history'] = (value['scope'].get('project_root_history') or [])[-8:] + [
                {'from': previous_root, 'at': now()}]
            value['provenance']['updated_at'] = now()
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
                            encoding='utf-8')
            relocated_lessons.append(value['id'])
        preserved = sorted(installed_roles(root))
        durable = len(list((root / '.crewloom/lessons').glob('*.json'))) if (root / '.crewloom/lessons').is_dir() else 0
        return {'project_id': moved['project_id'], 'checkout_id': moved['checkout_id'], 'project_root': str(root),
                'relocated_from': previous_root, 'rebuilt_caches': removed, 'preserved_role_memory': preserved,
                'durable_lessons_kept': durable, 'relocated_tasks': relocated_tasks,
                'relocated_lessons': relocated_lessons, 'reason': str(reason)[:200],
                'instruction': 'Relocation clears navigation and context caches; durable lessons and role memory are kept.'}


def binding_project_id(project_id, config):
    if project_id:
        return project_id
    if config:
        return config['project_id']
    raise ValueError('Explicit project identity is required for relocation')


def status(root, project_id=None, task_id=None):
    """Read-only inspection: it never claims ownership of a running task."""
    root = project_root(root)
    config, relative = load_config(root)
    binding = load_binding(root, required=False)
    if project_id and config and config['project_id'] != project_id:
        raise ValueError('Project identity does not match the portable configuration')
    tasks = []
    folder = root / '.crewloom/tasks'
    for path in sorted(folder.glob('*/state.json')) if folder.is_dir() else []:
        value = read_json(path, 'project task state')
        if value.get('project_root') != str(root):
            raise ValueError('Foreign project task state in this checkout: ' + str(path))
        tasks.append({'task_id': value['task_id'], 'role': value['role'], 'status': value['status'],
                      'policy_mode': value['policy_mode'], 'lifecycle': value['lifecycle'],
                      'updated_at': value.get('updated_at'), 'context': value.get('context'),
                      'verified': value.get('verified'),
                      'evidence_only': value.get('evidence_only'),
                      'registry_control_status': value.get('registry_control_status'),
                      'omissions': (value.get('context') or {}).get('omissions', 0),
                      'verification_runs': len(value.get('verification') or []),
                      'metrics': value.get('metrics', {})})
    active = reservation(root)
    if task_id and not any(item['task_id'] == task_id for item in tasks):
        raise ValueError('Unknown project task: ' + task_id)
    return {'project_root': str(root), 'config_path': relative if config else None,
            'project_id': binding['project_id'] if binding else (config or {}).get('project_id'),
            'checkout_id': binding['checkout_id'] if binding else None,
            'bound': binding is not None, 'policy_mode': (config or {}).get('policy', {}).get('mode'),
            'lifecycle': lifecycle_for(config) if config else 'manual',
            'host_adapter_enabled': bool((config or {}).get('host_adapter', {}).get('enabled')),
            'host_callbacks_verified': False,
            'source_roots': (config or {}).get('source_roots'),
            'instruction': 'Lifecycle label describes this repository only; host folder-open callbacks are not verified.',
            'reservation': active, 'managed_workflow': w.active_workflow(root),
            'tasks': tasks, 'roles': sorted(installed_roles(root)),
            'lessons': lesson_counts(root), 'rebuildable_caches': cache_state(root)}


def cache_state(root):
    found = {}
    for name in ('.crewloom/index/map.json', '.crewloom/context'):
        path = root / name
        found[name] = path.stat().st_size if path.is_file() else (len(list(path.glob('*.json'))) if path.is_dir() else 0)
    return found


def lesson_counts(root):
    import project_lessons
    counts = {}
    folder = w.safe_path(root, '.crewloom/lessons', internal=True)
    for path in sorted(folder.glob('*.json')) if folder.is_dir() else []:
        try:
            value = read_json(path, 'lesson record')
        except ValueError:
            counts['malformed'] = counts.get('malformed', 0) + 1
            continue
        state = value.get('state', 'unknown')
        counts[state] = counts.get(state, 0) + 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('enter', 'status', 'finish', 'cancel', 'rebind', 'privacy'))
    parser.add_argument('--project', required=True)
    parser.add_argument('--project-id')
    parser.add_argument('--task-id')
    parser.add_argument('--role')
    parser.add_argument('--config')
    parser.add_argument('--agency-registry', help='Explicit agency project-control ledger path')
    parser.add_argument('--agency-root', help='Agency workspace root that ledger paths are relative to')
    parser.add_argument('--agency-validator', help='Explicitly selected agency validator script to run first')
    parser.add_argument('--criteria', help='Project-relative acceptance criteria file')
    parser.add_argument('--seed', action='append', default=[])
    parser.add_argument('--source', action='append', default=[])
    parser.add_argument('--language', choices=('en', 'ar'))
    parser.add_argument('--changed', action='append', default=[])
    parser.add_argument('--verification', help='JSON list of operator attestations {command, exit_code, scope}')
    parser.add_argument('--evidence', help='JSON list of executor evidence references {workflow, step, scope}')
    parser.add_argument('--lesson', action='append', default=[],
                        help='JSON object {issue, remedy, conditions} recorded as a candidate lesson')
    parser.add_argument('--reason')
    args = parser.parse_args(argv)
    try:
        if args.action == 'privacy':
            result = privacy_report(args.project)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['status'] == 'ready' else 2
        if args.action == 'enter':
            result = enter(args.project, args.project_id, args.task_id, args.role, args.config,
                           args.agency_registry, args.criteria, args.seed, args.language, args.source,
                           True, args.agency_root, args.agency_validator)
        elif args.action == 'status':
            result = status(args.project, args.project_id, args.task_id)
        elif args.action == 'finish':
            result = finish(args.project, args.project_id, args.task_id, args.changed,
                            json.loads(args.verification or '[]'),
                            lessons=[json.loads(item) for item in args.lesson],
                            evidence=json.loads(args.evidence or '[]'))
        elif args.action == 'cancel':
            result = cancel(args.project, args.project_id, args.task_id, args.reason or 'operator request')
        else:
            result = rebind(args.project, args.project_id, args.reason or 'operator relocation')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        accepted = {'enter': ('active', 'complete'), 'finish': ('complete',), 'cancel': ('cancelled',),
                    'status': ('bound', None), 'rebind': ('manual', None)}[args.action]
        return 0 if args.action in ('status', 'rebind') or result.get('status') in [item for item in accepted if item] else 2
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
