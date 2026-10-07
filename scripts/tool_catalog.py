#!/usr/bin/env python3
"""Living tool catalog (N04): one machine source for tool contracts, lifecycle and the incremental gate.

`documentation/TOOLS.json` stays the single catalog. Legacy entries (id, skill, path, description,
example_args, dependencies, effect) keep working and are reported as `legacy-unverified`; an entry may
adopt contract version 1 (typed inputs/outputs/errors, capabilities, limits, owner, acceptance, evidence).
This module is pure logic plus a thin CLI: validation, fingerprints, lifecycle decisions, the commit/CI
gate and the generated human view. It does not sandbox anything: declared effects and capabilities are
metadata that the gate checks for shape and the runner checks for lifecycle, not an operating-system
boundary around a host tool.

Lifecycle: draft -> verified (declared acceptance ran, bound to the exact source and contract
fingerprints) -> active (explicit owner activation record). deprecated and retired entries keep their id
and path with a migration note. A changed implementation or contract makes recorded evidence stale.
"""
import argparse
import ast
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import unittest
from pathlib import Path, PurePosixPath

CATALOG_RELATIVE = 'documentation/TOOLS.json'
DOC_RELATIVE = 'documentation/TOOLS.md'
CONTRACT_VERSION = 1
CATALOG_VERSION = 2
PROVENANCE_VERSION = 2
LEGACY_FIELDS = ('id', 'skill', 'path', 'description', 'example_args', 'dependencies', 'effect')
CONTRACT_FIELDS = ('contract_version', 'interface_version', 'owner', 'status', 'inputs', 'outputs', 'errors',
                   'capabilities', 'limits', 'idempotent', 'acceptance', 'evidence', 'activation',
                   'deprecation', 'compat_note')
REQUIRED_CONTRACT = ('interface_version', 'owner', 'status', 'inputs', 'outputs', 'errors', 'capabilities',
                     'limits', 'acceptance')
FINGERPRINTED_CONTRACT = ('interface_version', 'inputs', 'outputs', 'errors', 'capabilities', 'limits',
                          'dependencies', 'effect', 'example_args', 'idempotent', 'acceptance')
EVIDENCE_FIELDS = ('test', 'command', 'exit_code', 'source_sha256', 'contract_sha256', 'support_sha256',
                   'acceptance_sha256', 'counts', 'provenance', 'recorded_at')
COUNT_FIELDS = ('discovered', 'run', 'executed', 'skipped', 'failures', 'errors', 'expected_failures',
                'unexpected_successes')
CATALOG_FIELDS = ('tools', 'catalog_version', 'assets', 'gate_baseline', 'legacy_exceptions')
SNAPSHOTS = ('index', 'commit')
ENTRY_MODES = ('100644', '100755')
STATUSES = ('draft', 'verified', 'active', 'deprecated', 'retired')
RUNNABLE = ('legacy-unverified', 'verified', 'active', 'deprecated')
CAPABILITIES = ('read-project-files', 'write-project-files', 'write-runtime-state', 'git-read', 'process-spawn',
                'network', 'docker', 'model-provider')
VALUE_TYPES = ('string', 'integer', 'number', 'boolean', 'path', 'json', 'text')
ASSET_LISTS = ('internal', 'build', 'migration', 'fixtures')
ID = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
VERSION = re.compile(r'\d+\.\d+\.\d+$')
PARALLEL = re.compile(r'(?:_v\d+|_copy|_new|_old|_backup|_tmp)\.py$')
MAX_ENTRIES = 32
TOOL_ROOT = re.compile(r'^(?:scripts/|\.agents/skills/[^/]+/scripts/)')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


class SnapshotError(ValueError):
    """The artifact state to be judged cannot be established; callers report it, never treat it as clean."""


def _clean_environment():
    return {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}


def _git_run(root, *argv, env=None, binary=False):
    result = subprocess.run(['git', '-C', str(root), *argv], capture_output=True, text=not binary, timeout=60,
                            env=_clean_environment() if env is None else env)
    return result if result.returncode == 0 else None


def _git(root, *argv):
    # A commit hook exports GIT_DIR/GIT_INDEX_FILE for the repository being committed; plain queries observe
    # exactly the checkout they were given (fixtures included), so inherited repository selection is dropped.
    result = _git_run(root, *argv)
    return result.stdout if result is not None else None


class WorkingView:
    """Read-only view of files on disk. Used for execution and evidence recording, which act on the working
    copy; never for the commit/CI gate, which judges a Git snapshot."""
    kind = 'worktree'

    def __init__(self, root):
        self.root = Path(root)
        self._cache = {}
        self.acceptance_required = True
        try:
            import crewloom_resources as resources
            self.acceptance_required = bool(resources.source_checkout())
        except Exception:  # an unresolvable installation keeps the strict default for source trees
            pass

    def _file(self, relative):
        candidate = self.root / relative
        if candidate.is_file():
            return candidate
        try:
            import crewloom_resources as resources
            if self.root.resolve() == Path(resources.distribution_root()).resolve():
                return Path(resources.resolve(relative))
        except Exception:  # an unresolvable installation is reported as a missing file
            pass
        return candidate

    def is_symlink(self, relative):
        return self._file(relative).is_symlink()

    def read(self, relative):
        if relative not in self._cache:
            file = self._file(relative)
            self._cache[relative] = file.read_bytes() if file.is_file() else None
        return self._cache[relative]

    def exists(self, relative):
        return self.read(relative) is not None

    def mode(self, relative):
        file = self._file(relative)
        return ('100755' if os.access(file, os.X_OK) else '100644') if file.is_file() else None


class GitView:
    """Read-only view of one Git snapshot: the staged index or a committed tree. Every read comes from the
    object database, so nothing in the working tree can stand in for it."""

    def __init__(self, root, kind, entries, label):
        self.root, self.kind, self.entries, self.label = Path(root), kind, entries, label
        self.acceptance_required = True
        self._cache = {}

    def exists(self, relative):
        entry = self.entries.get(relative)
        return entry is not None and entry[0] in ENTRY_MODES

    def is_symlink(self, relative):
        entry = self.entries.get(relative)
        return entry is not None and entry[0] == '120000'

    def mode(self, relative):
        entry = self.entries.get(relative)
        return entry[0] if entry else None

    def read(self, relative):
        entry = self.entries.get(relative)
        if entry is None or entry[0] not in ENTRY_MODES:
            return None
        if relative not in self._cache:
            result = _git_run(self.root, 'cat-file', 'blob', entry[1], binary=True)
            if result is None:
                raise SnapshotError('%s: blob %s of %s is unreadable' % (self.label, entry[1][:12], relative))
            self._cache[relative] = result.stdout
        return self._cache[relative]


