"""Acceptance for the concurrent development example: setup, application semantics, real batch.

The offline classes here run in seconds and prove the parts that need no container: that the
example ships real application code, that the setup command refuses every unsafe destination
and every missing explicit decision before it writes a byte, and that the generated
application actually computes the invoice and planning numbers it claims.

The opt-in class at the end is the real integration evidence. It runs the actual coordinator
over the actual example project with real Git worktrees, real managed Docker execution, real
role context, real ledger evidence, a real credential-reviewed decision and a real
fast-forward, and it runs the published command afterwards. Only the generation transport is
replaced, by a stand-in provider that answers with the example's own shipped module bytes and
records every request it was asked to make. Nothing here says anything about the quality,
latency or cost of any model.
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))

import crewloom_resources as resources  # noqa: E402
import model_host  # noqa: E402
import project_binding as pb  # noqa: E402
import repo_map  # noqa: E402
import task_coordinator as tc  # noqa: E402
import workflow as w  # noqa: E402

EXAMPLE = Path(resources.require('examples/concurrent-development',
                                 'Concurrent development example')).resolve()
PROJECT = EXAMPLE / 'project'
GENERATED = EXAMPLE / 'fixtures' / 'generated'
SETUP_PATH = EXAMPLE / 'setup_project.py'
PROJECT_ID = 'ledgerline-demo'
BATCH = 'ledgerline-batch'
MODEL = 'gpt-4.1-offline-example'
HOST = 'openai'
RPC_CREDENTIAL = 'offline-example-value-not-a-credential'

# Which shipped module the stand-in provider answers each declared output path with.
ARTIFACT_MODULES = {'src/billing.py': 'billing.py', 'src/planning.py': 'planning.py',
                    'src/report.py': 'report.py', 'src/app.py': 'app.py'}
# The held-out study grader contracts must never appear in this example's generation inventory.
STUDY_ONLY_NAMES = ('summarize', 'resolve_project_path')


def load_setup():
    """Import the shipped setup command through the same resource resolver a wheel would use."""
    spec = importlib.util.spec_from_file_location('development_example_setup', SETUP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    written = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module


setup = load_setup()


def stand_in_provider(requests):
    """Answer each generation request from the example's own shipped module bytes.

    The prompt the managed executor actually sent is read back, so every claim about what a
    task generated stays checkable from the recorded request. Declared outputs are returned
    through the adapter's own `validate_artifacts`, and an undeclared path is refused rather
    than invented. No network, CLI or credential is involved.
    """
    def generate(host, prompt, outputs, timeout=180, model=None):
        payload = json.loads(prompt.split('\n', 1)[1])
        requests.append({'host': host, 'model': model, 'task': payload['task'],
                         'outputs': list(payload['outputs']),
                         'inputs': {item['path']: item['text'] for item in payload['inputs']}})
        content = {}
        for relative in outputs:
            name = ARTIFACT_MODULES.get(relative)
            if name is None:
                raise ValueError('the example stand-in has no shipped bytes for ' + relative)
            content[relative] = (GENERATED / name).read_text(encoding='utf-8')
        artifacts = {'artifacts': [{'path': path, 'content': text}
                                   for path, text in content.items()]}
        return model_host.validate_artifacts(artifacts, outputs), {
            'host': host, 'model_reported': None, 'model_requested': model,
            'usage': {'input_tokens': len(prompt),
                      'output_tokens': sum(len(text) for text in content.values())},
            'execution_boundary': 'example stand-in provider; no network, CLI or credential'}
    return generate


def run_setup(destination, host=HOST, model=MODEL, native=False, project_id=PROJECT_ID):
    """Call the shipped setup command exactly as the guide does, and parse its report."""
    argv = ['--destination', str(destination), '--project-id', project_id, '--model-host', host,
            '--model', model, '--batch-id', BATCH]
    if native:
        argv.append('--native-host-cli')
    captured = io.StringIO()
    environment = {'OPENAI_API_KEY': RPC_CREDENTIAL} if host in ('openai', 'anthropic') else {}
    probes = {}
    if host in model_host.CLI_HOSTS:
        probes['return_value'] = {'host': host, 'version': 'offline-example-probe'}
    with mock.patch.dict(os.environ, environment), mock.patch.object(model_host, 'probe', **probes):
        with contextlib.redirect_stdout(captured):
            code = setup.main(argv)
    return code, captured.getvalue()


def git(root, *arguments, check=True):
    return subprocess.run(['git', *arguments], cwd=str(root), env=repo_map.git_environment(),
                          capture_output=True, text=True, timeout=60, check=check)


class ExampleAssetTests(unittest.TestCase):
    """What the repository ships, before anything is copied into a project."""

    def test_every_shipped_python_file_parses(self):
        files = sorted(path for path in EXAMPLE.rglob('*.py') if path.is_file())
        self.assertGreaterEqual(len(files), 10, files)
        for path in files:
            ast.parse(path.read_text(encoding='utf-8'), filename=str(path))

    def test_the_generation_inventory_is_real_application_code(self):
        modules = {name: (GENERATED / name).read_text(encoding='utf-8')
                   for name in ('billing.py', 'planning.py', 'report.py', 'app.py')}
        for name, text in modules.items():
            self.assertGreater(len(text), 1200, name + ' is too thin to be an application module')
            tree = ast.parse(text)
            self.assertTrue([node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)],
                            name + ' defines no function')
        self.assertIn('def compute_invoice(', modules['billing.py'])
        self.assertIn('def schedule(', modules['planning.py'])
        self.assertIn('def build_report(', modules['report.py'])
        self.assertIn("add_argument('--data'", modules['app.py'])

    def test_the_generation_inventory_never_carries_held_out_study_contracts(self):
        for path in sorted(GENERATED.glob('*.py')):
            text = path.read_text(encoding='utf-8')
            for name in STUDY_ONLY_NAMES:
                self.assertNotIn(name, text, path.name + ' must not restate a held-out contract')

    def test_the_reused_helpers_are_copied_from_the_shipped_context_study_example(self):
        study = resources.require('examples/context-study/project/src', 'Context study helpers')
        self.assertEqual((PROJECT / 'src' / 'money.py').read_bytes(),
                         (Path(study) / 'money.py').read_bytes())
        self.assertEqual((PROJECT / 'src' / 'scheduling_support.py').read_bytes(),
                         (Path(study) / 'scheduling.py').read_bytes())

    def test_templates_declare_placeholders_and_no_fallback(self):
        templates = sorted(PROJECT.rglob('*.json'))
        self.assertGreaterEqual(len(templates), 5, templates)
        seen = set()
        for path in templates:
            text = path.read_text(encoding='utf-8')
            json.loads(text)
            for literal in setup.TOKENS:
                if literal in text:
                    seen.add(literal)
            self.assertNotIn('fallback', text.lower(), path.name + ' may not name a fallback')
            lowered = text.lower()
            for banned in ('api_key', 'password', 'secret', 'bearer '):
                self.assertNotIn(banned, lowered, path.name + ' may not carry a credential')
        self.assertEqual(seen, set(setup.TOKENS),
                         'every placeholder must be declared by exactly these templates: '
                         + str(sorted(set(setup.TOKENS) - seen)))

    def test_the_workflows_name_only_roles_the_example_installs(self):
        roles = set()
        for path in sorted((PROJECT / 'workflows').glob('*.json')):
            for step in json.loads(path.read_text(encoding='utf-8'))['steps']:
                roles.add(step['role'])
        self.assertEqual(roles, set(setup.ROLES))

    def test_the_manifest_declares_a_three_task_dag_with_a_combined_acceptance(self):
        document = json.loads((PROJECT / 'coordinator.json').read_text(encoding='utf-8'))
        self.assertEqual([task['id'] for task in document['tasks']],
                         ['billing', 'planning', 'report'])
        self.assertEqual(document['tasks'][2]['depends_on'], ['billing', 'planning'])
        integration = json.loads(
            (PROJECT / 'workflows' / 'integration.json').read_text(encoding='utf-8'))['steps']
        declared = {name for step in integration for name in step['inputs']}
        for relative in ARTIFACT_MODULES:
            self.assertIn(relative, declared, relative + ' must be a combined acceptance input')
        for path in sorted((PROJECT / 'workflows').glob('*.json')):
            plan = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(plan['criteria'], 'criteria.md', path.name)
        self.assertTrue((PROJECT / 'criteria.md').is_file())


class SetupRefusalTests(unittest.TestCase):
    """Every refusal happens before the first write, and leaves nothing behind."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='crewloom-development-refusal-')).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)

    def assert_refused(self, destination, expected, **options):
        code, output = run_setup(destination, **options)
        self.assertEqual(code, 2, output)
        report = json.loads(output.strip().splitlines()[0])
        self.assertEqual(report['status'], 'blocked', report)
        self.assertIn(expected, report['error'], report)
        return report

    def test_an_existing_destination_is_refused(self):
        existing = self.base / 'taken'
        existing.mkdir()
        self.assert_refused(existing, 'already exists')
        self.assertEqual(list(existing.iterdir()), [], 'a refusal must not write')

    def test_an_aliased_destination_is_refused(self):
        alias = self.base / 'alias'
        alias.symlink_to(self.base, target_is_directory=True)
        self.assert_refused(alias / 'project', 'through a symlink')

    def test_a_destination_inside_the_crewloom_installation_is_refused(self):
        self.assert_refused(Path(resources.distribution_root()) / 'example-project',
                            'inside the Crewloom installation')

    def test_a_destination_inside_another_bound_project_is_refused(self):
        nested = self.base / 'bound'
        (nested / '.crewloom').mkdir(parents=True)
        (nested / 'crewloom.project.json').write_text('{}', encoding='utf-8')
        self.assert_refused(nested / 'project', 'inside the bound project')

    def test_a_destination_inside_another_git_work_tree_is_refused(self):
        outer = self.base / 'outer'
        outer.mkdir()
        git(outer, 'init', '-q')
        git(outer, 'config', 'gc.auto', '0')
        git(outer, 'config', 'maintenance.auto', 'false')
        self.assert_refused(outer / 'project', 'inside the Git work tree')

    def test_a_missing_exact_model_is_refused(self):
        self.assert_refused(self.base / 'no-model', 'exact model identifier', model='   ')

    def test_an_unknown_host_is_refused_before_any_availability_check(self):
        with contextlib.redirect_stderr(io.StringIO()) as noise:
            with self.assertRaises(SystemExit):
                run_setup(self.base / 'unknown-host', host='not-a-host')
        self.assertIn('invalid choice', noise.getvalue())
        self.assertFalse((self.base / 'unknown-host').exists())

    def test_a_native_cli_host_needs_its_explicit_operator_decision(self):
        self.assert_refused(self.base / 'native-missing', 'native host exception',
                            host='opencode', native=False)
        self.assertFalse((self.base / 'native-missing').exists(),
                         'a refusal must not create the destination')

    def test_a_tool_free_rpc_host_refuses_the_native_exception(self):
        self.assert_refused(self.base / 'rpc-native', 'needs no native exception',
                            host='openai', native=True)

    def test_a_missing_credential_is_refused_instead_of_falling_back(self):
        with mock.patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                code = setup.main(['--destination', str(self.base / 'no-credential'),
                                   '--project-id', PROJECT_ID, '--model-host', 'openai',
                                   '--model', MODEL, '--batch-id', BATCH])
        report = json.loads(captured.getvalue().strip().splitlines()[0])
        self.assertEqual(code, 2, report)
        self.assertIn('will not substitute another host or model', report['error'])
        self.assertFalse((self.base / 'no-credential').exists())

    def test_a_non_kebab_case_batch_id_is_refused(self):
        with mock.patch.dict(os.environ, {'OPENAI_API_KEY': RPC_CREDENTIAL}):
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                code = setup.main(['--destination', str(self.base / 'bad-batch'),
                                   '--project-id', PROJECT_ID, '--model-host', 'openai',
                                   '--model', MODEL, '--batch-id', 'Not Kebab Case'])
        report = json.loads(captured.getvalue().strip().splitlines()[0])
        self.assertEqual(code, 2, report)
        self.assertIn('kebab-case', report['error'])
        self.assertFalse((self.base / 'bad-batch').exists())


