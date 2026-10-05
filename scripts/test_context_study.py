"""Controlled context study: frozen protocol, held-out separation, blind independent grading.

The held-out cases, their expected values and this grader's oracle never appear in
a generation prompt or in the fixture source inventory. The parent runs the live
36-call study; everything here runs offline against Docker with no provider call.
"""
import ast
import inspect
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import evaluate_hosts as e
import repo_map
import workflow as w

LIB = Path(__file__).resolve().parents[1]
TASKS = {task['id']: task for task in e.study_contracts()['tasks']}

# Correct references for the three frozen APIs. They exist only in this acceptance
# suite: the generation prompt never sees them and the candidate never receives the
# expectation they are compared against.
REFERENCE = {}
REFERENCE['src/ledger.py'] = '''"""Invoice totals grouped by currency and category."""
import unicodedata

from src.money import format_amount, parse_amount, total_of


def _category(value):
    if not isinstance(value, str):
        raise ValueError('category must be a string')
    text = unicodedata.normalize('NFKC', value).strip().casefold()
    if not text:
        raise ValueError('category must stay nonempty')
    return text


def _currency(value):
    if not isinstance(value, str):
        raise ValueError('currency must be a string')
    text = value.strip().upper()
    if len(text) != 3 or not all('A' <= letter <= 'Z' for letter in text):
        raise ValueError('currency must be three ASCII letters')
    return text


def summarize(records):
    """Group exact invoice totals by currency and category."""
    if not isinstance(records, list):
        raise TypeError('records must be a list')
    groups = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('each record must be an object')
        amount = parse_amount(record.get('amount'), 'amount')
        key = (_currency(record.get('currency')), _category(record.get('category')))
        groups.setdefault(key, []).append(amount)
    return [{'currency': currency, 'category': category, 'total': format_amount(total_of(amounts))}
            for (currency, category), amounts in sorted(groups.items())]
'''
REFERENCE['src/scheduler.py'] = '''"""Deterministic topological task order."""
from src.scheduling import check_task


def plan(tasks):
    """Order every task after its dependencies, highest priority first."""
    if not isinstance(tasks, list):
        raise TypeError('tasks must be a list')
    normalized = []
    identifiers = set()
    for record in tasks:
        item = check_task(record)
        if item['id'] in identifiers:
            raise ValueError('duplicate task id: ' + item['id'])
        identifiers.add(item['id'])
        normalized.append(item)
    for item in normalized:
        for dependency in item['depends_on']:
            if dependency not in identifiers:
                raise ValueError('unknown dependency: ' + dependency)
            if dependency == item['id']:
                raise ValueError('task depends on itself: ' + item['id'])
    order = []
    done = set()
    remaining = {item['id']: item for item in normalized}
    while remaining:
        ready = [name for name, item in remaining.items()
                 if all(dependency in done for dependency in item['depends_on'])]
        if not ready:
            raise ValueError('dependency cycle')
        chosen = min(ready, key=lambda name: (-remaining[name]['priority'], name))
        order.append(chosen)
        done.add(chosen)
        del remaining[chosen]
    return order
'''
REFERENCE['src/paths.py'] = '''"""Project-contained resolution for a declared relative path."""
from pathlib import Path

from src.pathutil import contained, is_hardlinked, is_linked, regular_file_below, split_relative


def resolve_project_path(root, relative):
    """Resolve one declared project-relative path, refusing every escape."""
    if not isinstance(root, Path):
        raise TypeError('root must be a pathlib.Path')
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('root must be an existing absolute directory')
    parts = split_relative(relative)
    if regular_file_below(root, parts) is not None:
        raise ValueError('a parent component is a regular file')
    if is_linked(root, parts):
        raise ValueError('a path component is a symbolic link')
    target = root.joinpath(*parts)
    if is_hardlinked(target):
        raise ValueError('destination is a hardlinked file')
    if not contained(root, target):
        raise ValueError('destination escapes the project root')
    return target
'''

# Intentionally wrong references, used only to prove the grader discriminates.
WRONG = {
    # Rounds each record instead of each finished group, and never groups.
    'src/ledger.py': '''"""Wrong on purpose: rounds per record and ignores grouping."""
from src.money import format_amount, parse_amount


def summarize(records):
    if not isinstance(records, list):
        raise TypeError('records must be a list')
    rows = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('each record must be an object')
        rows.append({'currency': record['currency'], 'category': record['category'],
                     'total': format_amount(parse_amount(record['amount']))})
    return rows
''',
    # Takes the first ready task instead of the highest priority one.
    'src/scheduler.py': '''"""Wrong on purpose: input order decides instead of priority."""
from src.scheduling import check_task


def plan(tasks):
    if not isinstance(tasks, list):
        raise TypeError('tasks must be a list')
    order = []
    done = set()
    remaining = {}
    for record in tasks:
        item = check_task(record)
        remaining[item['id']] = item
    while remaining:
        ready = [name for name, item in remaining.items()
                 if all(dependency in done for dependency in item['depends_on'])]
        if not ready:
            raise ValueError('dependency cycle')
        chosen = sorted(ready)[0]
        order.append(chosen)
        done.add(chosen)
        del remaining[chosen]
    return order
''',
    # Follows a symlink and accepts a hardlinked destination.
    'src/paths.py': '''"""Wrong on purpose: follows links and accepts a hardlinked destination."""
from pathlib import Path

from src.pathutil import is_hardlinked, split_relative


def resolve_project_path(root, relative):
    if not isinstance(root, Path):
        raise TypeError('root must be a pathlib.Path')
    parts = split_relative(relative)
    target = root.joinpath(*parts)
    return target.resolve()
''',
}

# A candidate that reports success instead of doing the work.
SPOOFED = {
    'src/ledger.py': '''"""Grade spoofing: reports its own pass counters instead of working."""
import pathlib

PASSED = 11
TOTAL = 11


def summarize(records):
    """Pretend every case passed and record the claim in the output module."""
    pathlib.Path('claimed-grade.json').write_text('{"passed": 11, "total": 11}')
    return [{'currency': 'PASS', 'category': 'pass', 'total': '11.00'}]
''',
    'src/scheduler.py': '''"""Grade spoofing: returns a constant answer for every input."""
PASSED = 11
TOTAL = 11


def plan(tasks):
    return ['a']
''',
    'src/paths.py': '''"""Grade spoofing: always answers one fixed relative path."""
PASSED = 11
TOTAL = 11


def resolve_project_path(root, relative):
    from pathlib import Path
    return Path(root) / 'src' / 'hardlinked.txt'
''',
}

# A candidate that tries to edit its supplied inputs while it runs.
MUTATING = {
    'src/ledger.py': '''"""Wrong on purpose: tries to edit the supplied input before answering."""
import pathlib


def summarize(records):
    try:
        pathlib.Path('case.json').write_text('{"api":"summarize","input":[]}')
    except OSError:
        pass
    if not isinstance(records, list):
        raise TypeError('records must be a list')
    return [{'currency': 'XXX', 'category': 'xxx', 'total': '0.00'}]
''',
    'src/scheduler.py': '''"""Wrong on purpose: tries to overwrite its own source file."""
import pathlib


def plan(tasks):
    try:
        pathlib.Path(__file__).write_text('# overwritten by the candidate\\n')
    except OSError:
        pass
    if not isinstance(tasks, list):
        raise TypeError('tasks must be a list')
    return ['b']
''',
    'src/paths.py': '''"""Wrong on purpose: tries to delete a supplied fixture file."""
import pathlib


def resolve_project_path(root, relative):
    try:
        pathlib.Path(root, 'src', 'existing.txt').unlink()
    except OSError:
        pass
    from pathlib import Path
    return Path(root) / 'src' / 'new.txt'
''',
}