def _parse_entries(output, staged):
    """{path: (mode, oid)} from `ls-files -s -z` (mode oid stage) or `ls-tree -r -z` (mode type oid)."""
    entries = {}
    for record in output.split(b'\0'):
        if not record:
            continue
        head, _, path = record.partition(b'\t')
        fields = head.decode().split()
        if len(fields) != 3 or not path:
            raise SnapshotError('unparseable Git listing entry')
        if staged:
            mode, oid, stage = fields
            if stage != '0':
                raise SnapshotError('the index has unmerged entries (%s)' % path.decode('utf-8', 'replace'))
        else:
            mode, _, oid = fields
        entries[path.decode('utf-8', 'surrogateescape')] = (mode, oid)
    return entries


def _belongs(root, candidate):
    """True when a GIT_INDEX_FILE inherited from a hook is an index of the selected repository."""
    git_dir = _git(root, 'rev-parse', '--absolute-git-dir')
    common = _git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    if git_dir is None:
        return False
    allowed = [Path(git_dir.strip()).resolve()] + ([Path(common.strip()).resolve()] if common else [])
    inherited_dir = os.environ.get('GIT_DIR')
    if inherited_dir and Path(inherited_dir).resolve() not in allowed:
        return False
    target = Path(candidate).resolve()
    return target.is_file() and any(target == base or base in target.parents for base in allowed)


def index_file_for(root, explicit=None):
    """The index to judge: an explicit custom index, the index a commit hook is using for this repository,
    or the repository's own. A hook variable that points at another repository is ignored."""
    chosen = explicit or os.environ.get('CREWLOOM_TOOL_GATE_INDEX')
    if chosen:
        path = Path(chosen).resolve()
        if not path.is_file():
            raise SnapshotError('the selected index file does not exist: %s' % chosen)
        return str(path)
    inherited = os.environ.get('GIT_INDEX_FILE')
    if inherited and _belongs(root, inherited):
        return str(Path(inherited).resolve())
    return None


def open_snapshot(root, kind='index', rev='HEAD', index_file=None):
    """GitView of the staged index (commit hook) or of the committed tree `rev` (CI). Raises SnapshotError."""
    if kind not in SNAPSHOTS:
        raise SnapshotError('unknown snapshot %r (supported: %s)' % (kind, ', '.join(SNAPSHOTS)))
    if kind == 'commit':
        if _git(root, 'rev-parse', '--verify', rev + '^{commit}') is None:
            raise SnapshotError('commit snapshot %s cannot be resolved' % rev)
        result = _git_run(root, 'ls-tree', '-r', '-z', '--full-tree', rev, binary=True)
        if result is None:
            raise SnapshotError('commit snapshot %s cannot be listed' % rev)
        return GitView(root, 'commit', _parse_entries(result.stdout, False), 'commit ' + rev)
    chosen = index_file_for(root, index_file)
    environment = _clean_environment()
    if chosen:
        environment['GIT_INDEX_FILE'] = chosen
    result = _git_run(root, 'ls-files', '-s', '-z', env=environment, binary=True)
    if result is None:
        raise SnapshotError('the staged index cannot be listed (not a Git checkout?)')
    return GitView(root, 'index', _parse_entries(result.stdout, True), 'index')


def default_snapshot():
    """CI judges the exact committed tree; a developer or commit hook judges what is staged."""
    chosen = os.environ.get('CREWLOOM_TOOL_GATE_SNAPSHOT')
    if chosen:
        return chosen
    return 'commit' if os.environ.get('GITHUB_ACTIONS') or os.environ.get('CI') == 'true' else 'index'


def load_catalog(root, view=None):
    if view is not None:
        data = view.read(CATALOG_RELATIVE)
        if data is None:
            raise SnapshotError('%s is not part of the %s snapshot' % (CATALOG_RELATIVE, view.kind))
        return json.loads(data.decode('utf-8'))
    return json.loads((Path(root) / CATALOG_RELATIVE).read_text(encoding='utf-8'))


def status_of(item):
    return item.get('status') or 'legacy-unverified'


def implementation_file(root, item, path=None):
    """The file that implements a tool: an explicit path, `root/path`, or, for the live installation only,
    the module the installed distribution maps that path to (a wheel keeps scripts beside site-packages)."""
    if path is not None:
        return Path(path)
    return WorkingView(root)._file(item['path'])


def _digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def implementation_fingerprint(root, item, path=None, view=None):
    if view is not None and path is None:
        return _digest(view.read(item['path']))
    file = implementation_file(root, item, path)
    return hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None


def contract_fingerprint(item):
    return sha({key: item.get(key) for key in FINGERPRINTED_CONTRACT})


def _local_modules(view, relative, tree):
    """Repository files `relative` imports: siblings, the shared scripts directory and relative imports."""
    here = PurePosixPath(relative).parent
    roots = [here, PurePosixPath('scripts')]
    found = set()

    def probe(base, dotted, package_base=False):
        stem = base.joinpath(*dotted.split('.')) if dotted else base
        # Importing pkg.nested.child executes both package initializers before child.py.
        # A namespace package has no initializer; only existing repository files are bound.
        parents = stem.parents if dotted else (stem, *stem.parents)
        for parent in parents:
            if parent == base and not package_base:
                break
            if parent != base and base not in parent.parents:
                continue
            initializer = str(parent / '__init__.py')
            if view.exists(initializer):
                found.add(initializer)
        for candidate in (stem.with_suffix('.py') if dotted else None, stem / '__init__.py'):
            if candidate is not None and view.exists(str(candidate)):
                found.add(str(candidate))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for base in roots:
                    probe(base, alias.name)
        elif isinstance(node, ast.ImportFrom):
            bases = roots
            if node.level:
                bases = [here.joinpath(*(['..'] * (node.level - 1)))]
            for base in bases:
                base = PurePosixPath(os.path.normpath(str(base)))
                if node.module:
                    probe(base, node.module, package_base=bool(node.level))
                for alias in node.names:
                    probe(base, (node.module + '.' if node.module else '') + alias.name,
                          package_base=bool(node.level))
    return found


def support_closure(view, relative):
    """{path: sha256} of the repository modules a tool imports, transitively (the tool itself excluded). Dynamic
    imports and non-Python resources are not followed; that boundary is documented, not hidden."""
    seen, queue = {}, [relative]
    while queue and len(seen) < 256:
        current = queue.pop()
        data = view.read(current)
        if data is None:
            continue
        try:
            tree = ast.parse(data)
        except (SyntaxError, ValueError):
            continue
        for module in sorted(_local_modules(view, current, tree)):
            if module != relative and module not in seen:
                seen[module] = _digest(view.read(module))
                queue.append(module)
    return dict(sorted(seen.items()))


def provenance(item, root, path=None, view=None):
    """What a verification must be bound to right now: implementation, supporting closure, contract, acceptance."""
    view = view or WorkingView(root)
    relative = item.get('path')
    source = implementation_fingerprint(root, item, path, view)
    support = support_closure(view, relative) if source and isinstance(relative, str) else {}
    acceptance = {test: _digest(view.read(test)) for test in item.get('acceptance') or [] if isinstance(test, str)}
    return {'source': source, 'support': support, 'contract': contract_fingerprint(item), 'acceptance': acceptance}


