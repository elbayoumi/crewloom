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
import json
import os
import re
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

CATALOG_RELATIVE = 'documentation/TOOLS.json'
DOC_RELATIVE = 'documentation/TOOLS.md'
CONTRACT_VERSION = 1
CATALOG_VERSION = 2
LEGACY_FIELDS = ('id', 'skill', 'path', 'description', 'example_args', 'dependencies', 'effect')
CONTRACT_FIELDS = ('contract_version', 'interface_version', 'owner', 'status', 'inputs', 'outputs', 'errors',
                   'capabilities', 'limits', 'idempotent', 'acceptance', 'evidence', 'activation',
                   'deprecation', 'compat_note')
REQUIRED_CONTRACT = ('interface_version', 'owner', 'status', 'inputs', 'outputs', 'errors', 'capabilities',
                     'limits', 'acceptance')
FINGERPRINTED_CONTRACT = ('interface_version', 'inputs', 'outputs', 'errors', 'capabilities', 'limits',
                          'dependencies', 'effect', 'example_args', 'idempotent')
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


def load_catalog(root):
    return json.loads((Path(root) / CATALOG_RELATIVE).read_text(encoding='utf-8'))


def status_of(item):
    return item.get('status') or 'legacy-unverified'


def implementation_file(root, item, path=None):
    """The file that implements a tool: an explicit path, `root/path`, or, for the live installation only,
    the module the installed distribution maps that path to (a wheel keeps scripts beside site-packages)."""
    if path is not None:
        return Path(path)
    candidate = Path(root) / item['path']
    if candidate.is_file():
        return candidate
    try:
        import crewloom_resources as resources
        if Path(root).resolve() == Path(resources.distribution_root()).resolve():
            return Path(resources.resolve(item['path']))
    except Exception:  # an unresolvable installation is reported as a missing implementation
        pass
    return candidate


def implementation_fingerprint(root, item, path=None):
    file = implementation_file(root, item, path)
    return hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None


def contract_fingerprint(item):
    return sha({key: item.get(key) for key in FINGERPRINTED_CONTRACT})


def verification(item, root, path=None):
    """{'state': current|stale|missing|not-applicable, 'detail': ...} for an entry's recorded evidence."""
    status = status_of(item)
    if status not in ('verified', 'active'):
        return {'state': 'not-applicable', 'detail': 'status is ' + status}
    evidence = item.get('evidence') or []
    if not evidence:
        return {'state': 'missing', 'detail': 'no evidence is recorded'}
    source, contract = implementation_fingerprint(root, item, path), contract_fingerprint(item)
    for record in evidence:
        if record.get('source_sha256') == source and record.get('contract_sha256') == contract:
            return {'state': 'current', 'detail': 'evidence matches the current source and contract'}
    return {'state': 'stale', 'detail': 'the source or contract changed after the evidence was recorded'}


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


def validate_tool(item, root, files=True):
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
    elif not implementation_file(root, item).is_file() or implementation_file(root, item).is_symlink():
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
            or (files and not (Path(root) / p).is_file()) for p in acceptance):
        errors.append('%s: acceptance must list existing test_*.py files' % name)
    for record in item.get('evidence') or []:
        if not isinstance(record, dict) or set(record) - {'test', 'command', 'exit_code', 'source_sha256',
                                                          'contract_sha256', 'recorded_at'} \
                or record.get('exit_code') != 0:
            errors.append('%s: evidence records need only test, command, exit_code 0, fingerprints, recorded_at' % name)
    status = item['status']
    if status in ('verified', 'active') and verification(item, root)['state'] != 'current':
        errors.append('%s: status %s needs current evidence (%s)' % (name, status, verification(item, root)['detail']))
    if status == 'active' and not (isinstance(item.get('activation'), dict) and item['activation'].get('by')
                                   and item['activation'].get('at')):
        errors.append('%s: active status needs an activation record naming who activated it and when' % name)
    if status in ('deprecated', 'retired') and not (isinstance(item.get('deprecation'), dict)
                                                    and item['deprecation'].get('migration')):
        errors.append('%s: %s status needs deprecation.migration naming the replacement path' % (name, status))
    return errors


