"""Independent acceptance for the study v2 dependency-closure map and its sufficiency gate.

Written before the implementation and frozen: the implementer may not edit this file. It pins
what an outside reader must be able to rely on, using only the public study entry points:

* v1 is untouched (prompts, navigation text, plan and mandatory content keep their digests);
* the closure arm carries the package import contract, every intra-package import verbatim,
  full signature lines, closure bodies, and reports what a budget omitted;
* the offline gate rejects the v1 selected-map prompts that scored 0/11 and accepts the others.

Every case is offline: no provider is called, no Docker image is needed and nothing is written
outside a disposable directory.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_hosts as e
import repo_map
import test_context_study as study_fixtures

REFERENCE = study_fixtures.REFERENCE

# Recorded from the frozen v1 run of 2026-10-05; these must never move.
V1_FULL_SOURCE_SHA256 = {
    'invoice-summary': 'f62c9e6740733cb6900dcc8f916f3129dcc4fc1e459009684ed1ef2361c9be42',
    'dependency-order': '36d93953bcce32e4c327b8261964dd9c9e10cddedb36337123f47aebb2e43b75',
    'project-path': '90f63bb5cb207185c155dad349d3272ab22e0561fc4e0b046d8d6f2213d387e3',
}
# The v1 navigation text, with the parser version token normalised: a new index generation may
# print a new version, but nothing else in the v1 map may change.
V1_NAVIGATION_SHA256 = {
    'invoice-summary': 'ca6089f57aa1491af94dbbef6f084c487bf0e48bcacfe635078de5728297711d',
    'dependency-order': '6975474cb66aa8638fb4af0b9f7d547aef1942fe8593ee1a4a2af6f55e64cb44',
    'project-path': '5f78b65f89b46d1e89ec7a80bf58d826f59091c115e28d93f63004fbd27640a0',
}
V1_MANDATORY_SHA256 = {
    'invoice-summary': 'aa14beaa7278d323523902cdc346457edd3dd45af1f5e0790da3dfe70feb25ab',
    'dependency-order': '37e36edba7329c65f1cc1899678a7b834991cfeef6a82a9829c7c3b5dae62f83',
    'project-path': 'ebaf35028e4a607d83ddbaba750329bc9a7a3d9efc5df87d184e71c237e42a75',
}
V1_PLAN_SHA256 = 'b85f6bf5f45d9daa8e740e63ef3d39d5e97e99d7a1928367a48c5a0569464b19'

CLOSURE = 'closure-map'
INTRA = re.compile(r'^\s*(?:from\s+src(?:\.[\w.]*)?\s+import\s+.+|import\s+src(?:\.[\w.]*)?)\s*$')
DEFINITION = re.compile(r'^\s*(?:async\s+def|def|class)\s.*:\s*$')


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def payload_of(prompt):
    return json.loads(prompt[len(e.STUDY_PREAMBLE):])


def fixture_sources():
    root = e.study_fixture_root()
    return {path.relative_to(root).as_posix(): path.read_text(encoding='utf-8')
            for path in sorted((root / 'src').glob('*.py'))}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='crewloom-closure-')
        self.addCleanup(self.temp.cleanup)
        self.project = e.materialize_project(Path(self.temp.name) / 'project')
        self.tasks = {task['id']: task for task in e.study_contracts()['tasks']}


class V1IsUntouched(Base):
    def test_the_v1_conditions_and_plan_keep_their_exact_identity(self):
        self.assertEqual(e.CONDITIONS, ('full-source', 'selected-map'))
        plan = e.study_plan(['codex', 'opencode'])
        self.assertEqual(len(plan), 36)
        self.assertEqual(digest(json.dumps(plan, sort_keys=True)), V1_PLAN_SHA256)

    def test_the_v1_prompts_and_map_text_keep_their_digests(self):
        for ident, task in self.tasks.items():
            full, _ = e.study_prompt(task, 'full-source', self.project)
            self.assertEqual(digest(full), V1_FULL_SOURCE_SHA256[ident], ident)
            selected, built = e.study_prompt(task, 'selected-map', self.project)
            navigation = re.sub(r'\[python-ast v\d+\]', '[python-ast vN]',
                                payload_of(selected)['treatment']['navigation'])
            self.assertEqual(digest(navigation), V1_NAVIGATION_SHA256[ident], ident)
            self.assertEqual(built['mandatory_sha256'], V1_MANDATORY_SHA256[ident], ident)


class IndexCapturesDefinitions(Base):
    def test_every_symbol_carries_its_source_line_and_first_docstring_line(self):
        value, _ = repo_map.build(self.project)
        sources = fixture_sources()
        checked = 0
        for path, text in sources.items():
            entry = value['files'][path]
            self.assertGreaterEqual(entry['parser_version'], 3, path)
            lines = text.splitlines()
            for symbol in entry['symbols']:
                self.assertEqual(symbol['signature'], lines[symbol['line'] - 1].strip(), path)
                self.assertTrue(DEFINITION.match(symbol['signature']), symbol['signature'])
                checked += 1
        self.assertGreaterEqual(checked, 30)

    def test_the_first_docstring_line_is_recorded_and_absent_docstrings_are_empty(self):
        value, _ = repo_map.build(self.project)
        for path, text in fixture_sources().items():
            tree = ast.parse(text)
            expected = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    doc = ast.get_docstring(node)
                    expected[node.lineno] = doc.splitlines()[0].strip() if doc else ''
            for symbol in value['files'][path]['symbols']:
                self.assertEqual(symbol['doc'], expected[symbol['line']], path + ':' + symbol['name'])


class ClosurePrompt(Base):
    def prompt(self, ident, condition=CLOSURE):
        prompt, built = e.study_prompt(self.tasks[ident], condition, self.project)
        return prompt, built, payload_of(prompt)

    def test_the_mandatory_content_is_byte_identical_to_full_source(self):
        for ident in self.tasks:
            _, closure_built, closure = self.prompt(ident)
            _, full_built, full = self.prompt(ident, 'full-source')
            self.assertEqual(closure_built['mandatory_sha256'], full_built['mandatory_sha256'], ident)
            self.assertEqual(closure_built['mandatory_sha256'], V1_MANDATORY_SHA256[ident], ident)
            for key in full:
                if key != 'treatment':
                    self.assertEqual(closure[key], full[key], ident + ':' + key)

    def test_the_treatment_has_the_pinned_shape(self):
        for ident in self.tasks:
            treatment = self.prompt(ident)[2]['treatment']
            self.assertEqual(treatment['mode'], CLOSURE)
            for key in ('import_contract', 'imports', 'closure', 'signatures', 'omitted'):
                self.assertIn(key, treatment, ident)
            self.assertIsInstance(treatment['import_contract'], str)
            self.assertIsInstance(treatment['imports'], list)
            self.assertIsInstance(treatment['closure'], list)
            self.assertIsInstance(treatment['signatures'], list)
            self.assertIsInstance(treatment['omitted'], list)

    def test_the_contract_states_the_package_form_and_never_the_relative_one(self):
        for ident in self.tasks:
            contract = self.prompt(ident)[2]['treatment']['import_contract']
            self.assertIn('src.', contract, ident)
            self.assertNotIn('from .', contract, ident)

    def test_every_intra_package_import_appears_verbatim_and_nothing_else_is_invented(self):
        expected = set()
        for path, text in fixture_sources().items():
            for line in text.splitlines():
                if INTRA.match(line):
                    expected.add((path, line.strip()))
        self.assertGreaterEqual(len(expected), 3)
        for ident in self.tasks:
            imports = self.prompt(ident)[2]['treatment']['imports']
            self.assertEqual({(item['path'], item['statement']) for item in imports}, expected, ident)

    def test_signature_lines_are_complete_and_carry_their_parameters(self):
        for ident, task in self.tasks.items():
            treatment = self.prompt(ident)[2]['treatment']
            helper = e.TASK_SOURCES[ident]['helper']
            covered = {item['path'] for item in treatment['closure']} | {helper}
            listed = {}
            for item in treatment['signatures']:
                listed.setdefault(item['path'], []).append(item['signature'])
            for path, text in fixture_sources().items():
                lines = [line.strip() for line in text.splitlines() if DEFINITION.match(line)]
                if path in covered or not lines:
                    continue
                self.assertEqual(listed.get(path), lines, ident + ':' + path)
        parameterised = [item['signature'] for item in
                         self.prompt('invoice-summary')[2]['treatment']['signatures']]
        self.assertTrue(any('(' in line and ',' in line for line in parameterised))

    def test_the_prompt_is_far_smaller_than_full_source_and_close_to_the_v1_map(self):
        for ident in self.tasks:
            closure, _, _ = self.prompt(ident)
            full, _, _ = self.prompt(ident, 'full-source')
            selected, _, _ = self.prompt(ident, 'selected-map')
            self.assertLess(len(closure.encode()), 0.6 * len(full.encode()), ident)
            self.assertLessEqual(len(closure.encode()), len(selected.encode()) + 4096, ident)

    def test_the_prompt_is_deterministic_and_independent_of_file_times(self):
        first = self.prompt('dependency-order')[0]
        for path in (self.project / 'src').glob('*.py'):
            os.utime(path, (1, 1))
        self.assertEqual(self.prompt('dependency-order')[0], first)
        other = e.materialize_project(Path(self.temp.name) / 'second')
        again, _ = e.study_prompt(self.tasks['dependency-order'], CLOSURE, other)
        self.assertEqual(again, first)

    def test_an_unknown_condition_is_still_refused(self):
        with self.assertRaises(ValueError):
            e.study_prompt(self.tasks['project-path'], 'closure-maps', self.project)


class ClosureContext(unittest.TestCase):
    """The lower-level builder on a synthetic package named differently from the fixture."""

    def build(self, files, budget=6144, required=('pkg/a.py',)):
        folder = tempfile.TemporaryDirectory(prefix='crewloom-closure-synthetic-')
        self.addCleanup(folder.cleanup)
        source = Path(folder.name) / 'fixture'
        (source / 'pkg').mkdir(parents=True)
        (source / 'crewloom.project.json').write_text(json.dumps({
            'schema_version': 1, 'project_id': 'closure-synthetic',
            'description': 'Synthetic closure fixture.', 'source_roots': ['pkg'], 'exclude': []}))
        for name, text in files.items():
            (source / name).write_text(text, encoding='utf-8')
        project = e.materialize_project(Path(folder.name) / 'project', source)
        value, _ = repo_map.build(project)
        return repo_map.closure_context(project, value, list(required), budget), value

    FILES = {
        'pkg/__init__.py': '',
        'pkg/a.py': 'from pkg.b import fb\n\n\ndef fa():\n    return fb()\n',
        'pkg/b.py': 'from pkg.c import fc\n\n\ndef fb():\n    """B helper."""\n    return fc()\n',
        'pkg/c.py': '"""' + 'x' * 9000 + '"""\n\n\ndef fc():\n    return 1\n',
        'pkg/d.py': 'def fd(x, y=2):\n    """Unrelated helper."""\n    return x + y\n',
    }

    def test_the_package_name_is_derived_from_the_repository_not_hard_coded(self):
        result, _ = self.build(self.FILES)
        self.assertIn('pkg.', result['import_contract'])
        self.assertNotIn('src.', result['import_contract'])
        self.assertEqual({(item['path'], item['statement']) for item in result['imports']},
                         {('pkg/a.py', 'from pkg.b import fb'), ('pkg/b.py', 'from pkg.c import fc')})

    def test_a_body_is_followed_transitively_and_an_oversized_one_degrades_to_signatures(self):
        result, _ = self.build(self.FILES)
        self.assertEqual([item['path'] for item in result['closure']], ['pkg/b.py'])
        self.assertEqual(result['closure'][0]['text'], self.FILES['pkg/b.py'])
        signatures = {(item['path'], item['signature']): item['doc'] for item in result['signatures']}
        self.assertIn(('pkg/c.py', 'def fc():'), signatures)
        self.assertEqual(signatures[('pkg/d.py', 'def fd(x, y=2):')], 'Unrelated helper.')
        self.assertEqual(result['omitted'], [])
        for item in result['signatures']:
            self.assertNotEqual(item['path'], 'pkg/a.py')

    def test_the_closure_follows_two_levels_when_everything_fits(self):
        files = dict(self.FILES)
        files['pkg/c.py'] = 'def fc():\n    return 1\n'
        result, _ = self.build(files)
        self.assertEqual([item['path'] for item in result['closure']], ['pkg/b.py', 'pkg/c.py'])

    def test_a_tight_budget_reports_what_it_dropped_and_never_loses_a_module_silently(self):
        files = {'pkg/__init__.py': '', 'pkg/a.py': 'from pkg.m0 import f0\n\n\ndef fa():\n    pass\n'}
        for number in range(6):
            nxt = 'from pkg.m%d import f%d\n' % (number + 1, number + 1) if number < 5 else ''
            files['pkg/m%d.py' % number] = nxt + 'def f%d(alpha, beta=%d):\n    """Doc %d."""\n    pass\n' % (
                number, number, number)
        result, value = self.build(files, budget=1024)
        accounted = ({item['path'] for item in result['closure']} | {item['path'] for item in result['signatures']}
                     | set(result['omitted']) | {'pkg/a.py'})
        for path, entry in value['files'].items():
            if entry['symbols']:
                self.assertIn(path, accounted, path)
        self.assertTrue(result['omitted'])
        serialised = json.dumps({key: result[key] for key in
                                 ('import_contract', 'imports', 'closure', 'signatures', 'omitted')},
                                separators=(',', ':'), ensure_ascii=False)
        self.assertLessEqual(len(serialised.encode()), 1024)

    def test_mandatory_imports_that_cannot_fit_refuse_instead_of_truncating(self):
        files = {'pkg/__init__.py': '', 'pkg/a.py': 'def fa():\n    pass\n'}
        for number in range(80):
            files['pkg/n%02d.py' % number] = 'from pkg.a import fa\n\n\ndef g%d():\n    return fa()\n' % number
        with self.assertRaises(ValueError):
            self.build(files, budget=1024)

    def test_budget_bounds_match_the_existing_map(self):
        for bad in (1023, 65537, '6144', None):
            with self.assertRaises(ValueError):
                self.build(self.FILES, budget=bad)

    def test_a_missing_required_path_is_refused(self):
        with self.assertRaises(ValueError):
            self.build(self.FILES, required=('pkg/not_there.py',))


class SufficiencyGate(Base):
    def gate(self, ident, condition, reference):
        return e.study_sufficiency(self.tasks[ident], condition, reference, self.project)

    def test_the_v1_selected_map_prompts_that_scored_zero_are_rejected_before_any_call(self):
        for ident, task in self.tasks.items():
            result = self.gate(ident, 'selected-map', REFERENCE[task['output']])
            self.assertFalse(result['sufficient'], ident)
            self.assertTrue(any('import form' in item for item in result['missing']), ident)

    def test_full_source_and_the_closure_map_are_accepted_for_every_task(self):
        for ident, task in self.tasks.items():
            for condition in ('full-source', CLOSURE):
                result = self.gate(ident, condition, REFERENCE[task['output']])
                self.assertTrue(result['sufficient'], ident + ':' + condition + ':' + str(result['missing']))
                self.assertEqual(result['missing'], [])

    def test_a_reference_importing_something_no_prompt_defines_is_rejected_everywhere(self):
        reference = ('from src.money import format_amount, nonexistent_helper\n\n\n'
                     'def summarize(records):\n    return format_amount(records)\n')
        for condition in ('full-source', CLOSURE):
            result = self.gate('invoice-summary', condition, reference)
            self.assertFalse(result['sufficient'], condition)
            self.assertTrue(any('nonexistent_helper' in item for item in result['missing']), condition)

    def test_a_reference_with_only_standard_library_imports_needs_no_import_form(self):
        reference = 'import unicodedata\n\n\ndef summarize(records):\n    return unicodedata.normalize("NFC", "x")\n'
        result = self.gate('invoice-summary', 'selected-map', reference)
        self.assertTrue(result['sufficient'], result['missing'])

    def test_a_relative_import_in_the_reference_is_never_sufficient(self):
        reference = 'from .money import format_amount\n\n\ndef summarize(records):\n    return format_amount(records)\n'
        for condition in ('full-source', CLOSURE):
            self.assertFalse(self.gate('invoice-summary', condition, reference)['sufficient'], condition)

    def test_an_unknown_condition_or_unparsable_reference_is_refused(self):
        with self.assertRaises(ValueError):
            self.gate('invoice-summary', 'closure-maps', REFERENCE['src/ledger.py'])
        with self.assertRaises(ValueError):
            self.gate('invoice-summary', CLOSURE, 'def broken(:\n')

    def test_the_gate_reads_but_never_writes_the_project(self):
        before = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*')
                  if p.is_file() and '.git' not in p.relative_to(self.project).parts
                  and '.crewloom' not in p.relative_to(self.project).parts}
        self.gate('dependency-order', CLOSURE, REFERENCE['src/scheduler.py'])
        after = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*')
                 if p.is_file() and '.git' not in p.relative_to(self.project).parts
                 and '.crewloom' not in p.relative_to(self.project).parts}
        self.assertEqual(after, before)


class PlanV2(Base):
    def test_the_preregistered_seed_arms_and_size_are_pinned(self):
        self.assertEqual(e.STUDY_V2_SEED, 20261006)
        self.assertEqual(e.CONDITIONS_V2, ('full-source', CLOSURE))
        plan = e.study_plan_v2(['codex'])
        self.assertEqual(len(plan), 18)
        keys = {(item['host'], item['task'], item['condition'], item['repeat']) for item in plan}
        self.assertEqual(len(keys), 18)
        self.assertEqual({item['condition'] for item in plan}, set(e.CONDITIONS_V2))
        self.assertEqual({item['repeat'] for item in plan}, {1, 2, 3})

    def test_the_plan_is_deterministic_and_differs_from_v1_order(self):
        self.assertEqual(e.study_plan_v2(['codex']), e.study_plan_v2(['codex']))
        self.assertNotEqual(e.study_plan_v2(['codex']), e.study_plan(['codex']))

    def test_the_plan_refuses_unknown_hosts_and_repeats_like_v1(self):
        with self.assertRaises(ValueError):
            e.study_plan_v2(['nobody'])
        with self.assertRaises(ValueError):
            e.study_plan_v2([])
        with self.assertRaises(ValueError):
            e.study_plan_v2(['codex'], repeats=0)


if __name__ == '__main__':
    unittest.main()