def _record_problem(record, now, test, view):
    if record.get('provenance') != PROVENANCE_VERSION:
        return 'evidence predates provenance %d; record acceptance again' % PROVENANCE_VERSION
    if record.get('exit_code') != 0:
        return 'the recorded run did not succeed'
    if record.get('source_sha256') != now['source']:
        return 'the implementation changed after the evidence was recorded'
    if record.get('contract_sha256') != now['contract']:
        return 'the contract changed after the evidence was recorded'
    recorded = record.get('support_sha256')
    if recorded != now['support']:
        names = sorted(set(now['support']) ^ set(recorded or {}) | {
            name for name in now['support'] if (recorded or {}).get(name) != now['support'][name]})
        return 'supporting implementation changed (%s)' % ', '.join(names[:4])
    current = now['acceptance'].get(test)
    if current is None and view.acceptance_required:
        return 'acceptance file %s is missing from the snapshot' % test
    if current is not None and record.get('acceptance_sha256') != current:
        return 'acceptance %s changed after the evidence was recorded' % test
    counts = record.get('counts')
    if not isinstance(counts, dict) or any(type(counts.get(key)) is not int for key in COUNT_FIELDS):
        return 'the evidence has no structured acceptance counts'
    problem = acceptance_problem(counts)
    return 'the recorded counts are not meaningful passing acceptance (%s)' % problem if problem else None


def verification(item, root, path=None, view=None):
    """{'state': current|stale|missing|not-applicable, 'detail': ...} for an entry's recorded evidence."""
    status = status_of(item)
    if status not in ('verified', 'active'):
        return {'state': 'not-applicable', 'detail': 'status is ' + status}
    evidence = item.get('evidence') or []
    if not evidence:
        return {'state': 'missing', 'detail': 'no evidence is recorded'}
    view = view or WorkingView(root)
    now = provenance(item, root, path, view)
    if now['source'] is None:
        return {'state': 'stale', 'detail': 'the implementation is missing from the snapshot'}
    required = [test for test in item.get('acceptance') or [] if isinstance(test, str)]
    if not required:
        return {'state': 'stale', 'detail': 'no acceptance is declared'}
    for test in required:
        records = [r for r in evidence if isinstance(r, dict) and r.get('test') == test]
        if not records:
            return {'state': 'stale', 'detail': 'required acceptance %s has no recorded evidence' % test}
        problems = [_record_problem(record, now, test, view) for record in records]
        if all(problems):
            return {'state': 'stale', 'detail': problems[-1]}
    return {'state': 'current',
            'detail': 'evidence matches the current source, supporting code, contract and acceptance'}


def acceptance_problem(counts):
    """None when the counts describe meaningful passing acceptance, otherwise the reason it is not."""
    if (any(value < 0 for value in counts.values()) or counts['run'] > counts['discovered']
            or counts['executed'] + counts['skipped'] != counts['run']
            or counts['expected_failures'] > counts['executed']):
        return 'inconsistent test counts'
    if counts['discovered'] < 1:
        return 'no tests were discovered'
    if counts['failures'] or counts['errors'] or counts['unexpected_successes']:
        return 'tests failed or errored'
    if counts['executed'] < 1:
        return 'every test was skipped' if counts['skipped'] else 'no test executed'
    if counts['executed'] - counts['expected_failures'] < 1:
        return 'no test passed (expected failures are not passing acceptance)'
    return None


def execution_decision(item, root, path=None):
    """(allowed, message): the lifecycle check `crewloom run` applies before dispatching a registered tool."""
    status = status_of(item)
    if status not in RUNNABLE:
        return False, 'Tool %s is %s and may not be run' % (item['id'], status)
    if status in ('verified', 'active'):
        state = verification(item, root, path)
        if state['state'] != 'current':
            return False, 'Tool %s has %s verification (%s); record acceptance evidence again' % (
                item['id'], state['state'], state['detail'])
    if status == 'deprecated':
        return True, 'Tool %s is deprecated: %s' % (item['id'], (item.get('deprecation') or {}).get('migration'))
    return True, None


def _bounded_shape(name, value, errors, label, keys):
    if not isinstance(value, dict) or len(value) > MAX_ENTRIES:
        errors.append('%s: %s must be an object of at most %d entries' % (name, label, MAX_ENTRIES))
        return
    for key, spec in value.items():
        if not isinstance(key, str) or not key or not isinstance(spec, dict) or set(spec) - set(keys):
            errors.append('%s: %s.%s must be an object with only %s' % (name, label, key, ', '.join(keys)))
            continue
        if label != 'errors' and spec.get('type') not in VALUE_TYPES:
            errors.append('%s: %s.%s needs a type from %s' % (name, label, key, ', '.join(VALUE_TYPES)))
        if label == 'errors' and (type(spec.get('exit_code')) is not int or not isinstance(spec.get('meaning'), str)):
            errors.append('%s: errors.%s needs an integer exit_code and a meaning' % (name, key))
        if 'required' in spec and type(spec['required']) is not bool:
            errors.append('%s: %s.%s.required must be boolean' % (name, label, key))