class ApplicationSemanticsTests(unittest.TestCase):
    """The generated application, run for real with the standard library only."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp(prefix='crewloom-development-semantics-')
        cls.root = Path(cls.directory).resolve() / 'project'
        shutil.copytree(PROJECT, cls.root)
        for relative, name in ARTIFACT_MODULES.items():
            shutil.copyfile(GENERATED / name, cls.root / relative)
        cls.records = {}
        for script in ('check_billing.py', 'check_planning.py', 'check_report.py',
                       'check_combined.py', 'run_helper_tests.py'):
            result = cls.run_script(script)
            cls.records[script] = (result, json.loads(
                (cls.root / 'artifacts' / cls.output_of(script)).read_text(encoding='utf-8')))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)

    @staticmethod
    def output_of(script):
        return {'check_billing.py': 'billing_acceptance.json',
                'check_planning.py': 'planning_acceptance.json',
                'check_report.py': 'report_acceptance.json',
                'check_combined.py': 'combined_acceptance.json',
                'run_helper_tests.py': 'helper_tests.json'}[script]

    @classmethod
    def run_script(cls, script):
        return subprocess.run([sys.executable, 'tools/' + script], cwd=str(cls.root),
                              capture_output=True, text=True, timeout=300)

    def test_every_acceptance_command_passes(self):
        for script, (result, _) in sorted(self.records.items()):
            self.assertEqual(result.returncode, 0, script + ': ' + result.stderr[-400:])
            self.assertNotIn('Traceback', result.stderr, script)

    def test_invoice_totals_round_once_per_currency_group(self):
        record = self.records['check_billing.py'][1]
        cases = {item['name']: item['observed'] for item in record['cases']}
        self.assertEqual(cases['group_tax_rounds_once'], {'tax': '0.01', 'per_line_tax': '0.00'})
        self.assertEqual(cases['frozen_sample_totals']['gross'], '2976.34')
        self.assertEqual(cases['frozen_sample_totals']['rows'][-1], ['-500.00', '-75.00', '-575.00'])
        self.assertEqual(record['failed'], [])
        self.assertGreaterEqual(record['case_count'], 20)

    def test_currency_and_category_validation_is_named_not_guessed(self):
        observed = {item['name']: item['observed'] for item in
                    self.records['check_billing.py'][1]['cases']}
        for name in ('unknown_currency_is_refused', 'lowercase_currency_is_refused',
                     'unknown_category_is_refused', 'float_amount_is_refused',
                     'non_finite_amount_is_refused', 'negative_price_needs_the_refund_category'):
            self.assertIs(observed[name], True, name)

    def test_priority_dependency_and_cycle_rules_are_deterministic(self):
        cases = {item['name']: item['observed'] for item in
                 self.records['check_planning.py'][1]['cases']}
        self.assertEqual(cases['dependency_depth_beats_priority']['order'], ['later', 'first'])
        self.assertEqual(cases['equal_priority_breaks_lexically']['order'],
                         ['alpha', 'beta', 'gamma'])
        self.assertEqual(cases['capacity_chunks_without_mixing']['sizes'], [2, 2, 1])
        self.assertEqual(cases['a_cycle_is_named_and_refused']['cycle'], ['a', 'c', 'b', 'a'])
        self.assertIs(cases['the_plan_is_deterministic']['identical'], True)

    def test_the_combined_report_runs_the_command_and_carries_real_numbers(self):
        record = self.records['check_combined.py'][1]
        cases = {item['name']: item['observed'] for item in record['cases']}
        self.assertEqual(cases['english_report_from_the_integrated_command']['summary']
                         ['gross_by_currency'], {'USD': '2976.34'})
        self.assertEqual(cases['arabic_report_from_the_integrated_command']
                         ['rounding_after_integration'], {'tax': '45.01', 'per_line_tax': '45.00'})
        self.assertEqual(cases['mixed_currency_and_refund_from_the_integrated_command']
                         ['by_currency']['SAR'], {'net': '-100.00', 'tax': '-10.00',
                                                  'gross': '-110.00', 'per_line_tax': '-10.00'})
        self.assertEqual(cases['english_report_from_the_integrated_command']['returncode'], 0)
        self.assertIs(cases['two_runs_are_byte_identical']['identical'], True)
        self.assertEqual(record['failed'], [])
        for name in ('a_cycle_is_refused', 'a_float_amount_is_refused',
                     'a_boolean_quantity_is_refused', 'an_unknown_category_is_refused',
                     'an_unknown_payload_field_is_refused'):
            self.assertEqual(cases[name], {'returncode': 2, 'no_report': True,
                                           'names_cause': True}, name)

    def test_the_frozen_helper_tests_pass_against_the_reused_code(self):
        record = self.records['run_helper_tests.py'][1]
        self.assertTrue(record['accepted'], record)
        self.assertEqual(record['failures'] + record['errors'], 0)
        self.assertGreaterEqual(record['ran'], 12)

    def test_the_command_is_a_real_user_command(self):
        target = self.root / 'artifacts' / 'manual.json'
        result = subprocess.run([sys.executable, 'src/app.py', '--data', 'data/ledger_ar.json',
                                 '--out', str(target), '--language', 'ar'], cwd=str(self.root),
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(document['titles']['invoice'], 'ملخص الفاتورة')
        self.assertEqual(document['summary']['gross_by_currency'], {'SAR': '347.01'})
        self.assertEqual(document['plan']['order'], ['a', 'b', 'c'])
        bad = self.root / 'artifacts' / 'bad.json'
        result = subprocess.run([sys.executable, 'src/app.py', '--data', 'missing.json',
                                 '--out', str(bad)], cwd=str(self.root), capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(bad.exists())
        self.assertEqual(json.loads(result.stderr)['status'], 'blocked')


class PackagingDeclarationTests(unittest.TestCase):
    """The example ships in a wheel and an sdist through the patterns already declared.

    This reuses the packaging suite's own reproduction of setuptools' `package_data` globbing
    rather than a second guess at it, so the claim is the packaging declaration itself and not
    a wheel this test happened not to build.
    """
    @staticmethod
    def declared_patterns():
        import test_packaging
        config = test_packaging.pyproject()
        return test_packaging, [pattern for values
                                in config['tool']['setuptools']['package-data'].values()
                                for pattern in values]

    def test_every_example_file_is_selected_by_the_declared_package_data(self):
        test_packaging, patterns = self.declared_patterns()
        selected = test_packaging.matched_files(patterns)
        files = sorted(test_packaging.declared_files('examples/concurrent-development'))
        self.assertGreaterEqual(len(files), 25, files)
        missing = [name for name in files if name not in selected]
        self.assertEqual(missing, [], 'these example files would not reach an installed wheel')

    def test_the_guide_and_the_arabic_companion_are_packaged(self):
        test_packaging, patterns = self.declared_patterns()
        selected = test_packaging.matched_files(patterns)
        for name in ('documentation/DEVELOPMENT_EXAMPLE.md',
                     'examples/concurrent-development/README.md',
                     'examples/concurrent-development/README.ar.md'):
            self.assertIn(name, selected, name)

    def test_the_sdist_keeps_the_whole_example_tree(self):
        import test_packaging
        rules = [line.strip() for line
                 in (test_packaging.ROOT / 'MANIFEST.in').read_text(encoding='utf-8').splitlines()]
        self.assertIn('recursive-include examples *', rules)
        self.assertIn('global-exclude __pycache__ *.pyc *.pyo .DS_Store *.log', rules)
        self.assertFalse(any(path.suffix == '.pyc' for path in EXAMPLE.rglob('*')))


class PreparedProject(unittest.TestCase):
    """A real project built by the shipped setup command, copied per test."""

    template = None

    @classmethod
    def setUpClass(cls):
        directory = tempfile.mkdtemp(prefix='crewloom-development-template-')
        cls.addClassCleanup(shutil.rmtree, directory, True)
        cls.template = Path(directory).resolve() / 'project'
        code, output = run_setup(cls.template)
        if code:
            raise AssertionError('setup refused its own project: ' + output[-500:])
        cls.setup_report = json.loads(output)

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='crewloom-development-')
        self.addCleanup(shutil.rmtree, self.directory, True)
        self.root = Path(self.directory).resolve() / 'project'
        shutil.copytree(self.template, self.root, symlinks=True)
        pb.rebind(self.root, PROJECT_ID, 'test copy of the example project')

    def worktree(self, task):
        return self.root / '.crewloom' / 'worktrees' / BATCH / task

    def head(self):
        return git(self.root, 'rev-parse', 'HEAD').stdout.strip()


class SetupProjectTests(PreparedProject):
    """What the setup command leaves behind, checked against the project it actually built."""

    def test_it_is_bound_and_preflighted_by_the_real_coordinator(self):
        binding = pb.load_binding(self.root)
        self.assertEqual(binding['project_id'], PROJECT_ID)
        self.assertEqual(self.setup_report['preflight']['status'], 'validated')
        self.assertEqual(self.setup_report['preflight']['order'], ['billing', 'planning', 'report'])
        self.assertEqual(sorted(self.setup_report['preflight']['model_steps']),
                         ['billing', 'planning', 'report'])
        self.assertEqual(tc.validate(self.root, 'coordinator.json', PROJECT_ID)['status'],
                         'validated')

    def test_it_installs_only_the_two_roles_the_workflows_name(self):
        installed = sorted(path.parent.name for path in
                           (self.root / '.agents' / 'skills').glob('*/SKILL.md'))
        self.assertEqual(installed, sorted(setup.ROLES))

    def test_the_exact_model_is_recorded_with_no_substitute(self):
        manifest = json.loads((self.root / 'coordinator.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['project_id'], PROJECT_ID)
        self.assertEqual(manifest['id'], BATCH)
        for task in manifest['tasks']:
            self.assertIs(task['native_host_cli'], False)
        for name in ('billing', 'planning', 'report'):
            step = json.loads((self.root / 'workflows' / (name + '.json')).read_text(
                encoding='utf-8'))['steps'][0]
            self.assertEqual(step['host'], HOST)
            self.assertEqual(step['model'], MODEL)
        for path in sorted(self.root.rglob('*.json')):
            if '.crewloom' in path.parts:
                continue
            text = path.read_text(encoding='utf-8')
            for token in setup.TOKENS:
                self.assertNotIn(token, text, str(path) + ' kept an unsubstituted placeholder')

    def test_no_credential_or_runtime_state_is_tracked(self):
        tracked = git(self.root, 'ls-files', '-z').stdout.split('\0')
        self.assertNotIn('.crewloom/binding.json', tracked)
        self.assertNotIn('.crewloom/reviewers.json', tracked)
        for name in tracked:
            self.assertFalse(name.startswith('.crewloom'), name)
        ignore = (self.root / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('.crewloom', ignore)
        token = self.root / '.crewloom' / 'reviewer-token-example-reviewer'
        self.assertTrue(token.is_file())
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertEqual(git(self.root, 'config', '--get', 'core.hooksPath', check=False)
                         .stdout.strip(), '', 'setup must not disable the hook path')

    def test_the_base_commit_carries_the_portable_project_and_its_criteria(self):
        tracked = set(git(self.root, 'ls-files', '-z').stdout.split('\0'))
        for required in ('crewloom.project.json', 'criteria.md', 'coordinator.json',
                         'workflows/integration.json', 'contracts/invoicing.md',
                         'contracts/planning.md', 'contracts/report.md', 'tools/check_billing.py',
                         'tools/check_planning.py', 'tools/check_report.py',
                         'tools/check_combined.py', 'tools/run_helper_tests.py',
                         'tests/test_money.py', 'tests/test_scheduling_support.py',
                         'data/ledger_en.json', 'data/ledger_ar.json', 'src/money.py',
                         'src/scheduling_support.py'):
            self.assertIn(required, tracked)
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD').stdout.strip(),
                         self.setup_report['base']['commit'])

    def test_no_reservation_was_left_by_setup(self):
        self.assertFalse((self.root / '.crewloom' / 'active_task.json').exists(),
                         'setup must not reserve the root for a task nobody runs')
        self.assertFalse((self.root / '.crewloom' / 'active_coordinator.json').exists())


def install_pre_commit_hook(root):
    """A real hook in the real repository: every task commit has to pass through it.

    The marker goes into the shared Git directory, because a linked worktree's toplevel is
    the worktree itself and one record per commit is what has to be comparable afterwards.
    """
    hook = root / '.git' / 'hooks' / 'pre-commit'
    hook.write_text('#!/bin/sh\n'
                    'common=$(git rev-parse --git-common-dir)\n'
                    'case "$common" in /*) ;; *) common="$(git rev-parse --show-toplevel)/$common";; esac\n'
                    'printf "%s %s\\n" "$(git rev-parse --abbrev-ref HEAD)" "$(git write-tree)"'
                    ' >> "$common/hook-runs.txt"\n', encoding='utf-8')
    hook.chmod(0o755)
    return hook


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS') == '1',
                     'Enable the real Docker acceptance of the example explicitly')
class DockerDevelopmentExampleTests(PreparedProject):
    """One real batch: concurrent generation, real container acceptance, reviewed publication."""

    @staticmethod
    def cli_argv():
        """The installed command when a distribution check names it, else this checkout's CLI."""
        installed = os.environ.get('CREWLOOM_INSTALLED_CLI')
        return [installed] if installed else [sys.executable, str(SOURCE / 'crewloom.py')]

    def setUp(self):
        super().setUp()
        self.base = self.head()
        self.image = w.inspect_image(w.DEFAULT_IMAGE)
        self.requests = []
        install_pre_commit_hook(self.root)

    def batch(self, action, **options):
        return tc.__dict__[action](self.root, 'coordinator.json', PROJECT_ID, **options)

    def hook_runs(self):
        marker = self.root / '.git' / 'hook-runs.txt'
        return [line.split() for line in marker.read_text(encoding='utf-8').splitlines()
                if line.strip()] if marker.is_file() else []

    def test_the_batch_verifies_integrates_publishes_and_the_command_works(self):
        with mock.patch.object(model_host, 'generate', stand_in_provider(self.requests)):
            report = self.batch('run')
        self.assertEqual(report['status'], 'verified', report)
        self.assertTrue(report['workers_overlapped'], 'the two independent tasks did not overlap')
        self.assertEqual(sorted(item['host'] for item in self.requests), [HOST] * 3)
        self.assertEqual(sorted(item['model'] for item in self.requests), [MODEL] * 3)
        by_id = {item['id']: item for item in report['tasks']}
        checkouts = [item['checkout_id'] for item in report['tasks']]
        self.assertEqual(len(set(checkouts)), 3, 'every worktree needs its own checkout identity')
        declared = {'billing': ('src/billing.py', 'artifacts/billing_acceptance.json'),
                    'planning': ('src/planning.py', 'artifacts/planning_acceptance.json'),
                    'report': ('src/report.py', 'src/app.py',
                               'artifacts/report_acceptance.json')}
        for ident, outputs in sorted(declared.items()):
            item = by_id[ident]
            self.assertEqual(item['status'], 'verified', item)
            self.assertEqual(item['model_steps'], ['generate'])
            self.assertFalse(item['native_host_cli'])
            generated = [entry for entry in item['ledger'] if entry.get('kind') == 'model']
            self.assertEqual(len(generated), 1)
            self.assertEqual(generated[0]['host'], HOST)
            self.assertTrue(generated[0]['context_sha256'],
                            'the generation evidence needs the prompt it really sent')
            consumers = {entry['step'] for entry in generated[0]['consumed_by']}
            self.assertEqual(consumers, {'accept'})
            for entry in generated[0]['consumed_by']:
                self.assertEqual(entry['sha256'], generated[0]['outputs'][entry['output']])
            command = [entry for entry in item['ledger'] if entry.get('kind') is None]
            self.assertEqual([entry['step'] for entry in command], ['accept'])
            self.assertEqual(command[0]['image_id'], self.image,
                             'the acceptance must record the image it really ran in')
            self.assertEqual(sorted(item['outputs']), sorted(outputs))
        dependent = next(item for item in report['tasks'] if item['id'] == 'report')
        self.assertEqual(sorted(dependent['dependencies']), ['billing', 'planning'])
        # Dependency visibility: the dependent generation really read its merged ancestors.
        request = next(item for item in self.requests if 'src/report.py' in item['outputs'])
        self.assertIn('src/billing.py', request['inputs'])
        self.assertIn('src/planning.py', request['inputs'])
        self.assertIn('CURRENCIES = ', request['inputs']['src/billing.py'])
        self.assertIn('def schedule(', request['inputs']['src/planning.py'])
        # An independent task cannot see the other task's generated module.
        self.assertFalse((self.worktree('billing') / 'src' / 'planning.py').exists())
        self.assertFalse((self.worktree('planning') / 'src' / 'billing.py').exists())
        self.assertTrue((self.worktree('report') / 'src' / 'billing.py').is_file())
        # The configured hook ran for every real commit, on exactly the tree that became it.
        hooks = dict(self.hook_runs())
        self.assertEqual(sorted(hooks),
                         ['crewloom/' + BATCH + '/billing', 'crewloom/' + BATCH + '/planning',
                          'crewloom/' + BATCH + '/report'])
        for item in report['tasks']:
            tree = git(self.root, 'rev-parse', item['commit'] + '^{tree}').stdout.strip()
            self.assertEqual(hooks['crewloom/' + BATCH + '/' + item['id']], tree,
                             'the hook did not see the tree that became ' + item['id'])
        self.assertEqual(self.head(), self.base, 'the root must not move before a reviewed decision')
        for relative in ARTIFACT_MODULES:
            self.assertFalse((self.root / relative).exists(),
                             'no generated module may appear in the root before publication')

        prepared = self.batch('prepare')
        self.assertEqual(prepared['status'], 'review_ready', prepared)
        integration = prepared['integration']
        self.assertEqual(integration['reviewed_artifacts'], 9)
        acceptance = json.loads((self.worktree('integration') / 'artifacts' /
                                 'combined_acceptance.json').read_text(encoding='utf-8'))
        self.assertTrue(acceptance['accepted'], acceptance['failed'])
        self.assertGreaterEqual(acceptance['case_count'], 12)
        helpers = json.loads((self.worktree('integration') / 'artifacts' /
                              'helper_tests.json').read_text(encoding='utf-8'))
        self.assertTrue(helpers['accepted'], helpers)
        cases = {item['name']: item['observed'] for item in acceptance['cases']}
        self.assertEqual(cases['arabic_report_from_the_integrated_command']
                         ['rounding_after_integration'], {'tax': '45.01', 'per_line_tax': '45.00'})
        self.assertEqual(cases['english_report_from_the_integrated_command']['summary']
                         ['waves'], 3)
        self.assertIn('crewloom/' + BATCH + '/integration', dict(self.hook_runs()),
                      'the integration commit passed through the same hook')

        with self.assertRaisesRegex(ValueError, 'explicit reviewed decision'):
            self.batch('publish', expected_base=integration['base'],
                       candidate_head=integration['head'], diff_sha256=integration['diff_sha256'])
        self.assertEqual(self.head(), self.base)
        with self.assertRaisesRegex(ValueError, 'reviewer credential is required'):
            self.batch('review', expected_base=integration['base'],
                       candidate_head=integration['head'], diff_sha256=integration['diff_sha256'])
        token = (self.root / '.crewloom' / 'reviewer-token-example-reviewer').read_text(
            encoding='utf-8').strip()
        self.assertTrue(token, 'the registered reviewer must have an issued credential')
        # The credential is delivered on standard input, never as a command argument.
        argv = ['coordinator', 'review', '--project', str(self.root), '--project-id', PROJECT_ID,
                '--manifest', 'coordinator.json', '--expected-base', integration['base'],
                '--candidate-head', integration['head'], '--diff-sha256',
                integration['diff_sha256'], '--reviewer-token-stdin']
        command = subprocess.run([*self.cli_argv(), *argv],
                                 cwd=str(self.root), input=token + '\n', capture_output=True,
                                 text=True, timeout=180, env=repo_map.git_environment())
        self.assertEqual(command.returncode, 0, command.stdout[-400:] + command.stderr[-400:])
        decided = json.loads(command.stdout)
        self.assertEqual(decided['status'], 'reviewed', decided)
        self.assertEqual(decided['method'], 'hashed-token')
        self.assertEqual(decided['review_policy']['mode'], 'verified')
        self.assertNotIn(token, command.stdout + command.stderr)
        self.assertNotEqual(decided['principal'], 'qa-test-automation-engineer')
        published = self.batch('publish', expected_base=integration['base'],
                               candidate_head=integration['head'],
                               diff_sha256=integration['diff_sha256'])
        self.assertEqual(published['status'], 'published', published)
        # A second publication of the same decision is refused; after the fast-forward the refusal