# The same three candidates with their write attempts removed, used to show that
# mutating an input buys a candidate nothing at all.
MUTATING_CONTROL = {
    'src/ledger.py': '''"""Control: the wrong answer without the write attempt."""
def summarize(records):
    if not isinstance(records, list):
        raise TypeError('records must be a list')
    return [{'currency': 'XXX', 'category': 'xxx', 'total': '0.00'}]
''',
    'src/scheduler.py': '''"""Control: the wrong answer without the write attempt."""
def plan(tasks):
    if not isinstance(tasks, list):
        raise TypeError('tasks must be a list')
    return ['b']
''',
    'src/paths.py': '''"""Control: the wrong answer without the write attempt."""
def resolve_project_path(root, relative):
    from pathlib import Path
    return Path(root) / 'src' / 'new.txt'
''',
}

# The same three answers, each preceded by an attempt to raise its own file modes and
# then write. The stage is mounted read-only, so these attempts are refused outright;
# the point of the comparison is that forcing past the modes buys nothing at all.
ESCAPING = {
    'src/ledger.py': '''"""Wrong on purpose: raises its own file modes, rewrites the input, answers."""
import os
import pathlib


def summarize(records):
    try:
        os.chmod('case.json', 0o644)
        pathlib.Path('case.json').write_text('{"api":"summarize","input":[]}')
    except OSError:
        pass
    if not isinstance(records, list):
        raise TypeError('records must be a list')
    return [{'currency': 'XXX', 'category': 'xxx', 'total': '0.00'}]
''',
    'src/scheduler.py': '''"""Wrong on purpose: raises its own file modes and rewrites the input."""
import os
import pathlib


def plan(tasks):
    try:
        os.chmod('.', 0o777)
        pathlib.Path('case.json').write_text('{"api":"plan","input":[]}')
    except OSError:
        pass
    if not isinstance(tasks, list):
        raise TypeError('tasks must be a list')
    return ['b']
''',
    'src/paths.py': '''"""Wrong on purpose: raises its own file modes and rewrites the fixture."""
import os
import pathlib


def resolve_project_path(root, relative):
    try:
        os.chmod(str(pathlib.Path(root) / 'src'), 0o777)
        (pathlib.Path(root) / 'src' / 'existing.txt').unlink()
    except OSError:
        pass
    from pathlib import Path
    return Path(root) / 'src' / 'new.txt'
''',
}

DOCKER_AVAILABLE = (os.environ.get('CREWLOOM_DOCKER_TESTS') == '1'
                    and shutil.which('docker') is not None)


class TaskView(dict):
    """A task whose held-out cases cannot be read while a prompt is built."""

    def __init__(self, value):
        super().__init__(value)
        self.read = []

    def __getitem__(self, key):
        self.read.append(key)
        if key == 'cases':
            raise AssertionError('a generation prompt must never read the held-out cases')
        return dict.__getitem__(self, key)


class FrozenProtocolTests(unittest.TestCase):
    """Everything that decides the measurement is fixed before the first call."""

    def test_frozen_contracts_are_verified_byte_for_byte(self):
        contracts = e.study_contracts()
        self.assertEqual(contracts['protocol'], e.STUDY_PROTOCOL)
        self.assertEqual(sorted(t['id'] for t in contracts['tasks']), sorted(e.TASK_SOURCES))
        self.assertTrue(contracts['held_out_from_generation_prompts'])
        self.assertTrue(contracts['all_input_mutability_checks'])
        self.assertEqual(sum(len(task['cases']) for task in contracts['tasks']), 33)
        self.assertEqual(e.CONTRACTS_SHA256,
                         w.digest((Path(w.LIBRARY) / e.CONTRACTS_RELATIVE).read_bytes()))
        with tempfile.TemporaryDirectory() as folder:
            altered = Path(folder) / 'contracts.json'
            altered.write_bytes(json.dumps(dict(contracts, task_count=4)).encode())
            with self.assertRaisesRegex(ValueError, 'frozen digest'):
                e.study_contracts(altered)

    def test_the_held_out_resource_is_packaged_and_never_private_state(self):
        packaged = Path(w.LIBRARY) / e.GRADER_CONTRACTS_RELATIVE
        self.assertTrue(packaged.is_file(), e.GRADER_CONTRACTS_RELATIVE)
        original = Path(w.LIBRARY) / e.SUPERVISOR_CONTRACTS_RELATIVE
        if original.is_file():
            self.assertEqual(packaged.read_bytes(), original.read_bytes())
        self.assertEqual(w.digest(packaged.read_bytes()), e.CONTRACTS_SHA256)
        # The default read is the packaged resource; a distribution ships `examples`
        # and never ships the pruned private `.crewloom` state.
        self.assertEqual(e.CONTRACTS_RELATIVE, e.GRADER_CONTRACTS_RELATIVE)
        self.assertNotIn('.crewloom', e.GRADER_CONTRACTS_RELATIVE)
        # The oracle can never enter the generation inventory, and the runtime
        # refuses a contract placed inside the fixture it would be read from.
        self.assertFalse(packaged.resolve().is_relative_to(e.study_fixture_root()))
        with tempfile.TemporaryDirectory() as folder:
            inside = Path(folder).resolve() / 'project' / 'src'
            inside.mkdir(parents=True)
            (inside / 'contract.json').write_bytes(packaged.read_bytes())
            with patch.object(e, 'study_fixture_root', return_value=inside.parent):
                with self.assertRaisesRegex(ValueError, 'outside the generation fixture'):
                    e.study_contracts(inside / 'contract.json')

    def test_thirty_six_planned_calls_are_balanced_and_seed_frozen(self):
        plan = e.study_plan(['codex', 'opencode'])
        self.assertEqual(len(plan), 36)
        self.assertEqual(plan, e.study_plan(['codex', 'opencode']))
        self.assertNotEqual(plan, e.study_plan(['codex', 'opencode'], seed=e.STUDY_SEED + 1))
        for name in ('codex', 'opencode'):
            for task in e.TASK_SOURCES:
                for condition in e.CONDITIONS:
                    self.assertEqual(sum(1 for trial in plan if trial['host'] == name
                                         and trial['task'] == task and trial['condition'] == condition), 3)
        self.assertEqual(e.FROZEN_MODELS,
                         {'codex': 'gpt-6-sol', 'opencode': 'opencode/space-bunny-free'})

    def test_study_matrix_rejects_unavailable_or_repeated_hosts(self):
        for hosts in ([], ['codex', 'codex'], ['claude'], ['codex', 'claude']):
            with self.subTest(hosts=hosts):
                with self.assertRaises(ValueError):
                    e.study_plan(hosts)
        for repeats in (0, 21, True):
            with self.assertRaises(ValueError):
                e.study_plan(['codex'], repeats)

    def test_claude_is_absent_by_design_and_not_a_measured_result(self):
        self.assertNotIn('claude', e.STUDY_HOSTS)
        self.assertNotIn('claude', e.FROZEN_MODELS)
        self.assertTrue(any('Claude' in limit for limit in e.STUDY_LIMITS))

    def test_fixture_is_real_source_and_carries_no_oracle(self):
        modules = e.study_modules()
        self.assertEqual(len(modules), 10)
        self.assertTrue(all(name.startswith('src/') for name in modules))
        for task in e.TASK_SOURCES:
            helper = e.TASK_SOURCES[task]['helper']
            self.assertIn(helper, modules)
            for relative in e.TASK_SOURCES[task]['support']:
                self.assertIn(relative, modules)
        for name in modules:
            if name.endswith('__init__.py'):
                continue
            with self.subTest(module=name):
                text = (e.study_fixture_root() / name).read_text(encoding='utf-8')
                tree = ast.parse(text)
                self.assertTrue(any(isinstance(node, (ast.FunctionDef, ast.ClassDef))
                                    for node in tree.body), name)
        # The modules each task produces must not already exist in the fixture.
        for task in TASKS.values():
            self.assertNotIn(task['output'], modules)

    def test_fixture_helpers_are_reused_by_the_neighbouring_modules(self):
        root = e.study_fixture_root()
        self.assertIn('from src.money import', (root / 'src/invoicing.py').read_text())
        self.assertIn('from src.scheduling import', (root / 'src/workqueue.py').read_text())
        self.assertIn('from src.pathutil import', (root / 'src/project.py').read_text())
        for name in ('telemetry.py', 'reporting.py', 'notifications.py'):
            text = (root / 'src' / name).read_text()
            for helper in ('money', 'scheduling', 'pathutil'):
                self.assertNotIn('from src.' + helper, text, name)


