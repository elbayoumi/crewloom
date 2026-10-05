#!/usr/bin/env python3
"""Validate the exact public checkout and its core regression suites."""
import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

from crewloom import load_validator
from workflow import folded

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('skill-forge-recruiter', 'context-guardian', 'frontend-ux-auditor', 'qa-test-automation-engineer')
TEST_PATTERN = 'test_*.py'
SUITE_TIMEOUT = 60

# The controlled ephemeral trees this gate never walks into and never reviews as project content.
# They are build output, dependency trees, caches and private runtime state: `.git` is Git's own
# state, `.crewloom` is this toolkit's runtime state, and none of the rest belongs in a commit or a
# distribution. They are named here as a fixed set on purpose. Reading a `.gitignore` to decide what
# is project content would let the file that adds an independent application also declare it out of
# scope, which is exactly the boundary this gate exists to hold.
EPHEMERAL = frozenset({'.git', '.crewloom', '__pycache__', 'node_modules', '.next', 'build', 'dist',
                       '.venv', '.tox', '.mypy_cache', '.pytest_cache'})

# Harmless operating system metadata a desktop writes beside real files. Ignored for the same
# reason as the ephemeral trees: it is machine residue, never project content, and it never
# carries an application.
OS_METADATA = frozenset({'.DS_Store', '.localized', 'Thumbs.db', '.Spotlight-V100', '.Trashes',
                         'desktop.ini'})

# Generated distribution metadata, matched by suffix because setuptools names it after the version.
EGG_INFO = '.egg-info'

# One spelling-independent form of every ignorable top-level name, because APFS and HFS+ compare
# names without case while a contract and a directory entry are still different strings for one
# file. The comparison is the same folding the rest of the toolkit uses for every other name
# decision, so the answer is identical on a developer Mac, in CI and in a container.
IGNORED_KEYS = frozenset(folded(name) for name in EPHEMERAL | OS_METADATA)
SKIPPED = EPHEMERAL | OS_METADATA

# The one reviewed document that says which top-level files and directories belong to this project.
# It is metadata rather than a hint: a top-level entry this contract does not register is not part of
# the Crewloom toolkit, so an independent application added to this checkout is a reported failure
# instead of a new folder the gate walks past. Registering one is a reviewed change to this contract
# and its policy note, never something an ignore file or a directory name can buy.
SCOPE_CONTRACT = 'REPOSITORY_SCOPE.json'
SCOPE_SCHEMA = 1
SCOPE_KINDS = ('directories', 'files')

# The toolkit's own project identity. A fork keeps it, because a fork is still the Crewloom toolkit
# and still has to reject somebody else's application; an independent application keeps its own
# identity in its own root and repository. No Git host, owner or remote is named here: identity is
# a property of this project, not of where it happens to be published from.
SCOPE_PROJECT = 'crewloom-toolkit'
SCOPE_PROJECT_ID = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')


def _scope_entry_errors(name, kind, registered):
    """Why one declared scope entry is unusable, or an empty list when it is a real top-level name.

    A registered name has to be a single component that stays inside this root and is not itself
    ignorable. Registering an ephemeral or OS-metadata name would put a tree permanently outside the
    foreign-entry check while calling it project content, and two names that fold together would
    make the contract mean one directory on a case-insensitive filesystem and two on a
    case-sensitive one, so both are refused instead of resolved.
    """
    if not isinstance(name, str) or not name:
        return [SCOPE_CONTRACT + ' ' + kind + ' must hold nonempty text names: ' + repr(name)]
    if '\0' in name:
        return [SCOPE_CONTRACT + ' ' + kind + ' name contains a NUL byte: ' + repr(name)]
    path = Path(name)
    if path.is_absolute() or '\\' in name or '..' in path.parts \
            or len(path.parts) != 1 or name != path.name:
        return [SCOPE_CONTRACT + ' ' + kind + ' name must be one top-level name inside this root: '
                + name]
    key = folded(name)
    if key in IGNORED_KEYS or key.endswith(EGG_INFO):
        return [SCOPE_CONTRACT + ' ' + kind + ' may not register generated, ignored or operating '
                'system metadata as project content: ' + name]
    if key in registered:
        return [SCOPE_CONTRACT + ' ' + kind + ' name collides with an already registered name: '
                + name + ' and ' + registered[key] + ' compare as one name']
    return []