def validate_catalog(catalog, root, files=True):
    if not isinstance(catalog, dict) or not isinstance(catalog.get('tools'), list) or not catalog['tools']:
        return ['catalog: a non-empty "tools" list is required']
    errors = []
    if catalog.get('catalog_version') not in (None, CATALOG_VERSION):
        errors.append('catalog: unsupported catalog_version %r (supported: %d)' % (catalog['catalog_version'], CATALOG_VERSION))
    unknown = set(catalog) - {'tools', 'catalog_version', 'assets', 'gate_baseline'}
    if 'gate_baseline' in catalog and not re.fullmatch(r'[0-9a-f]{40}', str(catalog['gate_baseline'])):
        errors.append('catalog: gate_baseline must be a full 40-hex commit id')
    if unknown:
        errors.append('catalog: unsupported field(s): ' + ', '.join(sorted(unknown)))
    seen_ids, seen_paths = {}, {}
    for item in catalog['tools']:
        if not isinstance(item, dict):
            errors.append('catalog: every tool must be an object')
            continue
        errors.extend(validate_tool(item, root, files))
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
                        or (files and not (Path(root) / entry['path']).is_file()):
                    errors.append('catalog: assets.%s entries need an existing path and a reason' % kind)
                elif entry['path'] in seen_paths:
                    errors.append('catalog: %s is both a registered tool and assets.%s' % (entry['path'], kind))
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