class ConditionParityTests(unittest.TestCase):
    """The treatment is navigation versus source, never a weaker requirement."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = e.materialize_project(Path(self.temp.name) / 'project')
        self.addCleanup(shutil.rmtree, self.project / '.crewloom', True)

    def payload(self, task, condition):
        prompt, built = e.study_prompt(task, condition, self.project)
        preamble, body = prompt.split('\n', 1)
        return preamble, json.loads(body), built

    def test_mandatory_content_is_byte_identical_across_conditions(self):
        for task in TASKS.values():
            _, full, full_built = self.payload(task, 'full-source')
            _, selected, selected_built = self.payload(task, 'selected-map')
            self.assertEqual(set(full) - {'treatment'}, set(selected) - {'treatment'})
            for key in set(full) - {'treatment'}:
                with self.subTest(task=task['id'], key=key):
                    self.assertEqual(json.dumps(full[key], sort_keys=True, ensure_ascii=False),
                                     json.dumps(selected[key], sort_keys=True, ensure_ascii=False))
            self.assertEqual(full_built['mandatory_sha256'], selected_built['mandatory_sha256'])
            self.assertEqual(full['rules'], selected['rules'])
            self.assertEqual(full['criteria'], selected['criteria'])
            self.assertEqual(full['contract'], selected['contract'])
            self.assertEqual(full['outputs'], selected['outputs'])
            self.assertEqual([item['text'] for item in full['required_bodies']],
                             [item['text'] for item in selected['required_bodies']])
            self.assertEqual([item['text'] for item in full['required_bodies']],
                             [(self.project / e.TASK_SOURCES[task['id']]['helper']).read_text()])

    def test_only_the_treatment_differs_and_it_is_not_padding(self):
        for task in TASKS.values():
            _, full, full_built = self.payload(task, 'full-source')
            _, selected, selected_built = self.payload(task, 'selected-map')
            self.assertEqual(full['treatment']['mode'], 'full-source')
            self.assertEqual(selected['treatment']['mode'], 'selected-map')
            supplied = {item['path'] for item in full['treatment']['sources']}
            supplied.add(e.TASK_SOURCES[task['id']]['helper'])
            self.assertEqual(supplied, set(e.study_modules()))
            self.assertGreater(selected_built['context_bytes'], 1024)
            self.assertGreater(full_built['context_bytes'], selected_built['context_bytes'])
            self.assertNotIn('sources', selected['treatment'])
            self.assertNotIn('navigation', full['treatment'])
            self.assertIn('navigation_stats', selected['treatment'])

    def test_the_selected_map_comes_from_the_real_project_index(self):
        task = TASKS['invoice-summary']
        _, selected, _ = self.payload(task, 'selected-map')
        stats = selected['treatment']['navigation_stats']
        self.assertEqual(stats['indexed_files'], len(e.study_modules()))
        self.assertTrue(stats['index_graph_complete'])
        self.assertEqual(stats['index_config_sha256'], repo_map.module_configuration_digest(self.project))
        self.assertIn('src/money.py', selected['treatment']['navigation'])
        self.assertIn('FunctionDef parse_amount', selected['treatment']['navigation'])

    def test_a_prompt_build_never_reads_the_held_out_cases(self):
        for task in TASKS.values():
            view = TaskView(task)
            for condition in e.CONDITIONS:
                e.study_prompt(view, condition, self.project)
            with self.subTest(task=task['id']):
                self.assertEqual(sorted(set(view.read)), ['api', 'contract', 'id', 'output'])

    def test_no_case_id_or_case_input_reaches_a_prompt(self):
        for task in TASKS.values():
            for condition in e.CONDITIONS:
                prompt, _ = e.study_prompt(task, condition, self.project)
                payload = json.loads(prompt.split('\n', 1)[1])
                with self.subTest(task=task['id'], condition=condition):
                    self.assertNotIn('cases', payload)
                    self.assertNotIn('expected', payload)
                    self.assertEqual(set(payload) - {'treatment'},
                                     {'task_id', 'api', 'contract', 'outputs', 'rules',
                                      'criteria', 'fixture', 'required_bodies'})
                for case in task['cases']:
                    with self.subTest(task=task['id'], condition=condition, case=case['id']):
                        self.assertNotIn('"' + case['id'] + '"', prompt)
                        body = json.dumps(case['input'], ensure_ascii=False,
                                          separators=(',', ':'))
                        if len(body) >= 8:
                            self.assertNotIn(body, prompt)
                        wanted = json.dumps(case['expected'], ensure_ascii=False,
                                            separators=(',', ':'))
                        if len(wanted) >= 8:
                            self.assertNotIn(wanted, prompt)

    def test_unknown_condition_and_missing_helper_are_refused(self):
        task = TASKS['invoice-summary']
        with self.assertRaises(ValueError):
            e.study_prompt(task, 'full-sources', self.project)
        with tempfile.TemporaryDirectory() as folder:
            empty = Path(folder) / 'empty'
            (empty / 'src').mkdir(parents=True)
            (empty / 'crewloom.project.json').write_text('{"source_roots": ["src"], "exclude": []}')
            with self.assertRaises(ValueError):
                e.study_modules(empty)


class GraderBoundaryTests(unittest.TestCase):
    """The oracle stays outside the candidate, and the grader never trusts a claim."""

    def setUp(self):
        self.contracts = e.study_contracts()
        self.captured = []

    def capture(self, stage, argv, image_id, timeout, writable=None):
        """A stand-in executor that records the staged bytes and returns nothing."""
        names = sorted(path.relative_to(stage).as_posix() for path in stage.rglob('*')
                       if path.is_file() and not path.is_symlink())
        self.captured.append({'names': names, 'argv': list(argv), 'writable': writable,
                              'files': {name: (stage / name).read_text(encoding='utf-8', errors='replace')
                                        for name in names}})
        return {'exit_code': 1, 'timed_out': False, 'duration_ms': 1, 'output': 'no output',
                'output_truncated': False, 'image_id': image_id, 'network': 'none'}

    def test_the_staged_candidate_receives_no_oracle_and_no_labels(self):
        with patch.object(e.w, 'docker_execute', side_effect=self.capture):
            for task in self.contracts['tasks']:
                e.grade_study(REFERENCE[task['output']].encode(), task, 'sha256:test',
                              fixture=e.study_fixture_root())
        self.assertEqual(len(self.captured), 33)
        for task in self.contracts['tasks']:
            for case in task['cases']:
                record = self.captured.pop(0)
                names = record['names']
                with self.subTest(task=task['id'], case=case['id']):
                    self.assertEqual(record['argv'], ['python3', 'probe/probe.py'])
                    # An empty writable list is the boundary: the executor mounts the
                    # stage read-only, and the candidate's result travels back over a
                    # dedicated descriptor from an isolated child process.
                    self.assertEqual(record['writable'], ())
                    self.assertNotIn('expected', ' '.join(names))
                    self.assertNotIn('grade', ' '.join(names))
                    self.assertIn('case.json', names)
                    self.assertEqual(sorted(json.loads(record['files']['case.json'])),
                                     ['api', 'call', 'input'])
                    self.assertEqual(json.loads(record['files']['case.json'])['input'], case['input'])
                    self.assertEqual(json.loads(record['files']['output.json']), {'output': task['output']})
                    for name, text in record['files'].items():
                        self.assertNotIn(task['id'] + '/' + case['id'], text, name)
                        self.assertNotIn('full-source', text, name)
                        self.assertNotIn('selected-map', text, name)
                        self.assertNotIn('codex', text, name)
                        self.assertNotIn('opencode', text, name)

    def test_the_trusted_harness_is_itself_fingerprinted(self):
        """A rewritten checker has to show up, so nothing in the stage is exempt."""
        with tempfile.TemporaryDirectory() as folder:
            stage = e.stage_case(folder, REFERENCE['src/ledger.py'].encode(),
                                 TASKS['invoice-summary'], TASKS['invoice-summary']['cases'][1],
                                 e.study_fixture_root(), e.TASK_SOURCES['invoice-summary']['support'],
                                 'ledger.py')
            digests = e._stage_digests(stage)
            self.assertIn('probe/probe.py', digests)
            self.assertIn('probe/run.py', digests)
            self.assertEqual(digests['probe/probe.py'], w.digest(e.PROBE.encode()))
            self.assertEqual(digests['probe/run.py'], w.digest(e.RUNNER.encode()))
            self.assertIn('case.json', digests)
            # Every regular file in the stage is covered, with no excluded subtree.
            self.assertEqual(sorted(digests), sorted(
                path.relative_to(stage).as_posix()
                for path in stage.rglob('*') if path.is_file() and not path.is_symlink()))

    def test_the_sealed_stage_declares_the_executor_mountpoint(self):
        """The runtime creates `/workspace/.crewloom`, so the stage provides it."""
        observed = {}

        def execute(root, argv, image, timeout, writable=None):
            observed['writable'] = writable
            observed['mountpoint'] = (root / '.crewloom').is_dir()
            observed['modes'] = {name: (root / name).stat().st_mode & 0o222
                                 for name in ('case.json', 'probe/probe.py', 'probe/run.py')}
            return {'exit_code': 1, 'timed_out': False, 'duration_ms': 1, 'output': '',
                    'output_truncated': False, 'image_id': image, 'network': 'none'}

        with patch.object(e.w, 'docker_execute', side_effect=execute):
            grade = e.grade_study(REFERENCE['src/ledger.py'].encode(),
                                  TASKS['invoice-summary'], 'sha256:test',
                                  fixture=e.study_fixture_root())
        self.assertEqual(observed['writable'], ())
        self.assertTrue(observed['mountpoint'])
        self.assertEqual(sorted(set(observed['modes'].values())), [0])
        self.assertEqual(grade['checks_total'], 11)

    def test_input_mutation_is_checked_after_a_raised_exception_too(self):
        """Mutate-then-raise must be InputMutated, not the documented refusal.

        The harness is exercised natively here so the post-call comparison is proved on
        the exception path without waiting for a container.
        """
        task = TASKS['invoice-summary']
        case = next(item for item in task['cases'] if item['id'] == 'non-finite')
        self.assertEqual(case['expected'], {'error': 'ValueError'})
        mutating = (b'def summarize(records):\n'
                    b'    records.clear()\n'
                    b'    raise ValueError("invalid amount")\n')
        honest = (b'def summarize(records):\n'
                  b'    raise ValueError("invalid amount")\n')
        for label, source, wanted in (
                ('honest refusal', honest, {'outcome': 'raised', 'exception': 'ValueError'}),
                ('mutate then raise', mutating, {'outcome': 'input-mutated'})):
            with self.subTest(candidate=label), tempfile.TemporaryDirectory() as folder:
                stage = e.stage_case(folder, source, task, case, e.study_fixture_root(),
                                     e.TASK_SOURCES['invoice-summary']['support'], 'ledger.py')
                envelope = self.run_harness(stage)
                self.assertEqual(envelope, wanted)
                self.assertEqual(e.study_score(envelope, e.expected_outcome(case['expected'])),
                                 int(label == 'honest refusal'))

    def test_an_error_shaped_return_is_not_a_raised_builtin(self):
        """The contract's `{'error': ...}` means raise, and only the runner can say so."""
        task = TASKS['invoice-summary']
        case = next(item for item in task['cases'] if item['id'] == 'non-finite')
        returned = b'def summarize(records):\n    return {"error": "ValueError"}\n'
        shadowed = (b'class ValueError(Exception):\n    pass\n'
                    b'def summarize(records):\n    raise ValueError("wrong class")\n')
        subclassed = (b'class Refused(ValueError):\n    pass\n'
                      b'def summarize(records):\n    raise Refused("wrong class")\n')
        wanted = {'outcome': 'raised', 'exception': 'ValueError'}
        for label, source in (('returned dict', returned), ('shadowed name', shadowed),
                              ('subclass', subclassed)):
            with self.subTest(candidate=label), tempfile.TemporaryDirectory() as folder:
                stage = e.stage_case(folder, source, task, case, e.study_fixture_root(),
                                     e.TASK_SOURCES['invoice-summary']['support'], 'ledger.py')
                envelope = self.run_harness(stage)
                self.assertNotEqual(e.recorded_outcome(envelope), wanted, envelope)
                self.assertFalse(e.study_score(envelope, e.expected_outcome(case['expected'])))

    def test_only_the_three_documented_envelopes_are_accepted(self):
        task = TASKS['invoice-summary']
        case = next(item for item in task['cases'] if item['id'] == 'non-finite')
        self.assertEqual(e.expected_outcome(case['expected']),
                         {'outcome': 'raised', 'exception': 'ValueError'})
        self.assertEqual(e.expected_outcome([]), {'outcome': 'value', 'value': []})
        self.assertIsNotNone(e.recorded_outcome({'outcome': 'value', 'value': None}))
        for forged in ({'outcome': 'raised'}, {'outcome': 'passed'}, {'outcome': 'value'},
                       {'outcome': 'raised', 'exception': 'ValueError', 'passed': 11},
                       {'error': 'ValueError'}, [], 'raised', None):
            with self.subTest(envelope=forged):
                self.assertIsNone(e.recorded_outcome(forged))
                self.assertFalse(e.study_score(forged, e.expected_outcome(case['expected'])))

    def run_harness(self, stage):
        """Run the real staged harness natively and return the envelope it publishes."""
        finished = subprocess.run([sys.executable, 'probe/probe.py'], cwd=str(stage),
                                  capture_output=True, text=True)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        return json.loads(finished.stdout)

    def test_the_grader_is_called_without_any_host_or_treatment(self):
        parameters = set(inspect.signature(e.grade_study).parameters)
        self.assertEqual(parameters, {'candidate', 'task', 'image_id', 'timeout', 'case_runs', 'fixture'})
        seen = []

        def spy(candidate, task, image_id, **options):
            seen.append((type(candidate), task['id'], image_id, sorted(options)))
            raise ValueError('stop before the container')

        with patch.object(e, 'grade_study', side_effect=spy):
            with self.assertRaises(ValueError):
                e.grade_study(b'VALUE = 1\n', TASKS['invoice-summary'], 'sha256:test')
        self.assertEqual(seen[0][0], bytes)
        self.assertEqual(seen[0][1], 'invoice-summary')
        self.assertEqual(seen[0][2], 'sha256:test')

    def test_a_candidate_that_claims_a_grade_scores_nothing(self):
        with patch.object(e.w, 'docker_execute', side_effect=self.capture):
            for task in self.contracts['tasks']:
                grade = e.grade_study(SPOOFED[task['output']].encode(), task, 'sha256:test',
                                      fixture=e.study_fixture_root())
                with self.subTest(task=task['id']):
                    self.assertEqual(grade['held_out_pass_count'], 0)
                    self.assertIn('PASSED = 11', SPOOFED[task['output']])

    def test_no_output_nonzero_exit_and_malformed_results_are_honest_failures(self):
        outcomes = [
            {'exit_code': 0, 'timed_out': False, 'duration_ms': 1, 'output': '', 'output_truncated': False,
             'image_id': 'sha256:test', 'network': 'none'},
            {'exit_code': 3, 'timed_out': False, 'duration_ms': 1, 'output': 'boom',
             'output_truncated': False, 'image_id': 'sha256:test', 'network': 'none'},
            {'exit_code': 124, 'timed_out': True, 'duration_ms': 1, 'output': 'timeout',
             'output_truncated': False, 'image_id': 'sha256:test', 'network': 'none'},
        ]
        for outcome in outcomes:
            with self.subTest(outcome=outcome['exit_code']), \
                    patch.object(e.w, 'docker_execute', return_value=outcome):
                grade = e.grade_study(b'def summarize(records):\n    return []\n',
                                      TASKS['invoice-summary'], 'sha256:test',
                                      fixture=e.study_fixture_root())
                self.assertEqual(grade['held_out_pass_count'], 0)
                self.assertEqual(grade['checks_total'], 11)
                self.assertTrue(all(run['error'] for run in grade['runs']))

    def test_a_candidate_that_modifies_a_supplied_file_scores_nothing(self):
        def mutate(stage, argv, image_id, timeout, writable=None):
            target = stage / 'case.json'
            target.chmod(0o644)
            target.write_text('{"api":"summarize","input":[]}')
            return {'exit_code': 0, 'timed_out': False, 'duration_ms': 1, 'output': '',
                    'output_truncated': False, 'image_id': image_id, 'network': 'none'}

        with patch.object(e.w, 'docker_execute', side_effect=mutate):
            grade = e.grade_study(REFERENCE['src/ledger.py'].encode(), TASKS['invoice-summary'],
                                  'sha256:test', fixture=e.study_fixture_root())
        self.assertEqual(grade['held_out_pass_count'], 0)
        self.assertEqual(grade['runs'][0]['mutated_files'], ['case.json'])
        self.assertIn('modified', grade['runs'][0]['error'])
        self.assertNotIn('actual', grade['runs'][0])

    def test_case_input_filesystem_fixtures_are_built_inside_the_stage_only(self):
        observed = {}
        original = e._stage_filesystem

        def spy(stage, outside, kind):
            original(stage, outside, kind)
            observed[kind] = sorted(path.relative_to(stage).as_posix() for path in stage.rglob('*'))

        with patch.object(e, '_stage_filesystem', side_effect=spy), \
                patch.object(e.w, 'docker_execute', side_effect=self.capture):
            for task in self.contracts['tasks']:
                for case in task['cases']:
                    if case.get('fixture'):
                        e.grade_study(REFERENCE[task['output']].encode(), task, 'sha256:test',
                                      fixture=e.study_fixture_root(), case_runs=1)
        self.assertEqual(sorted(observed), ['hardlink', 'ordinary', 'symlink-inside', 'symlink-outside'])
        self.assertIn('src/existing.txt', observed['ordinary'])
        self.assertIn('linked', observed['symlink-outside'])
        self.assertIn('src/hardlinked.txt', observed['hardlink'])
        self.assertIn('seed.txt', observed['hardlink'])

    def test_the_hardlink_fixture_uses_the_python39_api(self):
        """`Path.hardlink_to` is 3.10+, so the stage builds the link with `os.link`."""
        self.assertNotIn('hardlink_to(', Path(e.__file__).read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder) / 'project'
            (stage / 'src').mkdir(parents=True)
            e._stage_filesystem(stage, Path(folder) / 'outside-project', 'hardlink')
            linked = stage / 'src' / 'hardlinked.txt'
            seed = stage / 'seed.txt'
            self.assertTrue(linked.is_file())
            self.assertEqual(linked.stat().st_nlink, 2)
            self.assertEqual(seed.stat().st_nlink, 2)
            self.assertEqual(linked.read_text(encoding='utf-8'), 'hardlink source\n')

    def test_external_comparison_never_uses_a_candidate_reported_flag(self):
        self.assertTrue(e.study_score([{'currency': 'USD', 'category': 'design', 'total': '13.00'}],
                                      [{'currency': 'USD', 'category': 'design', 'total': '13.00'}]))
        self.assertFalse(e.study_score({'passed': 11, 'total': 11}, []))
        self.assertFalse(e.study_score({'passed': 11}, {'error': 'ValueError'}))
        self.assertTrue(e.study_score({'error': 'ValueError'}, {'error': 'ValueError'}))
        self.assertFalse(e.study_score({'error': 'InvoiceError'}, {'error': 'ValueError'}))