def _scope_entries(root, registered):
    """Every top-level entry this checkout holds that its own contract does not register.

    Reported by name and never by content: the gate reads directory entry names and the one small
    contract document, so an unregistered project is refused without a single payload body being
    read into a commit message or a log line.
    """
    errors = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        key = folded(entry.name)
        if key in IGNORED_KEYS or key.endswith(EGG_INFO):
            continue
        if key in registered:
            if registered[key] != entry.name:
                errors.append('Top-level name resolves through a folded alias: ' + entry.name
                              + ' and the registered ' + registered[key]
                              + ' are one name on a case-insensitive filesystem; register one spelling')
            continue
        kind = 'directory' if entry.is_dir() else 'file'
        errors.append('Unregistered top-level ' + kind + ': ' + entry.name + ' belongs to no project '
                      'declared by ' + SCOPE_CONTRACT + '. Keep an independent application in its own '
                      'canonical root and repository, or add it to ' + SCOPE_CONTRACT
                      + ' as a reviewed scope change with its own policy note.')
    return errors


def scope_errors(root):
    """Every reason this checkout's top-level content is not the registered Crewloom project.

    Read-only, actionable, and total: a missing, malformed, foreign, mis-schemaed or escaping
    contract is reported rather than tolerated, because the alternative is a checkout that has
    quietly grown a second project while the gate keeps reporting PASS. Nothing is written, no
    payload body is read or printed, and a contract that cannot be read at all is not used to judge
    anything else: the one real reason is reported instead of a pile of derived ones.

    This is contract validation against reviewed project metadata, not an OS sandbox. It decides
    what belongs to this project; it cannot stop a privileged owner of the machine or of this
    repository from editing the contract itself, and it does not pretend otherwise.
    """
    contract = root / SCOPE_CONTRACT
    if contract.is_symlink():
        return [SCOPE_CONTRACT + ' may not be a symlink: the declared project scope is a real file']
    if not contract.is_file():
        return ['Missing ' + SCOPE_CONTRACT + ': this checkout declares no project scope, so every '
                'top-level file and directory in it would be unowned. An independent application '
                'belongs in its own canonical root and repository, not inside the Crewloom toolkit.']
    try:
        document = json.loads(contract.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        return ['Malformed ' + SCOPE_CONTRACT + ': ' + str(exc)]
    if not isinstance(document, dict):
        return [SCOPE_CONTRACT + ' must be a JSON object describing exactly one project scope']
    errors = []
    if document.get('schema_version') != SCOPE_SCHEMA:
        errors.append(SCOPE_CONTRACT + ' schema_version must be ' + str(SCOPE_SCHEMA) + ': '
                      + repr(document.get('schema_version')))
    project = document.get('project_id')
    if not isinstance(project, str) or not SCOPE_PROJECT_ID.fullmatch(project):
        errors.append(SCOPE_CONTRACT + ' project_id must be lowercase kebab-case text: ' + repr(project))
    elif project != SCOPE_PROJECT:
        errors.append(SCOPE_CONTRACT + ' declares a different project: ' + project + ' is not the '
                      'toolkit identity ' + SCOPE_PROJECT + '. A fork of this toolkit keeps '
                      + SCOPE_PROJECT + '; an independent application keeps its own identity, root '
                      'and repository.')
    if not isinstance(document.get('purpose'), str) or not document['purpose'].strip():
        errors.append(SCOPE_CONTRACT + ' purpose must record the reviewed policy for this project '
                      'scope: registering an independent application is a reviewed change with a '
                      'written note, not a new top-level folder')
    registered = {}
    for kind in SCOPE_KINDS:
        names = document.get(kind)
        if not isinstance(names, list) or not names:
            errors.append(SCOPE_CONTRACT + ' ' + kind
                          + ' must be a nonempty list of top-level names')
            continue
        for name in names:
            problems = _scope_entry_errors(name, kind, registered)
            if problems:
                errors.extend(problems)
                continue
            registered[folded(name)] = name
    if folded(SCOPE_CONTRACT) not in registered:
        errors.append(SCOPE_CONTRACT + ' must register itself in files: the contract that decides '
                      'the project scope may not sit outside it')
    if errors:
        return errors
    return _scope_entries(root, registered)


def inspect(root):
    errors = scope_errors(root)
    files = [p for p in root.rglob('*') if not SKIPPED & set(p.relative_to(root).parts) and p.is_file()]
    for path in files:
        if path.is_symlink():
            errors.append(f'Symlink excluded from distribution: {path.relative_to(root)}')
            continue
        if path.suffix == '.py':
            try:
                ast.parse(path.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeError) as exc:
                errors.append(f'Invalid Python: {path.relative_to(root)}: {exc}')
        if path.suffix != '.md':
            continue
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'```.*?```', '', text, flags=re.S)
        text = re.sub(r'`[^`]*`', '', text)
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if re.match(r'(?:[a-zA-Z][\w+.-]*:|#)', target):
                continue
            local = unquote(target.split('#', 1)[0])
            resolved = (path.parent / local).resolve()
            if root.resolve() not in (resolved, *resolved.parents) or not resolved.exists():
                errors.append(f'Broken or escaping link: {path.relative_to(root)} -> {target}')
    if not (root / 'LICENSE').is_file():
        errors.append('Missing LICENSE')
    if not list((root / '.agents' / 'skills').glob('*/SKILL.md')):
        errors.append('No skills found')
    validator = load_validator()
    validator.REPO = root
    for path in (root / '.agents' / 'skills').glob('*/SKILL.md'):
        errors.extend(f'{path.parent.name}: {error}' for error in validator.check(path.parent.name))
    return errors