def validate_tool(item, root, files=True, view=None):
    name = str(item.get('id'))
    errors = []
    unknown = set(item) - set(LEGACY_FIELDS) - set(CONTRACT_FIELDS)
    if unknown:
        errors.append('%s: unsupported field(s): %s' % (name, ', '.join(sorted(unknown))))
    for key in LEGACY_FIELDS:
        if key not in item:
            errors.append('%s: missing %s' % (name, key))
    if not isinstance(item.get('id'), str) or not ID.match(item.get('id', '')):
        errors.append('%s: id must be a lowercase hyphenated slug' % name)
    path = item.get('path')
    if not isinstance(path, str) or path.startswith('/') or '..' in Path(path).parts:
        errors.append('%s: path must stay inside the repository' % name)
    elif view is not None and not (view.exists(path) and not view.is_symlink(path)):
        errors.append('%s: path %s is not a regular file' % (name, path))
    elif view is None and (not implementation_file(root, item).is_file() or implementation_file(root, item).is_symlink()):
        errors.append('%s: path %s is not a regular file' % (name, path))
    if not isinstance(item.get('dependencies'), list) or any(not isinstance(d, str) for d in item.get('dependencies', [])):
        errors.append('%s: dependencies must be a list of strings' % name)
    declares = any(key in item for key in CONTRACT_FIELDS if key != 'compat_note')  # a note alone is not a contract
    if not declares:
        return errors
    if item.get('contract_version') != CONTRACT_VERSION:
        errors.append('%s: unsupported contract_version %r (supported: %d)' % (name, item.get('contract_version'),
                                                                                CONTRACT_VERSION))
        return errors
    for key in REQUIRED_CONTRACT:
        if key not in item:
            errors.append('%s: contract field %s is required' % (name, key))
    if errors:
        return errors
    if item['status'] not in STATUSES:
        errors.append('%s: status must be one of %s' % (name, ', '.join(STATUSES)))
    if not isinstance(item['owner'], str) or not item['owner']:
        errors.append('%s: owner must name the responsible role' % name)
    if not isinstance(item['interface_version'], str) or not VERSION.match(item['interface_version']):
        errors.append('%s: interface_version must be MAJOR.MINOR.PATCH' % name)
    _bounded_shape(name, item['inputs'], errors, 'inputs', ('type', 'required', 'description'))
    _bounded_shape(name, item['outputs'], errors, 'outputs', ('type', 'required', 'description'))
    _bounded_shape(name, item['errors'], errors, 'errors', ('exit_code', 'meaning'))
    caps = item['capabilities']
    if not isinstance(caps, list) or any(c not in CAPABILITIES for c in caps) or len(set(caps)) != len(caps):
        errors.append('%s: capabilities must be unique values from %s' % (name, ', '.join(CAPABILITIES)))
    limits = item['limits']
    if not isinstance(limits, dict) or set(limits) - {'timeout_seconds', 'output_bytes'} or not limits or \
            any(type(v) is not int or v < 1 for v in limits.values()):
        errors.append('%s: limits needs positive integer timeout_seconds and/or output_bytes only' % name)
    acceptance = item['acceptance']
    if not isinstance(acceptance, list) or not acceptance or any(
            not isinstance(p, str) or not Path(p).name.startswith('test_')
            or (files and not (view.exists(p) if view is not None else (Path(root) / p).is_file()))
            for p in acceptance):
        errors.append('%s: acceptance must list existing test_*.py files' % name)
    for record in item.get('evidence') or []:
        if not isinstance(record, dict) or set(record) - set(EVIDENCE_FIELDS) or record.get('exit_code') != 0:
            errors.append('%s: evidence records need only %s with exit_code 0' % (name, ', '.join(EVIDENCE_FIELDS)))
    status = item['status']
    if status in ('verified', 'active'):
        state = verification(item, root, view=view)
        if state['state'] != 'current':
            errors.append('%s: status %s needs current evidence (%s)' % (name, status, state['detail']))
    if status == 'active' and not (isinstance(item.get('activation'), dict) and item['activation'].get('by')
                                   and item['activation'].get('at')):
        errors.append('%s: active status needs an activation record naming who activated it and when' % name)
    if status in ('deprecated', 'retired') and not (isinstance(item.get('deprecation'), dict)
                                                    and item['deprecation'].get('migration')):
        errors.append('%s: %s status needs deprecation.migration naming the replacement path' % (name, status))
    return errors


def validate_catalog(catalog, root, files=True, view=None):
    if not isinstance(catalog, dict) or not isinstance(catalog.get('tools'), list) or not catalog['tools']:
        return ['catalog: a non-empty "tools" list is required']
    errors = []
    if catalog.get('catalog_version') not in (None, CATALOG_VERSION):
        errors.append('catalog: unsupported catalog_version %r (supported: %d)' % (catalog['catalog_version'], CATALOG_VERSION))
    unknown = set(catalog) - set(CATALOG_FIELDS)
    if 'gate_baseline' in catalog and not re.fullmatch(r'[0-9a-f]{40}', str(catalog['gate_baseline'])):
        errors.append('catalog: gate_baseline must be a full 40-hex commit id')
    if unknown:
        errors.append('catalog: unsupported field(s): ' + ', '.join(sorted(unknown)))
    seen_ids, seen_paths = {}, {}
    for item in catalog['tools']:
        if not isinstance(item, dict):
            errors.append('catalog: every tool must be an object')
            continue
        errors.extend(validate_tool(item, root, files, view))
        for table, key in ((seen_ids, 'id'), (seen_paths, 'path')):
            if item.get(key) in table:
                errors.append('catalog: duplicate %s %r' % (key, item.get(key)))
            table[item.get(key)] = True
    assets = catalog.get('assets') or {}
    if not isinstance(assets, dict) or set(assets) - set(ASSET_LISTS):
        errors.append('catalog: assets may only contain ' + ', '.join(ASSET_LISTS))
    else:
        for kind, entries in assets.items():
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {'path', 'reason'} or not entry['reason'] \
                        or (files and not (view.exists(entry['path']) if view is not None
                                           else (Path(root) / entry['path']).is_file())):
                    errors.append('catalog: assets.%s entries need an existing path and a reason' % kind)
                elif entry['path'] in seen_paths:
                    errors.append('catalog: %s is both a registered tool and assets.%s' % (entry['path'], kind))
    errors.extend(_exception_errors(catalog, seen_paths))
    return errors


def _exception_errors(catalog, tool_paths):
    """`legacy_exceptions` authorize one exact change to a legacy tool: path, the sha256 of the changed bytes,
    a responsible owner and a real reason. They are reviewed in the diff and expire when the bytes change again."""
    entries = catalog.get('legacy_exceptions', [])
    if not isinstance(entries, list):
        return ['catalog: legacy_exceptions must be a list']
    errors = []
    by_path = {t.get('path'): t for t in catalog.get('tools', []) if isinstance(t, dict)}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'owner', 'reason'} \
                or not re.fullmatch(r'[0-9a-f]{64}', str(entry.get('sha256'))) or not entry.get('owner') \
                or not isinstance(entry.get('reason'), str) or len(entry['reason'].strip()) < 20:
            errors.append('catalog: legacy_exceptions entries need path, a 64-hex sha256, owner and a reason '
                          'of at least 20 characters')
        elif entry['path'] not in tool_paths:
            errors.append('catalog: legacy exception for %s names no registered tool' % entry['path'])
        elif by_path[entry['path']].get('contract_version') is not None:
            errors.append('catalog: legacy exception for %s is obsolete; the tool has a contract' % entry['path'])
    return errors


def is_stdlib(name):
    names = getattr(sys, 'stdlib_module_names', None)
    if names is not None:
        return name in names
    import importlib.util
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return False
    origin = getattr(spec, 'origin', None)
    return spec is not None and (origin in ('built-in', 'frozen') or (
        origin is not None and str(origin).startswith(sysconfig.get_paths()['stdlib'])
        and 'site-packages' not in str(origin)))


def imports_of(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split('.')[0])
    return found


OPERATIONAL_SUFFIXES = ('.py', '.sh', '.bash', '.zsh', '.js', '.mjs', '.cjs', '.ts', '.rb', '.pl')
CLI_MODULES = {'argparse', 'click', 'typer', 'optparse', 'fire', 'docopt'}
EFFECT_BARE = {'open', 'print', 'input', 'exec', 'eval', '__import__', 'exit', 'quit', 'breakpoint'}
EFFECT_MODULES = {'subprocess', 'requests', 'urllib', 'http', 'smtplib', 'ftplib', 'webbrowser', 'pty'}
EFFECT_FUNCTIONS = {'shutil': {'copy', 'copy2', 'copyfile', 'copytree', 'move', 'rmtree', 'make_archive',
                               'unpack_archive', 'chown', 'copymode', 'copystat'},
                    'socket': {'socket', 'create_connection', 'create_server'}, 'asyncio': {'run'}}