@unittest.skipUnless(DOCKER_AVAILABLE, 'Docker is required for the isolated grader proof')
class IsolatedGraderProofTests(unittest.TestCase):
    """Actual containers, actual reference and known-bad candidates, no provider."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.image = w.inspect_image(w.DEFAULT_IMAGE)
        except ValueError as exc:
            raise unittest.SkipTest('Study image unavailable: ' + str(exc))

    def grade(self, sources, task_id):
        task = TASKS[task_id]
        return e.grade_study(sources[task['output']].encode(), task, self.image,
                             fixture=e.study_fixture_root())

    def test_correct_references_pass_every_frozen_case(self):
        for task_id in TASKS:
            with self.subTest(task=task_id):
                grade = self.grade(REFERENCE, task_id)
                self.assertEqual(grade['cases_total'], 11)
                self.assertEqual(grade['held_out_total'], 11)
                self.assertEqual(grade['held_out_pass_count'], 11)
                self.assertEqual(grade['mean_pass_rate'], 1.0)
                self.assertEqual([run for run in grade['runs'] if run['passed'] != 1], [])
                for run in grade['runs']:
                    self.assertEqual(run['network'], 'none')
                    self.assertEqual(run['mutated_files'], [])
                    self.assertEqual(run['stage_mount'], 'read-only')
                    self.assertEqual(run['writable_mounts'], 0)
                    self.assertNotIn('error', run)

    # Answers correctly only when the stage refuses every write, even after the
    # candidate has raised its own file modes back.
    WRITE_PROBE = '''
import os as _os

_REFERENCE = {call}
_STATE = []


def _stage_accepts_a_write():
    if _STATE:
        return _STATE[0]
    for name in ('.', 'probe', 'probe/probe.py', 'case.json'):
        try:
            _os.chmod(name, 0o777)
        except OSError:
            pass
    try:
        with open('_write_probe', 'w') as stream:
            stream.write('x')
    except OSError:
        writable = False
    else:
        writable = True
    _STATE.append(writable)
    return writable


def {call}({arguments}):
    return {sentinel} if _stage_accepts_a_write() else _REFERENCE({arguments})
'''

    def test_the_stage_is_really_read_only_inside_the_container(self):
        """A differential, not a mode check: file modes are not the boundary.

        The candidate owns the stage, so it raises its own modes first and then tries
        to create a file. It returns the reference answer only when that write is
        refused, so a read-write mount scores zero on all eleven cases and a read-only
        mount scores eleven.
        """
        for task_id in TASKS:
            task = TASKS[task_id]
            call = task['api'].split('(')[0]
            if call == 'summarize':
                sentinel, arguments = [{'currency': 'LEAK', 'category': 'leak', 'total': '0.00'}], 'value'
            elif call == 'plan':
                sentinel, arguments = ['LEAK'], 'value'
            else:
                sentinel, arguments = 'LEAK', 'root, relative'
            candidate = (REFERENCE[task['output']] + self.WRITE_PROBE.format(
                call=call, arguments=arguments, sentinel=repr(sentinel))).encode()
            with self.subTest(task=task_id):
                grade = e.grade_study(candidate, task, self.image, fixture=e.study_fixture_root())
                self.assertEqual(grade['held_out_pass_count'], 11, grade['runs'])
                self.assertEqual([run['mutated_files'] for run in grade['runs']], [[]] * 11)

    def test_intentionally_wrong_references_are_rejected(self):
        for task_id in TASKS:
            with self.subTest(task=task_id):
                grade = self.grade(WRONG, task_id)
                self.assertLess(grade['held_out_pass_count'], 11)
                self.assertGreater(grade['held_out_pass_count'], 0)

    def test_grade_spoofing_candidates_score_nothing(self):
        for task_id in TASKS:
            with self.subTest(task=task_id):
                self.assertEqual(self.grade(SPOOFED, task_id)['held_out_pass_count'], 0)

    def test_candidates_that_try_to_mutate_supplied_files_gain_nothing(self):
        for task_id in TASKS:
            with self.subTest(task=task_id):
                grade = self.grade(MUTATING, task_id)
                control = self.grade(MUTATING_CONTROL, task_id)
                self.assertEqual(grade['held_out_pass_count'], control['held_out_pass_count'])
                for run in grade['runs']:
                    # The sealed stage refused the write, so the candidate's grade is
                    # exactly what its own honest answer earns.
                    self.assertEqual(run['mutated_files'], [])
                    self.assertTrue(run['supplied_files_read_only'])
                    self.assertEqual(run['network'], 'none')

    def test_a_candidate_that_forces_its_way_past_the_modes_gains_nothing(self):
        """The mount refuses the write, so the attempt is worth exactly nothing.

        File modes were never the boundary and the candidate owns the stage, so the
        only claim worth making is the measurable one: raising its own modes buys no
        part of a grade, because the honest control with the same answer scores the
        same and nothing in the stage is ever modified.
        """
        for task_id in TASKS:
            self.assertIn('os.chmod', ESCAPING[TASKS[task_id]['output']])
            with self.subTest(task=task_id):
                grade = self.grade(ESCAPING, task_id)
                control = self.grade(MUTATING_CONTROL, task_id)
                self.assertEqual(grade['held_out_pass_count'], control['held_out_pass_count'])
                self.assertEqual([run['passed'] for run in grade['runs']],
                                 [run['passed'] for run in control['runs']])
                for run in grade['runs']:
                    self.assertEqual(run['mutated_files'], [])
                    self.assertEqual(run['stage_mount'], 'read-only')

    def test_broken_empty_and_crashing_modules_are_honest_failures(self):
        broken = (b'', b'def summarize(records):\n    return "not the declared shape"\n',
                  b'syntax error here(\n', b'def summarize(records):\n    raise SystemExit(3)\n',
                  b'import os\n\n\ndef summarize(records):\n    os._exit(0)\n')
        for source in broken:
            with self.subTest(source=source[:24]):
                grade = e.grade_study(source, TASKS['invoice-summary'], self.image,
                                      fixture=e.study_fixture_root())
                self.assertEqual(grade['held_out_pass_count'], 0)
                self.assertTrue(all(run['passed'] == 0 for run in grade['runs']))
                self.assertTrue(any(run.get('error') or run.get('actual') for run in grade['runs']))

    def test_an_error_shaped_return_and_a_shadowed_name_score_nothing(self):
        """The documented refusal is the exception, not a dictionary that looks like one."""
        task = TASKS['invoice-summary']
        refusal = b'def summarize(records):\n    raise ValueError("invalid amount")\n'
        for label, source in (
                ('returned error dict',
                 b'def summarize(records):\n    return {"error": "ValueError"}\n'),
                ('shadowed ValueError',
                 b'class ValueError(Exception):\n    pass\n'
                 b'def summarize(records):\n    raise ValueError("wrong class")\n'),
                ('ValueError subclass',
                 b'class Refused(ValueError):\n    pass\n'
                 b'def summarize(records):\n    raise Refused("wrong class")\n')):
            with self.subTest(candidate=label):
                grade = e.grade_study(source, task, self.image, fixture=e.study_fixture_root())
                self.assertEqual(grade['held_out_pass_count'], 0, grade['runs'])
        honest = e.grade_study(refusal, task, self.image, fixture=e.study_fixture_root())
        refused = [run for run in honest['runs'] if run['outcome'] == 'raised']
        self.assertEqual([run['actual'] for run in refused],
                         [{'error': 'ValueError'}] * len(refused))


def _stub_generate(**overrides):
    """A provider stand-in: no network, no CLI, deterministic per trial."""
    def generate(name, prompt, outputs, timeout, model, evidence=None):
        record = {'host': name, 'host_version': 'stub-1', 'model_requested': model,
                  'model_reported': None, 'cost_usd': 0, 'duration_ms': 7,
                  'prompt_bytes': len(prompt.encode()),
                  'usage_metrics': {'input_tokens': 1200, 'uncached_input_tokens': 900,
                                    'cached_input_tokens': 300, 'cache_write_tokens': 0,
                                    'output_tokens': 40, 'reasoning_tokens': 0,
                                    'total_tokens': 1240},
                  'usage': {'steps': []}}
        record.update(overrides)
        return {outputs[0]: 'VALUE = 1\n'}, record
    return generate


def _stub_grade(**overrides):
    def grade(candidate, task, image_id, timeout=None, case_runs=1, fixture=None):
        record = {'task': task['id'], 'held_out_pass_count': 11, 'held_out_total': 11,
                  'checks_total': 11, 'mean_pass_rate': 1.0, 'runs': []}
        record.update(overrides)
        return record
    return grade


@unittest.skipUnless(DOCKER_AVAILABLE, 'Docker is required to freeze the image id')
class CollectionTests(unittest.TestCase):
    """Protocol frozen first, every attempt retained, one host never stopping the other."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = Path(self.temp.name) / 'study'

    def collect(self, generate=None, grade=None, hosts=('codex', 'opencode'), repeats=1):
        with patch.object(e.host, 'generate', side_effect=generate or _stub_generate()), \
                patch.object(e, 'grade_study', side_effect=grade or _stub_grade()):
            return e.collect_study(self.destination, list(hosts), None, repeats, e.STUDY_SEED)

    def test_protocol_and_both_prompts_exist_before_the_first_call(self):
        calls = []

        def generate(*args, **options):
            calls.append(args)
            self.assertTrue((self.destination / 'protocol.json').is_file())
            self.assertTrue((self.destination / 'contracts.json').is_file())
            return _stub_generate()(*args, **options)

        report = self.collect(generate, repeats=3)
        self.assertEqual(len(calls), 36)
        self.assertEqual(report['protocol']['planned_calls'], 36)
        protocol = json.loads((self.destination / 'protocol.json').read_text())
        self.assertEqual(protocol['contracts_sha256'], e.CONTRACTS_SHA256)
        self.assertEqual(protocol['contracts_relative'], e.GRADER_CONTRACTS_RELATIVE)
        self.assertEqual(protocol['seed'], e.STUDY_SEED)
        self.assertEqual(protocol['models_requested'], e.FROZEN_MODELS)
        self.assertEqual(protocol['image_id'], report['protocol']['image_id'])
        # Everything that decides the measurement is frozen before the first call:
        # grader, executor, transport, container harness, contracts and helper bytes.
        self.assertEqual(protocol['grader_sha256'], w.digest(Path(e.__file__).read_bytes()))
        self.assertEqual(protocol['executor_sha256'], w.digest(Path(w.__file__).read_bytes()))
        self.assertEqual(protocol['transport_sha256'],
                         w.digest(Path(e.host.__file__).read_bytes()))
        self.assertEqual(protocol['harness_sha256'], {'probe': w.digest(e.PROBE.encode()),
                                                      'runner': w.digest(e.RUNNER.encode())})
        self.assertEqual(sorted(protocol['fixture_modules']), sorted(protocol['fixture_sha256']))
        self.assertEqual(protocol['fixture_sha256']['src/money.py'],
                         w.digest((e.study_fixture_root() / 'src/money.py').read_bytes()))
        self.assertEqual(sorted(protocol['helper_sha256']), sorted(e.TASK_SOURCES))
        self.assertEqual(sorted(protocol['prompt_sha256']['invoice-summary']),
                         ['full-source', 'selected-map'])
        for task in TASKS:
            digests = protocol['mandatory_sha256'][task]
            self.assertEqual(sorted(digests), ['full-source', 'selected-map'])
            self.assertEqual(len(set(digests.values())), 1)
            for condition in e.CONDITIONS:
                self.assertTrue((self.destination /
                                 ('prompt-' + task + '-' + condition + '.txt')).is_file())
        self.assertTrue(report['study_complete'])

    def test_every_planned_trial_is_reported_with_the_required_fields(self):
        report = self.collect(repeats=2)
        required = {'submission', 'host', 'task', 'condition', 'repeat', 'order', 'seed', 'status',
                    'context_bytes', 'mandatory_sha256', 'source_sha256', 'model_requested',
                    'model_reported', 'host_version', 'input_tokens', 'uncached_input_tokens',
                    'cached_input_tokens', 'cache_write_tokens', 'output_tokens', 'reasoning_tokens',
                    'total_tokens', 'cost_usd', 'duration_generation_ms', 'duration_grading_ms',
                    'held_out_pass_count', 'held_out_total', 'raw_paths'}
        self.assertEqual(len(report['results']), 24)
        self.assertEqual([row['order'] for row in report['results']], list(range(1, 25)))
        for row in report['results']:
            with self.subTest(row=row['submission']):
                self.assertTrue(required <= set(row))
                self.assertEqual(row['status'], 'scored')
                self.assertIsNone(row['model_reported'])
                self.assertEqual(row['cost_usd'], 0)
                self.assertEqual(row['input_tokens'], 1200)
                self.assertIsNotNone(row['duration_generation_ms'])
                self.assertIsNotNone(row['duration_grading_ms'])
                self.assertEqual(row['raw_paths']['prompt'],
                                 'prompt-' + row['task'] + '-' + row['condition'] + '.txt')
        self.assertEqual(json.loads((self.destination / 'results.json').read_text()), report['results'])

    def test_a_failed_quality_grade_is_retained_and_never_replaced(self):
        quality = {'held_out_pass_count': 4, 'held_out_total': 11, 'checks_total': 11,
                   'mean_pass_rate': 4 / 11, 'runs': []}
        report = self.collect(grade=_stub_grade(**quality), repeats=2)
        self.assertEqual(len(report['results']), 24)
        self.assertTrue(all(row['status'] == 'scored' for row in report['results']))
        self.assertTrue(all(row['held_out_pass_count'] == 4 for row in report['results']))
        for group in report['groups']:
            self.assertEqual(group['failed'], 0)
            self.assertEqual(group['held_out_mean_pass_rate'], 4 / 11)
            self.assertEqual(group['planned'], 2)
        self.assertTrue(report['study_complete'])

    def test_a_generation_failure_is_kept_in_the_denominator_with_no_replacement(self):
        calls = []

        def generate(name, prompt, outputs, timeout, model, evidence=None):
            calls.append((name, prompt))
            if len(calls) == 1:
                raise ValueError('Host returned a malformed event stream')
            return _stub_generate()(name, prompt, outputs, timeout, model, evidence)

        report = self.collect(generate, repeats=2)
        self.assertEqual(len(calls), 24)
        failed = [row for row in report['results'] if row['status'] == 'failed']
        self.assertEqual(len(failed), 1)
        self.assertIn('malformed', failed[0]['error'])
        self.assertIsNone(failed[0]['source_sha256'])
        self.assertIsNone(failed[0]['held_out_pass_count'])
        broken = next(group for group in report['groups']
                      if group['scored'] == 1 and group['failed'] == 1)
        self.assertEqual(broken['status_counts'], {'failed': 1, 'scored': 1})
        self.assertFalse(report['study_complete'])

    def test_an_unavailable_host_stops_only_that_host_and_says_so(self):
        def generate(name, prompt, outputs, timeout, model, evidence=None):
            if name == 'codex':
                raise e.host.HostUnavailable('Install codex and authenticate it locally first')
            return _stub_generate()(name, prompt, outputs, timeout, model, evidence)

        report = self.collect(generate, repeats=2)
        unavailable = [row for row in report['results'] if row['status'] == 'host-unavailable']
        self.assertEqual(len(unavailable), 12)
        self.assertEqual({row['host'] for row in unavailable}, {'codex'})
        self.assertTrue(all('authenticate' in row['error'] for row in unavailable))
        self.assertTrue(all(row['status'] == 'scored' for row in report['results']
                            if row['host'] == 'opencode'))
        for group in report['groups']:
            if group['host'] == 'codex':
                self.assertEqual(group['scored'], 0)
                self.assertEqual(group['failed'], 2)
                self.assertEqual(group['status_counts'], {'host-unavailable': 2})
                self.assertIsNone(group['held_out_mean_pass_rate'])
                self.assertIsNone(group['usage']['input_tokens']['mean'])
            else:
                self.assertEqual(group['scored'], 2)
                self.assertEqual(group['failed'], 0)
        self.assertFalse(report['study_complete'])

    def test_grader_failures_are_recorded_without_losing_the_artifact(self):
        def grade(*args, **options):
            raise ValueError('container refused the stage')

        report = self.collect(grade=grade)
        broken = [row for row in report['results'] if row['status'] == 'grading-failed']
        self.assertEqual(len(broken), 12)
        self.assertTrue(all('grader failed' in row['error'] for row in broken))
        self.assertTrue(all(row['source_sha256'] for row in broken))
        self.assertEqual([row for row in report['results'] if row['status'] == 'scored'], [])

    def test_paired_summaries_report_sample_counts_and_variance(self):
        def grade(candidate, task, image_id, *args, **options):
            return _stub_grade(held_out_pass_count=11 if b'VALUE' in candidate else 0)(
                candidate, task, image_id)

        report = self.collect(grade=grade, repeats=3)
        self.assertEqual(len(report['pairs']), 6)
        for pair in report['pairs']:
            self.assertEqual(pair['paired_repeats'], 3)
            self.assertEqual(pair['held_out_pass_rate']['reported'], 3)
            self.assertEqual(pair['held_out_pass_rate']['mean'], 0.0)
            self.assertEqual(pair['held_out_pass_rate']['variance'], 0.0)
        for group in report['groups']:
            self.assertEqual(group['usage']['input_tokens']['mean'], 1200)
            self.assertEqual(group['usage']['input_tokens']['reported'], 3)
            self.assertEqual(group['cost_usd']['mean'], 0)
        self.assertEqual(report['limits'], list(e.STUDY_LIMITS) + e.study_contracts()['quality_limits'])
        self.assertTrue(any('superiority' in limit for limit in report['limits']))
        self.assertFalse(any('guarantee' in limit or 'will save' in limit
                             for limit in report['limits']))

    def test_existing_evidence_is_never_overwritten(self):
        self.collect()
        with self.assertRaisesRegex(ValueError, 'fresh'):
            self.collect()

    def test_study_models_are_frozen_and_cannot_be_swapped(self):
        with self.assertRaises(ValueError):
            e.collect_study(Path(self.temp.name) / 'other', ['codex'],
                            {'claude': 'some-model'})
        with self.assertRaises(ValueError):
            e.collect_study(Path(self.temp.name) / 'other2', ['claude'])