def suite_directories(root=ROOT):
    """Every directory whose discovered test modules the gate must run."""
    return [root / '.agents' / 'skills' / name / 'scripts' for name in SUITES] + [root / 'scripts']


def missing_suite_directories(root=ROOT):
    """An absent directory would silently drop its tests from the batched run."""
    return [directory for directory in suite_directories(root) if not directory.is_dir()]


def discovered_modules(directory):
    """Every test module recursive unittest discovery selects under one directory.

    Discovery descends into Python packages exactly as unittest itself does, so a
    nested package's regressions stay covered while caches and plain folders are
    never mistaken for suites. Modules already in the suite directory keep their
    established order and the nested packages follow them.
    """
    found = []

    def walk(folder):
        entries = sorted(folder.iterdir())
        for path in entries:
            if path.is_file() and path.match(TEST_PATTERN):
                found.append(path)
        for path in entries:
            if path.is_dir() and (path / '__init__.py').is_file():
                walk(path)

    if directory.is_dir():
        walk(directory)
    return found


def suite_plan(root=ROOT, python=None):
    """One bounded child invocation per discovered test module, in stable order.

    Splitting discovery into one module per invocation keeps every discovered
    assertion inside the same 60 second bound however much the coverage grows,
    and the plan is recomputed per run so a newly added module is never omitted.
    A nested package module keeps its suite directory as the discovery top level,
    so its package-relative imports resolve as the recursive invocation resolved
    them before the plan was batched.
    """
    python = python or sys.executable
    plan = []
    for directory in suite_directories(root):
        for module in discovered_modules(directory):
            argv = [python, '-m', 'unittest', 'discover', '-s', str(module.parent), '-p', module.name]
            if module.parent != directory:
                argv += ['-t', str(directory)]
            plan.append((module, argv))
    return plan


def run_suites(root=ROOT, python=None, timeout=SUITE_TIMEOUT, runner=subprocess.run):
    """Run every planned module once and return the first failing code, or 0.

    A timeout is a reported gate failure rather than an unhandled traceback, and
    a failing child's exit code propagates instead of being swallowed.
    """
    missing = missing_suite_directories(root)
    for directory in missing:
        print(f'SUITE DIRECTORY MISSING: {directory}', file=sys.stderr)
    if missing:
        return 1
    for module, argv in suite_plan(root, python):
        try:
            result = runner(argv, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            print(f'SUITE TIMED OUT after {timeout}s: {module}', file=sys.stderr)
            return 1
        if result.returncode:
            print(f'SUITE FAILED with exit {result.returncode}: {module}', file=sys.stderr)
            return result.returncode
    return 0


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-tests', action='store_true')
    args = parser.parse_args(argv)
    errors = inspect(root)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    if not args.skip_tests:
        code = run_suites(root)
        if code:
            return code
    print('PASS: public repository structure, Python syntax, links, and requested regressions')
    return 0


if __name__ == '__main__':
    sys.exit(main())