# is the frozen base, and the root does not move a second time.
        with self.assertRaises(ValueError):
            self.batch('publish', expected_base=integration['base'],
                       candidate_head=integration['head'], diff_sha256=integration['diff_sha256'])
        self.assertEqual(self.head(), integration['head'])
        self.assertEqual(self.head(), integration['head'])
        for relative in ARTIFACT_MODULES:
            self.assertTrue((self.root / relative).is_file(), relative + ' must be published')
        # The published tree runs the generated command for real, with no coordinator involved.
        target = self.root / 'artifacts' / 'published-report.json'
        result = subprocess.run([sys.executable, 'src/app.py', '--data', 'data/ledger_ar.json',
                                 '--out', str(target), '--language', 'ar'], cwd=str(self.root),
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads(target.read_text(encoding='utf-8'))
        self.assertEqual(document['summary']['gross_by_currency'], {'SAR': '347.01'})
        self.assertEqual(document['invoice']['by_currency']['SAR']['tax'], '45.01')
        self.assertEqual(document['plan']['waves'], [['a'], ['b'], ['c']])

    def test_a_failed_task_quality_blocks_its_dependent_and_publication(self):
        original = (self.root / 'tools' / 'check_billing.py').read_text(encoding='utf-8')
        weakened = original.replace("'gross': '2976.34'", "'gross': '2976.35'")
        self.assertNotEqual(weakened, original, 'the acceptance must actually be weakened')
        self.assertEqual(original.count("'gross': '2976.34'"), 1)
        (self.root / 'tools' / 'check_billing.py').write_text(weakened, encoding='utf-8')
        git(self.root, 'add', 'tools/check_billing.py')
        git(self.root, 'commit', '-qm', 'Demand a total the generated arithmetic cannot produce')
        base = self.head()
        with mock.patch.object(model_host, 'generate', stand_in_provider(self.requests)):
            report = self.batch('run')
        self.assertEqual(report['status'], 'failed', report)
        tasks = {item['id']: item for item in report['tasks']}
        self.assertIn(tasks['billing']['status'], ('failed', 'blocked'))
        self.assertIn('finished as failed', tasks['billing']['error'])
        # The refused cause is the acceptance that actually failed, named by its own step and
        # owning role, not a summary that loses it.
        self.assertIn('step accept (role qa-test-automation-engineer) failed: Command failed: accept',
                      tasks['billing']['error'])
        self.assertNotIn('no error recorded', tasks['billing']['error'])
        run_state = json.loads((self.worktree('billing') / '.crewloom' / 'workflows' /
                               'billing-workflow' / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual(run_state['status'], 'failed')
        self.assertEqual(run_state['error'], 'Command failed: accept',
                         'the managed run must carry the failing stage\'s own cause')
        self.assertEqual(run_state['steps']['accept']['role'], 'qa-test-automation-engineer')
        self.assertEqual(run_state['steps']['accept']['status'], 'failed')
        self.assertIsNone(tasks['billing']['commit'],
                          'a failed acceptance may not become a task commit')
        self.assertEqual(tasks['billing']['outputs'], {})
        self.assertEqual(tasks['report']['status'], 'blocked')
        self.assertIn('Blocked by billing', tasks['report']['error'])
        self.assertEqual(tasks['planning']['status'], 'verified')
        self.assertEqual(git(self.worktree('billing'), 'rev-parse', 'HEAD').stdout.strip(), base,
                         'a failed task must leave its branch at the base')
        pending = git(self.worktree('billing'), 'status', '--porcelain', '--', 'src/billing.py')
        self.assertIn('src/billing.py', pending.stdout,
                      'the unaccepted generated module stays in the worktree, uncommitted')
        with self.assertRaisesRegex(ValueError, 'Refusing partial acceptance'):
            self.batch('prepare')
        with self.assertRaisesRegex(ValueError, 'prepare the combined candidate'):
            self.batch('review', expected_base=base, candidate_head='0' * 40,
                       diff_sha256='0' * 64)
        self.assertEqual(self.head(), base, 'a failed quality gate must leave the root alone')
        for relative in ARTIFACT_MODULES:
            self.assertFalse((self.root / relative).exists())
        self.assertEqual(self.batch('status')['status'], 'failed')

    def test_a_native_cli_host_needs_both_the_manifest_decision_and_the_run_flag(self):
        shutil.rmtree(self.root)
        self.root = Path(self.directory).resolve() / 'native-project'
        code, output = run_setup(self.root, host='opencode', native=True)
        self.assertEqual(code, 0, output[-400:])
        pb.rebind(self.root, PROJECT_ID, 'test copy of the native CLI example project')
        install_pre_commit_hook(self.root)
        manifest = json.loads((self.root / 'coordinator.json').read_text(encoding='utf-8'))
        self.assertTrue(all(task['native_host_cli'] for task in manifest['tasks']))
        step = json.loads((self.root / 'workflows' / 'billing.json').read_text(
            encoding='utf-8'))['steps'][0]
        self.assertEqual(step['host'], 'opencode')
        self.assertEqual(step['model'], MODEL)
        base = self.head()
        # First decision only: the committed manifest opt-in, without this run's flag.
        with mock.patch.object(model_host, 'generate', stand_in_provider(self.requests)):
            refused = self.batch('run')
        self.assertEqual(self.requests, [], 'no provider may be reached without both decisions')
        billing = next(item for item in refused['tasks'] if item['id'] == 'billing')
        self.assertEqual(billing['status'], 'blocked')
        self.assertIn('explicit operator opt-in', billing['error'])
        self.assertEqual(billing['ledger'], [])
        self.assertEqual(self.head(), base, 'a refused opt-in must not move the root')
        self.assertFalse((self.root / 'src' / 'billing.py').exists())
        self.assertEqual(refused['status'], 'failed')
        # The refusal is this run's grant, not a retraction of the committed manifest decision.
        state = json.loads((self.root / '.crewloom' / 'coordinators' / BATCH /
                            'state.json').read_text(encoding='utf-8'))
        for ident in ('billing', 'planning', 'report'):
            self.assertIs(state['tasks'][ident]['native_host_cli'], True,
                          ident + ' lost the decision its own committed manifest made')
        for ident in ('billing', 'planning'):
            grant = state['tasks'][ident]['native_cli_run']
            self.assertEqual({key: grant[key] for key in ('declared', 'operator_flag', 'granted',
                                                          'hosts')},
                             {'declared': True, 'operator_flag': False, 'granted': False,
                              'hosts': ['opencode']},
                             ident + ' must record the refused per-run grant, not the intent')
        # The second decision arrives on the SAME root and the SAME batch: no new batch id, no
        # rebuilt source project, and the still-true committed intent is what the retry reads.
        with mock.patch.object(model_host, 'generate', stand_in_provider(self.requests)):
            report = self.batch('run', allow_host_cli=True)
        self.assertEqual(report['status'], 'verified', report)
        self.assertTrue(report['resumed'], 'the retry reused the batch the refusal left behind')
        self.assertEqual(sorted(item['host'] for item in self.requests), ['opencode'] * 3)
        self.assertEqual(sorted(item['model'] for item in self.requests), [MODEL] * 3)
        self.assertEqual(len(self.requests), 3, 'the refused attempt reached no provider')
        billing = next(item for item in report['tasks'] if item['id'] == 'billing')
        self.assertTrue(billing['native_host_cli'])
        self.assertEqual(billing['native_cli_run']['granted'], True)
        self.assertEqual(billing['native_cli_run']['operator_flag'], True)
        self.assertEqual([entry['host'] for entry in billing['ledger'] if entry.get('kind') == 'model'],
                         ['opencode'])
        command = [entry for entry in billing['ledger'] if entry.get('kind') is None]
        self.assertEqual([entry['step'] for entry in command], ['accept'])
        self.assertEqual(command[0]['image_id'], self.image,
                         'the retried acceptance ran in the real container, not a stand-in')
        self.assertEqual((self.worktree('billing') / 'src' / 'billing.py').read_text(
            encoding='utf-8'), (GENERATED / 'billing.py').read_text(encoding='utf-8'))
        # Every retried task ended as a real commit on the same repository, through the same hook.
        hooks = dict(self.hook_runs())
        self.assertEqual(sorted(hooks), ['crewloom/' + BATCH + '/' + ident
                                         for ident in ('billing', 'planning', 'report')])
        for ident in ('billing', 'planning', 'report'):
            record = next(item for item in report['tasks'] if item['id'] == ident)
            self.assertEqual(record['status'], 'verified')
            self.assertTrue(record['commit'], ident + ' needs a real task commit')
            self.assertEqual(hooks['crewloom/' + BATCH + '/' + ident],
                             git(self.root, 'rev-parse', record['commit'] + '^{tree}').stdout.strip(),
                             ident + ' commit did not pass through the repository hook')
        self.assertEqual(self.head(), base, 'the retried batch still did not move the root')
        self.assertFalse((self.root / 'src' / 'billing.py').exists(),
                         'nothing is published before a reviewed decision')


if __name__ == '__main__':
    unittest.main()