class FailureLatencyTests(unittest.TestCase):
    """A generation attempt that really ran reports its latency, whatever ended it."""

    GENERATION_SECONDS = 0.05
    GRADING_SECONDS = 0.3

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = None

    def collect(self, generate=None, grade=None, hosts=('codex', 'opencode'), repeats=1, name='study'):
        self.destination = Path(self.temp.name) / name
        with patch.object(e.w, 'inspect_image', return_value='sha256:offline-fixture'), \
                patch.object(e.host, 'generate', side_effect=generate or _stub_generate()), \
                patch.object(e, 'grade_study', side_effect=grade or _stub_grade()):
            return e.collect_study(self.destination, list(hosts), None, repeats, e.STUDY_SEED)

    def slow_grade(self, record=None):
        record = record or _stub_grade()

        def grade(*args, **options):
            time.sleep(self.GRADING_SECONDS)
            return record(*args, **options)

        return grade

    def test_a_failed_generation_keeps_its_measured_latency_and_no_usage(self):
        def generate(*args, **options):
            raise ValueError('Host returned a malformed event stream')

        report = self.collect(generate)
        self.assertEqual(len(report['results']), 12)
        for row in report['results']:
            self.assertEqual(row['status'], 'failed')
            self.assertIs(type(row['duration_generation_ms']), int)
            self.assertGreaterEqual(row['duration_generation_ms'], 0)
            self.assertIsNone(row['duration_grading_ms'])
            for key in ('source_sha256', 'cost_usd', 'input_tokens', 'uncached_input_tokens',
                        'cached_input_tokens', 'cache_write_tokens', 'output_tokens',
                        'reasoning_tokens', 'total_tokens', 'held_out_pass_count'):
                self.assertIsNone(row[key], key)
        for group in report['groups']:
            self.assertEqual(group['duration_generation_ms']['reported'], group['planned'])
            self.assertIsNotNone(group['duration_generation_ms']['mean'])
            self.assertIsNone(group['duration_grading_ms']['mean'])
        self.assertFalse(report['study_complete'])

    def test_the_generation_clock_never_absorbs_grading_time(self):
        def generate(name, prompt, outputs, timeout, model, evidence=None):
            time.sleep(self.GENERATION_SECONDS)
            return _stub_generate(duration_ms=None)(name, prompt, outputs, timeout, model, evidence)

        report = self.collect(generate, self.slow_grade(), hosts=('codex',))
        self.assertEqual(len(report['results']), 6)
        for row in report['results']:
            self.assertEqual(row['status'], 'scored')
            self.assertGreaterEqual(row['duration_generation_ms'], self.GENERATION_SECONDS * 1000)
            self.assertLess(row['duration_generation_ms'], self.GRADING_SECONDS * 1000,
                            'the grading clock must stay out of the generation latency')
            self.assertGreaterEqual(row['duration_grading_ms'], self.GRADING_SECONDS * 1000)

    def test_a_transport_reported_generation_latency_is_kept_verbatim(self):
        report = self.collect(grade=self.slow_grade(), hosts=('codex',))
        for row in report['results']:
            self.assertEqual(row['duration_generation_ms'], 7)
            self.assertGreaterEqual(row['duration_grading_ms'], self.GRADING_SECONDS * 1000)

    def test_a_host_that_never_ran_keeps_no_latency_at_all(self):
        def generate(name, prompt, outputs, timeout, model, evidence=None):
            if name == 'codex':
                raise e.host.HostUnavailable('Install codex and authenticate it locally first')
            return _stub_generate()(name, prompt, outputs, timeout, model, evidence)

        report = self.collect(generate, hosts=('codex', 'opencode'), repeats=2)
        unavailable = [row for row in report['results'] if row['status'] == 'host-unavailable']
        self.assertEqual(len(unavailable), 12)
        for row in unavailable:
            self.assertIsNone(row['duration_generation_ms'],
                              'a generation that never started has no latency to report')
            self.assertIsNone(row['raw_paths'])
        for row in report['results']:
            if row['host'] == 'opencode':
                self.assertEqual(row['status'], 'scored')
                self.assertEqual(row['duration_generation_ms'], 7)
        for group in report['groups']:
            if group['host'] == 'codex':
                self.assertEqual(group['duration_generation_ms'],
                                 {'reported': 0, 'mean': None, 'variance': None})
            else:
                self.assertEqual(group['duration_generation_ms']['reported'], group['planned'])

    def test_captured_failure_evidence_is_referenced_only_when_it_exists(self):
        def capturing(name, prompt, outputs, timeout, model, evidence=None):
            Path(evidence).mkdir(parents=True, exist_ok=True)
            (Path(evidence) / 'stderr.log').write_text('transport gave up\n', encoding='utf-8')
            raise ValueError('Host returned a malformed event stream')

        def uncaptured(name, prompt, outputs, timeout, model, evidence=None):
            raise ValueError('Host returned a malformed event stream')

        for label, generate, captured in (('captured', capturing, True),
                                          ('absent', uncaptured, False)):
            with self.subTest(evidence=label):
                report = self.collect(generate, hosts=('codex',), name='study-' + label)
                for row in report['results']:
                    self.assertEqual(row['status'], 'failed')
                    if not captured:
                        self.assertIsNone(row['raw_paths'], 'no path may be invented')
                        continue
                    self.assertEqual(row['raw_paths'], {
                        'transport': row['submission'] + '/transport',
                        'prompt': 'prompt-' + row['task'] + '-' + row['condition'] + '.txt'})
                    self.assertTrue((self.destination / row['raw_paths']['transport']).is_dir())
                    self.assertTrue((self.destination / row['raw_paths']['prompt']).is_file())

    def test_a_grader_failure_keeps_the_generation_latency_and_the_artifact(self):
        def grade(*args, **options):
            raise ValueError('container refused the stage')

        report = self.collect(grade=grade, hosts=('codex',))
        for row in report['results']:
            self.assertEqual(row['status'], 'grading-failed')
            self.assertEqual(row['duration_generation_ms'], 7)
            self.assertIsNone(row['duration_grading_ms'])
            self.assertTrue(row['source_sha256'])
            self.assertTrue((self.destination / row['raw_paths']['artifact']).is_file())

    def test_the_frozen_protocol_plans_one_attempt_per_trial_and_no_retry(self):
        calls = []

        def generate(name, prompt, outputs, timeout, model, evidence=None):
            calls.append((name, prompt))
            return _stub_generate()(name, prompt, outputs, timeout, model, evidence)

        report = self.collect(generate, repeats=e.STUDY_REPEATS)
        self.assertEqual(e.STUDY_PROTOCOL, 'crewloom-context-study-v1')
        self.assertEqual(e.STUDY_REPEATS, 3)
        self.assertEqual(len(calls), 36)
        self.assertEqual(len(report['results']), 36)
        self.assertEqual(report['protocol']['planned_calls'], 36)
        self.assertEqual(report['protocol']['repeats_per_condition'], 3)
        self.assertEqual(report['protocol']['seed'], e.STUDY_SEED)
        self.assertEqual(report['protocol']['models_requested'], e.FROZEN_MODELS)
        self.assertEqual([row['order'] for row in report['results']], list(range(1, 37)))
        self.assertEqual(len({row['submission'] for row in report['results']}), 36)
        self.assertEqual(sorted({row['repeat'] for row in report['results']}), [1, 2, 3])
        self.assertEqual(len(calls), len(report['results']),
                         'every planned trial makes exactly one attempt and is never regenerated')
        self.assertTrue(report['study_complete'])


if __name__ == '__main__':
    unittest.main()