EFFECT_OS = {'system', 'popen', 'remove', 'unlink', 'rmdir', 'removedirs', 'rename', 'replace', 'mkdir', 'makedirs',
             'chmod', 'chown', 'kill', 'killpg', 'execv', 'execve', 'execl', 'execlp', 'execvp', 'fork', '_exit',
             'chdir', 'putenv', 'symlink', 'link', 'truncate', 'utime', 'write'}
EFFECT_METHODS = {'write_text', 'write_bytes', 'unlink', 'rmdir', 'mkdir', 'touch', 'symlink_to', 'rename'}
IMPORT_TIME_OK = {'sys.path.insert', 'sys.path.append', 'sys.path.extend', 'sys.path.remove', 'warnings.filterwarnings',
                  'warnings.simplefilter', 'os.environ.setdefault', 'logging.disable', 'multiprocessing.set_start_method',
                  'locale.setlocale', 'mimetypes.add_type', '__all__.extend', '__all__.append', 'random.seed',
                  'sys.setrecursionlimit', 'faulthandler.enable', 'csv.field_size_limit'}
TEST_MAIN = {'unittest.main', 'pytest.main'}
TEST_LOADERS = ('.exec_module',)  # a test that loads the script under test by path may execute that module


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    elif isinstance(node, ast.Call):
        parts.append('?')
    else:
        return None
    return '.'.join(reversed(parts))


def _shallow(node):
    """Nodes a statement executes at import: everything except function and lambda bodies."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        for child in ast.iter_child_nodes(current):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                stack.append(child)


def _is_main_test(test):
    if isinstance(test, ast.BoolOp):
        return any(_is_main_test(value) for value in test.values)
    if not isinstance(test, ast.Compare):
        return False
    operands = [test.left] + list(test.comparators)
    named = any(isinstance(n, ast.Name) and n.id == '__name__' for n in operands)

    def is_main(node):
        if isinstance(node, ast.Constant):
            return node.value == '__main__'
        return isinstance(node, (ast.Tuple, ast.List, ast.Set)) and any(is_main(e) for e in node.elts)
    return named and any(is_main(n) for n in operands)


def _statements(body):
    """Module-level statements, descending only through plain control flow that runs at import."""
    for statement in body:
        yield statement
        if isinstance(statement, (ast.If, ast.Try)) and not (isinstance(statement, ast.If)
                                                              and _is_main_test(statement.test)):
            nested = list(statement.body) + list(statement.orelse)
            if isinstance(statement, ast.Try):
                nested += list(statement.finalbody) + [s for h in statement.handlers for s in h.body]
            yield from _statements(nested)


def _effect_reason(node, testish):
    """Why one node performs an effect when the module is merely imported, or None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'sys' \
            and node.attr in ('argv', 'stdin'):
        return 'reads sys.' + node.attr
    if isinstance(node, ast.Call):
        name = _dotted(node.func) or ''
        root, _, tail = name.partition('.')
        leaf = name.rsplit('.', 1)[-1]
        if not tail and root in EFFECT_BARE:
            return 'calls %s()' % root
        if root in EFFECT_MODULES and tail:
            return 'calls %s' % name
        if root in EFFECT_FUNCTIONS and leaf in EFFECT_FUNCTIONS[root] and name.count('.') == 1:
            return 'calls %s' % name
        if root == 'os' and leaf in EFFECT_OS and name.startswith('os.') and name.count('.') == 1:
            return 'calls %s' % name
        if root == 'sys' and leaf == 'exit':
            return 'calls sys.exit'
        if isinstance(node.func, ast.Attribute) and node.func.attr in EFFECT_METHODS:
            return 'calls .%s()' % node.func.attr
    return None