def classify_source(name, text):
    """('test'|'entrypoint'|'module'|'spoofed-test', detail). Syntax errors are reported by other gates."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return 'module', 'unparseable'
    modules = imports_of(tree)
    guarded = any(isinstance(n, ast.If) and isinstance(n.test, ast.Compare) and isinstance(n.test.left, ast.Name)
                  and n.test.left.id == '__name__' for n in tree.body)
    cli = bool({'argparse', 'click', 'typer', 'optparse'} & modules) or 'sys.argv' in text
    testish = name.startswith('test_') or name.endswith('_test.py')
    if testish:
        if not ({'unittest', 'pytest'} & modules):
            return 'spoofed-test', 'named like a test but imports neither unittest nor pytest'
        if cli and guarded and not re.search(r'unittest\.main\(|pytest\.main\(', text):
            return 'spoofed-test', 'named like a test but exposes its own command line'
        return 'test', ''
    if guarded and cli:
        return 'entrypoint', ''
    return 'module', ''


def _git(root, *argv):
    # A commit hook exports GIT_DIR/GIT_INDEX_FILE for the repository being committed; the gate must observe
    # exactly the checkout it was given (fixtures included), so inherited repository selection is dropped.
    environment = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    result = subprocess.run(['git', '-C', str(root), *argv], capture_output=True, text=True, timeout=60,
                            env=environment)
    return result.stdout if result.returncode == 0 else None


def changed_assets(root, base):
    """[(status, path)] of files that differ from `base` in the working tree (plus untracked); None if unknown."""
    if _git(root, 'rev-parse', '--verify', base + '^{commit}') is None:
        return None
    diff = _git(root, 'diff', '--name-status', '-M', base)
    if diff is None:
        return None
    changed = []
    for line in diff.splitlines():
        parts = line.split('\t')
        if parts[0][0] == 'R':
            changed.append(('A', parts[2]))
        elif parts[0][0] in 'AMD':
            changed.append((parts[0][0], parts[1]))
    untracked = _git(root, 'ls-files', '--others', '--exclude-standard') or ''
    changed.extend(('A', line) for line in untracked.splitlines() if line)
    return changed


def base_catalog(root, base):
    text = _git(root, 'show', '%s:%s' % (base, CATALOG_RELATIVE))
    return json.loads(text) if text else None


def gate(root, base='HEAD', changed=None, previous=None):
    """The commit/CI gate. Returns (errors, notes); errors reject, notes only inform.

    Static rules always run on the whole catalog. Incremental rules inspect only files changed since
    `base`: unregistered operational entrypoints, spoofed test classification, parallel/duplicate
    implementations, undeclared third-party dependencies, new tools without declared acceptance,
    activation at creation, and compatibility of ids/paths/commands against the base catalog."""
    root = Path(root)
    notes = []
    try:
        catalog = load_catalog(root)
    except (OSError, ValueError) as exc:
        return ['catalog: unreadable: %s' % exc], notes
    errors = validate_catalog(catalog, root)
    tools = [t for t in catalog.get('tools', []) if isinstance(t, dict)]
    by_path = {t.get('path'): t for t in tools}
    declared = {e['path'] for kind in ASSET_LISTS for e in ((catalog.get('assets') or {}).get(kind) or [])
                if isinstance(e, dict) and 'path' in e}
    baseline = catalog.get('gate_baseline')
    if baseline and changed is None:
        # Code that predates the standard is inventoried, not grandfathered: it is judged from the first commit
        # that carried the standard, so every later addition or change is held to it.
        if changed_assets(root, baseline) is not None:
            base = baseline
        else:
            notes.append('gate_baseline %s is not resolvable here (shallow clone?); using %s' % (baseline[:12], base))
    head_catalog = base_catalog(root, 'HEAD')
    if head_catalog and head_catalog.get('gate_baseline') and head_catalog['gate_baseline'] != baseline:
        errors.append('catalog: gate_baseline may not move once committed (it would hide earlier violations)')
    if changed is None:
        changed = changed_assets(root, base)
    if changed is None:
        notes.append('incremental checks skipped: %r is not a resolvable base revision' % base)
        return errors, notes
    previous = previous if previous is not None else base_catalog(root, base)
    hashes = {}
    for tool in tools:
        digest = implementation_fingerprint(root, tool) if isinstance(tool.get('path'), str) else None
        if digest:
            hashes.setdefault(digest, []).append(tool['path'])
    for status, path in changed:
        if status == 'D' or not path.endswith('.py') or not TOOL_ROOT.match(path) or not (root / path).is_file():
            continue
        name = Path(path).name
        text = (root / path).read_text(encoding='utf-8', errors='replace')
        kind, detail = classify_source(name, text)
        if kind == 'spoofed-test':
            errors.append('%s: classification spoofing: %s' % (path, detail))
            continue
        if kind == 'test':
            continue
        if PARALLEL.search(name):
            errors.append('%s: parallel implementation name; extend the existing tool in place' % path)
        registered = by_path.get(path)
        if kind == 'entrypoint' and registered is None and path not in declared:
            errors.append('%s: unregistered operational entrypoint; register it in %s or declare it under assets '
                          'with a reason' % (path, CATALOG_RELATIVE))
        if registered is not None:
            clones = [p for p in hashes.get(implementation_fingerprint(root, registered), []) if p != path]
            if clones:
                errors.append('%s: byte-identical to registered tool %s; reuse it' % (path, clones[0]))
            try:
                third = {m for m in imports_of(ast.parse(text)) if not is_stdlib(m)
                         and not (root / 'scripts' / (m + '.py')).is_file()
                         and not (root / Path(path).parent / (m + '.py')).is_file()}
            except SyntaxError:
                third = set()
            blob = ' '.join(registered.get('dependencies', [])).lower()
            for module in sorted(third):
                if module.lower() not in blob:
                    errors.append('%s: undeclared dependency %r; declare it in the tool dependencies' % (path, module))
            if status_of(registered) == 'legacy-unverified':
                notes.append('%s changed and stays legacy-unverified: no contract or evidence is claimed' % path)
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


def check_rendered(root):
    root = Path(root)
    text = (root / DOC_RELATIVE).read_text(encoding='utf-8')
    try:
        expected = render_into(text, load_catalog(root))
    except ValueError as exc:
        return [str(exc)]
    return [] if expected == text else [DOC_RELATIVE + ' differs from the catalog; run scripts/tool_catalog.py render']


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


def record_evidence(root, ident, runner=subprocess.run, timeout=300):
    """Controlled writer: run the tool's declared acceptance and bind a passing result to the exact fingerprints.

    A failing run records nothing and an existing record is never rewritten with a different result."""
    root = Path(root)
    catalog = load_catalog(root)
    item = next((t for t in catalog['tools'] if t.get('id') == ident), None)
    if item is None or item.get('contract_version') != CONTRACT_VERSION:
        raise ValueError('Tool %r has no contract version %d to verify' % (ident, CONTRACT_VERSION))
    problems = [e for e in validate_tool(item, root) if 'needs current evidence' not in e]
    if problems:
        raise ValueError('Contract is invalid: ' + '; '.join(problems))
    records = []
    for test in item['acceptance']:
        command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(Path(test).parent), '-p', Path(test).name]
        result = runner(command, cwd=str(root), capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            raise ValueError('Acceptance failed for %s (exit %d); no evidence was recorded\n%s' % (
                test, result.returncode, (result.stderr or '')[-400:]))
        records.append({'test': test, 'command': ' '.join(command[1:]), 'exit_code': 0,
                        'source_sha256': implementation_fingerprint(root, item),
                        'contract_sha256': contract_fingerprint(item),
                        'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    item['evidence'] = records
    if item['status'] == 'draft':
        item['status'] = 'verified'
    (root / CATALOG_RELATIVE).write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
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
    commands.add_parser('render')
    commands.add_parser('render-check')
    recording = commands.add_parser('record-evidence')
    recording.add_argument('tool')
    parser.add_argument('--root', help='Toolkit checkout (defaults to this checkout)')
    args = parser.parse_args(argv)
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
            errors, notes = gate(root, args.base)
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