def operational_reasons(tree, testish=False):
    """Reasons a module is operational code rather than importable logic: a main guard, import-time effects
    (bare top-level calls, loops, `with`, raises, I/O/process/network calls, argv/stdin reads)."""
    reasons = []
    for statement in _statements(tree.body):
        if isinstance(statement, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.Pass)):
            continue
        if isinstance(statement, ast.If) and _is_main_test(statement.test):
            calls = {_dotted(n.func) or '?' for n in _shallow(statement) if isinstance(n, ast.Call)}
            if not (testish and calls and calls <= TEST_MAIN | {'sys.exit', 'SystemExit', 'exit'}):
                reasons.append('main guard')
            continue
        if isinstance(statement, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            reasons.append('top-level %s block' % type(statement).__name__.lower())
        elif isinstance(statement, ast.Raise):
            reasons.append('top-level raise')
        elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            name = _dotted(statement.value.func) or '?'
            if name not in IMPORT_TIME_OK and not (testish and (name in TEST_MAIN or name.endswith(TEST_LOADERS))):
                reasons.append('top-level call %s()' % name)
        header = [statement.test] if isinstance(statement, (ast.If, ast.While)) else \
            [] if isinstance(statement, (ast.Try, ast.ClassDef)) else [statement]
        for part in header:
            for node in _shallow(part):
                reason = _effect_reason(node, testish)
                if reason:
                    reasons.append(reason)
        if isinstance(statement, ast.ClassDef):
            for inner in statement.body:
                if isinstance(inner, (ast.Assign, ast.Expr)):
                    for node in _shallow(inner):
                        reason = _effect_reason(node, testish)
                        if reason:
                            reasons.append(reason)
    return list(dict.fromkeys(reasons))


def console_scripts(view):
    """Module names pyproject.toml publishes as installed commands (an explicit, reviewed inventory)."""
    data = view.read('pyproject.toml')
    if data is None:
        return set()
    block = re.search(r'^\[project\.scripts\]\s*\n((?:[^\[\n][^\n]*\n?)*)', data.decode('utf-8', 'replace'), re.M)
    return set(re.findall(r'=\s*"([A-Za-z0-9_.]+):', block.group(1))) if block else set()


def classify_source(name, text, mode='100644', console=False):
    """('test'|'entrypoint'|'module'|'spoofed-test', detail). Syntax errors are reported by other gates.

    A name never decides the category. A file named like a test must import a test framework and run nothing
    but that framework; any other main guard or import-time effect makes it operational code in disguise."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 'module', 'unparseable'
    modules = imports_of(tree)
    testish = name.startswith('test_') or name.endswith('_test.py')
    if testish:
        if not ({'unittest', 'pytest'} & modules):
            return 'spoofed-test', 'named like a test but imports neither unittest nor pytest'
        reasons = operational_reasons(tree, testish=True)
        if 'main guard' in reasons:
            return 'spoofed-test', 'named like a test but exposes its own command line'
        if reasons:
            return 'spoofed-test', 'named like a test but executes operational code at import (%s)' % reasons[0]
        return 'test', ''
    reasons = operational_reasons(tree)
    if mode == '100755':
        reasons.append('executable bit')
    if name == '__main__.py':
        reasons.append('package entry point')
    if console:
        reasons.append('published console script')
    if reasons:
        return 'entrypoint', '; '.join(dict.fromkeys(reasons))
    return 'module', ''


def changed_assets(root, base, view):
    """[(status, path)] of files whose snapshot entry differs from `base`; None if the base cannot be resolved."""
    if _git(root, 'rev-parse', '--verify', base + '^{commit}') is None:
        return None
    result = _git_run(root, 'ls-tree', '-r', '-z', '--full-tree', base, binary=True)
    if result is None:
        return None
    before = _parse_entries(result.stdout, False)
    changed = []
    for path in sorted(set(before) | set(view.entries)):
        old, new = before.get(path), view.entries.get(path)
        if old != new:
            changed.append(('D' if new is None else 'A' if old is None else 'M', path))
    return changed


def base_catalog(root, base):
    text = _git(root, 'show', '%s:%s' % (base, CATALOG_RELATIVE))
    return json.loads(text) if text else None


def _is_candidate(path, view):
    if not TOOL_ROOT.match(path):
        return False
    if path.endswith(OPERATIONAL_SUFFIXES) or view.mode(path) == '100755':
        return True
    data = view.read(path)
    return bool(data and data.startswith(b'#!'))


def _declared_assets(catalog):
    return {e['path']: kind for kind in ASSET_LISTS for e in ((catalog.get('assets') or {}).get(kind) or [])
            if isinstance(e, dict) and 'path' in e}


def _referenced_by_a_test(view, path):
    name = Path(path).name
    for candidate in sorted(view.entries):
        if TOOL_ROOT.match(candidate) and Path(candidate).name.startswith('test_') and candidate.endswith('.py'):
            data = view.read(candidate)
            if data and name.encode() in data:
                return True
    return False


def _label_errors(view, declared, consoles):
    """A category label never exempts code from classification: `internal` and `fixtures` assets must not be
    operational (a published console script is the one reviewed exception for internal), and an executable
    fixture must be exercised by a test."""
    errors = []
    for path, kind in sorted(declared.items()):
        data = view.read(path)
        if data is None or not path.endswith('.py'):
            continue
        category, detail = classify_source(Path(path).name, data.decode('utf-8', 'replace'), view.mode(path),
                                           Path(path).stem in consoles)
        if category == 'spoofed-test':
            errors.append('%s: classification spoofing: %s' % (path, detail))
        elif category == 'entrypoint' and kind in ('internal', 'fixtures'):
            published = Path(path).stem in consoles
            if kind == 'internal' and published:
                continue
            if kind == 'fixtures' and _referenced_by_a_test(view, path):
                continue
            errors.append('%s: declared as assets.%s but it is operational code (%s); register it as a tool'
                          % (path, kind, detail))
    return errors


def gate(root, base='HEAD', changed=None, previous=None, snapshot=None, index_file=None, view=None):
    """The commit/CI gate. Returns (errors, notes); errors reject, notes only inform.

    Every artifact read (catalog, implementations, supporting code, acceptance, evidence) comes from one Git
    snapshot: the staged index for a commit, the committed tree for CI. The working tree is never substituted
    for it. An unknown or unreadable snapshot is an error, not a pass.

    Static rules run on the whole catalog. Incremental rules inspect only files that differ from `base`:
    unregistered operational code (guarded or not), spoofed test classification, parallel/duplicate
    implementations, undeclared third-party dependencies, changed legacy tools without a contract transition,
    new tools without declared acceptance, activation at creation, and compatibility against the base."""
    root = Path(root)
    notes = []
    try:
        view = view or open_snapshot(root, snapshot or default_snapshot(), index_file=index_file)
        return _gate(root, base, changed, previous, view, notes)
    except SnapshotError as exc:
        return ['snapshot: %s' % exc], notes
    except (OSError, ValueError) as exc:
        return ['catalog: unreadable: %s' % exc], notes


def _gate(root, base, changed, previous, view, notes):
    catalog = load_catalog(root, view)
    errors = validate_catalog(catalog, root, view=view)
    tools = [t for t in catalog.get('tools', []) if isinstance(t, dict)]
    by_path = {t.get('path'): t for t in tools}
    declared = _declared_assets(catalog)
    consoles = console_scripts(view)
    errors.extend(_label_errors(view, declared, consoles))
    exceptions = {e['path']: e for e in catalog.get('legacy_exceptions') or []
                  if isinstance(e, dict) and 'path' in e and 'sha256' in e}
    for path, entry in exceptions.items():
        tool = by_path.get(path)
        if tool is not None and tool.get('contract_version') is None \
                and implementation_fingerprint(root, tool, view=view) != entry['sha256']:
            errors.append('%s: legacy exception does not match the current bytes; it authorized a different '
                          'version' % path)
    baseline = catalog.get('gate_baseline')
    if baseline and changed is None:
        # Code that predates the standard is inventoried, not grandfathered: it is judged from the first commit
        # that carried the standard, so every later addition or change is held to it.
        if changed_assets(root, baseline, view) is not None:
            base = baseline
        else:
            notes.append('gate_baseline %s is not resolvable here (shallow clone?); using %s' % (baseline[:12], base))
    head_catalog = base_catalog(root, 'HEAD')
    if head_catalog and head_catalog.get('gate_baseline') and head_catalog['gate_baseline'] != baseline:
        errors.append('catalog: gate_baseline may not move once committed (it would hide earlier violations)')
    if changed is None:
        changed = changed_assets(root, base, view)
    if changed is None:
        notes.append('incremental checks skipped: %r is not a resolvable base revision' % base)
        return errors, notes
    previous = previous if previous is not None else base_catalog(root, base)
    hashes = {}
    for tool in tools:
        digest = implementation_fingerprint(root, tool, view=view) if isinstance(tool.get('path'), str) else None
        if digest:
            hashes.setdefault(digest, []).append(tool['path'])
    for status, path in changed:
        if status == 'D' or not _is_candidate(path, view):
            continue
        name = Path(path).name
        data = view.read(path)
        if data is None:
            continue
        text = data.decode('utf-8', errors='replace')
        if not path.endswith('.py'):
            kind, detail = 'entrypoint', 'non-Python executable'
        else:
            kind, detail = classify_source(name, text, view.mode(path), Path(path).stem in consoles)
        if kind == 'spoofed-test':
            errors.append('%s: classification spoofing: %s' % (path, detail))
            continue
        if kind == 'test':
            continue
        if PARALLEL.search(name):
            errors.append('%s: parallel implementation name; extend the existing tool in place' % path)
        registered = by_path.get(path)
        if kind == 'entrypoint' and registered is None and path not in declared:
            errors.append('%s: unregistered operational entrypoint (%s); register it in %s or declare it under '
                          'assets with a reason' % (path, detail, CATALOG_RELATIVE))
        if registered is not None:
            digest = implementation_fingerprint(root, registered, view=view)
            clones = [p for p in hashes.get(digest, []) if p != path]
            if clones:
                errors.append('%s: byte-identical to registered tool %s; reuse it' % (path, clones[0]))
            try:
                third = {m for m in imports_of(ast.parse(text)) if not is_stdlib(m)
                         and not view.exists('scripts/' + m + '.py')
                         and not view.exists(str(PurePosixPath(path).parent / (m + '.py')))}
            except SyntaxError:
                third = set()
            blob = ' '.join(registered.get('dependencies', [])).lower()
            for module in sorted(third):
                if module.lower() not in blob:
                    errors.append('%s: undeclared dependency %r; declare it in the tool dependencies' % (path, module))
            if status_of(registered) == 'legacy-unverified':
                reviewed = exceptions.get(path)
                if reviewed is not None and reviewed['sha256'] == digest:
                    notes.append('%s changed under a reviewed legacy exception (owner %s)' % (path, reviewed['owner']))
                else:
                    errors.append('%s: a changed legacy-unverified tool must adopt contract version %d with '
                                  'current evidence, or carry a legacy_exceptions record for sha256 %s'
                                  % (path, CONTRACT_VERSION, digest))
    previous_by_id = {t['id']: t for t in (previous or {}).get('tools', []) if isinstance(t, dict) and 'id' in t}
    ids = {t.get('id'): t for t in tools}
    for ident, old in previous_by_id.items():
        new = ids.get(ident)
        if new is None:
            errors.append('compatibility: tool %s was removed; keep it as a retired entry with a migration' % ident)
            continue
        if new.get('path') != old.get('path') and status_of(new) != 'retired':
            errors.append('compatibility: tool %s changed path without a retired record' % ident)
        if new.get('example_args') != old.get('example_args') and not new.get('compat_note'):
            errors.append('compatibility: tool %s changed its command arguments without a compat_note' % ident)
    for ident, new in ids.items():
        if ident in previous_by_id or previous is None:
            continue
        if new.get('contract_version') != CONTRACT_VERSION:
            errors.append('%s: a new tool must declare contract version %d' % (ident, CONTRACT_VERSION))
        elif new.get('status') == 'active':
            errors.append('%s: a new tool cannot be introduced as active; verify it first' % ident)
        elif not new.get('acceptance'):
            errors.append('%s: a new tool needs declared acceptance' % ident)
    return errors, notes


MARK_BEGIN = '<!-- tool-catalog:begin (generated by scripts/tool_catalog.py render; do not edit) -->'
MARK_END = '<!-- tool-catalog:end -->'


def render_table(catalog):
    rows = ['| Tool | Status | Purpose | Arguments |', '| --- | --- | --- | --- |']
    for item in catalog['tools']:
        arguments = item.get('example_args', '').replace('|', '\\|')
        rows.append('| [%s](../%s) | %s | %s | `%s` |' % (item['id'], item['path'], status_of(item),
                                                          item['description'].replace('|', '\\|'), arguments))
    return '\n'.join(rows)


def render_into(text, catalog):
    block = MARK_BEGIN + '\n' + render_table(catalog) + '\n' + MARK_END
    if MARK_BEGIN in text and MARK_END in text:
        head, rest = text.split(MARK_BEGIN, 1)
        return head + block + rest.split(MARK_END, 1)[1]
    raise ValueError('The generated-table markers are missing from ' + DOC_RELATIVE)


def check_rendered(root, view=None):
    root = Path(root)
    try:
        text = (view.read(DOC_RELATIVE).decode('utf-8') if view is not None
                else (root / DOC_RELATIVE).read_text(encoding='utf-8'))
        expected = render_into(text, load_catalog(root, view))
    except (AttributeError, SnapshotError) as exc:
        return ['%s is not readable in the snapshot: %s' % (DOC_RELATIVE, exc)]
    except ValueError as exc:
        return [str(exc)]
    return [] if expected == text else [DOC_RELATIVE + ' differs from the catalog; run scripts/tool_catalog.py render']


def check_all(root, base='HEAD', snapshot=None, index_file=None):
    """The whole commit/CI check on one snapshot: (errors, notes) for the gate and the generated human view."""
    notes = []
    try:
        view = open_snapshot(root, snapshot or default_snapshot(), index_file=index_file)
    except SnapshotError as exc:
        return ['snapshot: %s' % exc], notes
    errors, notes = gate(root, base, view=view)
    return errors + check_rendered(root, view), notes


def discover(catalog):
    """Compact metadata only: enough to choose a tool, not enough to flood a context window."""
    return [{'id': t['id'], 'status': status_of(t), 'effect': t.get('effect'), 'purpose': t.get('description')}
            for t in catalog['tools']]


def describe(catalog, root, ident):
    item = next((t for t in catalog['tools'] if t.get('id') == ident), None)
    if item is None:
        raise ValueError('Unknown registered tool: ' + str(ident))
    return dict(item, lifecycle=status_of(item), verification=verification(item, root),
                implementation_sha256=implementation_fingerprint(root, item),
                contract_sha256=contract_fingerprint(item))


def run_acceptance_worker(start_dir, pattern, output):
    """Run one acceptance module with unittest's own result object and write structured counts as JSON.

    The outcome is read from the result, never from an exit code or display text: Python 3.9 exits 0 for a
    module with no tests where 3.12+ exits 5, so the exit code cannot define meaningful acceptance."""
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(start_dir, pattern=pattern)
    result = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    skipped = len(result.skipped)
    counts = {'discovered': suite.countTestCases(), 'run': result.testsRun, 'executed': result.testsRun - skipped,
              'skipped': skipped, 'failures': len(result.failures), 'errors': len(result.errors),
              'expected_failures': len(result.expectedFailures),
              'unexpected_successes': len(result.unexpectedSuccesses)}
    Path(output).write_text(json.dumps({'counts': counts, 'tail': stream.getvalue()[-600:]}), encoding='utf-8')
    return 0


def _run_acceptance(root, test, runner, timeout):
    """(counts, command) for one required acceptance file; ValueError unless it ran meaningful passing tests."""
    directory = tempfile.mkdtemp(prefix='crewloom-acceptance-')
    output = Path(directory) / 'result.json'
    command = [sys.executable, str(Path(__file__).resolve()), 'acceptance-worker', str(Path(test).parent),
               Path(test).name, str(output)]
    try:
        result = runner(command, cwd=str(root), capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise ValueError('Acceptance failed for %s (exit %d); no evidence was recorded\n%s' % (
                test, result.returncode, (result.stderr or '')[-400:]))
        try:
            report = json.loads(output.read_text(encoding='utf-8'))
            counts = {key: report['counts'][key] for key in COUNT_FIELDS}
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('Acceptance for %s produced no structured result; no evidence was recorded' % test)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    problem = acceptance_problem(counts) if all(type(v) is int for v in counts.values()) else 'malformed counts'
    if problem:
        raise ValueError('Acceptance for %s is not meaningful (%s; %s); no evidence was recorded\n%s' % (
            test, problem, ', '.join('%s=%s' % kv for kv in counts.items()), (report.get('tail') or '')[-400:]))
    return counts, 'tool_catalog.py acceptance-worker %s %s' % (Path(test).parent, Path(test).name)


def _assert_catalog_unchanged(root, expected):
    """Reject any catalog drift, including unrelated edits, instead of overwriting another writer."""
    import workflow as w
    try:
        path = w.safe_path(root, CATALOG_RELATIVE, internal=True)
        current = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise ValueError('The catalog changed or became unreadable; no evidence was recorded') from exc
    if current != expected:
        raise ValueError('The catalog changed while acceptance ran; no evidence was recorded')
    return path


def _publish_evidence_catalog(root, expected, catalog):
    """Replace the complete catalog atomically, preserving permissions and cleaning failed preparations."""
    path = _assert_catalog_unchanged(root, expected)
    mode = path.stat().st_mode & 0o777
    descriptor, temporary = tempfile.mkstemp(dir=str(path.parent), prefix='.TOOLS-')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        _assert_catalog_unchanged(root, expected)  # also check changes during preparation
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_evidence(root, ident, runner=subprocess.run, timeout=300):
    """Controlled writer: run every declared (required) acceptance file and bind the passing, meaningful results
    to the exact implementation, supporting code, contract and acceptance bytes that were tested.

    All declared acceptance is required: there is no optional tier, and a failing, wholly skipped or empty
    module blocks promotion; expected failures alone cannot pass. Cooperating recorders use the existing
    project lock protocol. Any catalog drift refuses recording and preserves the other writer's bytes.
    The final complete catalog is atomically replaced; arbitrary host editors do not honor this lock."""
    import workflow as w
    root = Path(root).resolve()
    w.safe_path(root, CATALOG_RELATIVE, internal=True)
    folder = w.safe_path(root, '.crewloom/tool-catalog', internal=True)
    with w.project_lock(folder):
        return _record_evidence(root, ident, runner, timeout)


def _record_evidence(root, ident, runner, timeout):
    snapshot = (root / CATALOG_RELATIVE).read_bytes()
    catalog = json.loads(snapshot.decode('utf-8'))
    item = next((t for t in catalog['tools'] if t.get('id') == ident), None)
    if item is None or item.get('contract_version') != CONTRACT_VERSION:
        raise ValueError('Tool %r has no contract version %d to verify' % (ident, CONTRACT_VERSION))
    problems = [e for e in validate_tool(item, root) if 'needs current evidence' not in e]
    if problems:
        raise ValueError('Contract is invalid: ' + '; '.join(problems))
    before = provenance(item, root)
    if before['source'] is None:
        raise ValueError('The implementation of %s is missing; no evidence was recorded' % ident)
    tested = []
    for test in item['acceptance']:
        counts, command = _run_acceptance(root, test, runner, timeout)
        tested.append((test, counts, command))
    _assert_catalog_unchanged(root, snapshot)
    after = provenance(item, root)
    if after != before:
        raise ValueError('The source, supporting code, contract or acceptance changed while acceptance ran; '
                         'no evidence was recorded')
    stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    item['evidence'] = [{'test': test, 'command': command, 'exit_code': 0, 'source_sha256': before['source'],
                         'contract_sha256': before['contract'], 'support_sha256': before['support'],
                         'acceptance_sha256': before['acceptance'][test], 'counts': counts,
                         'provenance': PROVENANCE_VERSION, 'recorded_at': stamp} for test, counts, command in tested]
    if item['status'] == 'draft':
        item['status'] = 'verified'
    if provenance(item, root) != before:  # last look before the catalog write
        raise ValueError('The artifacts changed while the evidence was prepared; no evidence was recorded')
    _publish_evidence_catalog(root, snapshot, catalog)
    return item


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('discover')
    describing = commands.add_parser('describe')
    describing.add_argument('tool')
    commands.add_parser('validate')
    checking = commands.add_parser('gate')
    checking.add_argument('--base', default=os.environ.get('CREWLOOM_TOOL_GATE_BASE') or 'HEAD')
    checking.add_argument('--snapshot', choices=SNAPSHOTS, default=None,
                          help='Artifact view to judge: the staged index (default locally) or the committed tree (CI)')
    checking.add_argument('--index-file', default=None, help='Judge this custom index of the selected repository')
    worker = commands.add_parser('acceptance-worker', help=argparse.SUPPRESS)
    for argument in ('start_dir', 'pattern', 'output'):
        worker.add_argument(argument)
    commands.add_parser('render')
    commands.add_parser('render-check')
    recording = commands.add_parser('record-evidence')
    recording.add_argument('tool')
    parser.add_argument('--root', help='Toolkit checkout (defaults to this checkout)')
    args = parser.parse_args(argv)
    if args.command == 'acceptance-worker':  # needs no checkout resolution: it runs in the checkout's directory
        return run_acceptance_worker(args.start_dir, args.pattern, args.output)
    if not (args.root or root):
        import crewloom_resources
        root = crewloom_resources.distribution_root()  # the checkout or the installed distribution, not a guess
    root = Path(args.root or root).resolve()
    try:
        if args.command == 'discover':
            print(json.dumps(discover(load_catalog(root)), indent=2, ensure_ascii=False))
        elif args.command == 'describe':
            print(json.dumps(describe(load_catalog(root), root, args.tool), indent=2, ensure_ascii=False))
        elif args.command == 'validate':
            import crewloom_resources
            # An installed distribution ships the tools, not their tests, so file presence is checked only in a checkout.
            errors = validate_catalog(load_catalog(root), root, files=crewloom_resources.source_checkout())
            print('\n'.join(errors) if errors else 'PASS: tool catalog')
            return 1 if errors else 0
        elif args.command == 'gate':
            errors, notes = gate(root, args.base, snapshot=args.snapshot, index_file=args.index_file)
            for note in notes:
                print('note: ' + note)
            for error in errors:
                print(error, file=sys.stderr)
            if not errors:
                print('PASS: tool gate (base %s)' % args.base)
            return 1 if errors else 0
        elif args.command == 'render':
            text = (root / DOC_RELATIVE).read_text(encoding='utf-8')
            (root / DOC_RELATIVE).write_text(render_into(text, load_catalog(root)), encoding='utf-8')
        elif args.command == 'render-check':
            errors = check_rendered(root)
            print('\n'.join(errors) if errors else 'PASS: generated tool view')
            return 1 if errors else 0
        else:
            item = record_evidence(root, args.tool)
            print(json.dumps({'tool': item['id'], 'status': item['status'], 'evidence': item['evidence']}, indent=2))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'rejected', 'error': str(exc)}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
