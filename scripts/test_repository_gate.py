"""Acceptance for bounded per-module batching of the repository gate.

The gate must keep every discovered module and assertion inside the unchanged
60 second per-invocation bound, refuse to drop coverage, report a bounded
timeout as a plain failure, and never make a discovered suite optional.
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_repository import (ROOT, SUITES, SUITE_TIMEOUT, main,
                              missing_suite_directories, run_suites,
                              suite_directories, suite_plan)

PASSING_MODULE = ('import unittest\n\n\n'
                  'class BoundedGateTests(unittest.TestCase):\n'
                  '    def test_this_module_passes(self):\n'
                  '        self.assertTrue(True)\n\n\n'
                  'if __name__ == "__main__":\n'
                  '    unittest.main()\n')
FAILING_MODULE = ('import unittest\n\n\n'
                  'class BoundedGateTests(unittest.TestCase):\n'
                  '    def test_this_module_fails(self):\n'
                  '        self.assertEqual(1, 2)\n\n\n'
                  'if __name__ == "__main__":\n'
                  '    unittest.main()\n')
NESTED_HELPER = 'VALUE = 41\n'
NESTED_MODULE = ('import unittest\n'
                 'from . import nested_helper\n\n\n'
                 'class NestedPackageGateTests(unittest.TestCase):\n'
                 '    def test_the_nested_package_import_resolves(self):\n'
                 '        self.assertEqual(nested_helper.VALUE, 41)\n\n\n'
                 'if __name__ == "__main__":\n'
                 '    unittest.main()\n')
NESTED_FAILING_MODULE = ('import unittest\n'
                         'from . import nested_helper\n\n\n'
                         'class NestedPackageGateTests(unittest.TestCase):\n'
                         '    def test_the_nested_package_fails(self):\n'
                         '        self.assertEqual(nested_helper.VALUE, 41)\n'
                         '        self.assertEqual(1, 2)\n\n\n'
                         'if __name__ == "__main__":\n'
                         '    unittest.main()\n')


def build_root(directory, modules):
    """A checkout-shaped tree whose every planned suite directory exists."""
    root = Path(directory)
    for name in SUITES:
        (root / '.agents' / 'skills' / name / 'scripts').mkdir(parents=True)
    (root / 'scripts').mkdir(parents=True)
    for relative, body in modules.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding='utf-8')
    return root


def build_nested(root, body=NESTED_MODULE):
    """A nested Python package whose module only imports through its package."""
    nested = root / 'scripts' / 'nested'
    nested.mkdir(parents=True, exist_ok=True)
    (nested / '__init__.py').write_text('', encoding='utf-8')
    (nested / 'nested_helper.py').write_text(NESTED_HELPER, encoding='utf-8')
    (nested / 'test_nested.py').write_text(body, encoding='utf-8')
    return nested / 'test_nested.py'


def discovered(root):
    """Every module recursive unittest discovery selects, as a set of paths.

    Written from the discovery rule itself rather than from the gate: a module is
    selected when every directory between its suite directory and itself is a
    Python package, so caches and plain folders never join the plan.
    """
    found = []
    for directory in suite_directories(root):
        for module in sorted(directory.rglob('test_*.py')):
            between = module.relative_to(directory).parts[:-1]
            packaged = all((directory.joinpath(*between[:depth]) / '__init__.py').is_file()
                           for depth in range(1, len(between) + 1))
            if packaged and module.is_file():
                found.append(module)
    return found


@contextlib.contextmanager
def captured():
    """Capture the gate's own reporting while muting inherited child output."""
    sys.stdout.flush()
    sys.stderr.flush()
    saved = (os.dup(1), os.dup(2))
    sink = os.open(os.devnull, os.O_WRONLY)
    messages = io.StringIO()
    try:
        os.dup2(sink, 1)
        os.dup2(sink, 2)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(messages):
            yield messages
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        os.close(sink)


class GatePlanTests(unittest.TestCase):
    """The batched plan selects each discovered module exactly once."""

    def test_every_discovered_module_becomes_its_own_bounded_invocation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_alpha.py': PASSING_MODULE,
                                          'scripts/test_beta.py': PASSING_MODULE,
                                          'scripts/helper.py': 'VALUE = 1\n',
                                          'scripts/__pycache__/test_cached.py': PASSING_MODULE,
                                          f'.agents/skills/{SUITES[0]}/scripts/test_skill.py': PASSING_MODULE})
            plan = suite_plan(root)
            self.assertEqual([module for module, _ in plan], discovered(root))
            self.assertEqual(len(plan), 3, 'each discovered module runs once and nothing else runs')
            for module, argv in plan:
                self.assertEqual(argv, [sys.executable, '-m', 'unittest', 'discover',
                                        '-s', str(module.parent), '-p', module.name])

    def test_a_module_added_after_import_is_selected_without_a_gate_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_first.py': PASSING_MODULE})
            before = suite_plan(root)
            (root / 'scripts' / 'test_added_later.py').write_text(PASSING_MODULE, encoding='utf-8')
            after = suite_plan(root)
            self.assertEqual(len(after), len(before) + 1)
            self.assertIn(root / 'scripts' / 'test_added_later.py', [module for module, _ in after])

    def test_a_nested_package_module_is_planned_with_its_suite_as_discovery_top(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_alpha.py': PASSING_MODULE})
            module = build_nested(root)
            plan = suite_plan(root)
            selected = [item for item, _ in plan]
            self.assertEqual(sorted(selected), sorted(discovered(root)),
                             'a nested package module is selected exactly as recursive discovery selects it')
            self.assertEqual(len(selected), len(set(selected)), 'no module may run twice')
            argv = dict((item, argv) for item, argv in plan)[module]
            self.assertEqual(argv, [sys.executable, '-m', 'unittest', 'discover',
                                    '-s', str(module.parent), '-p', module.name,
                                    '-t', str(root / 'scripts')],
                             'the suite directory anchors the nested package import')
            self.assertEqual(dict((item, argv) for item, argv in plan)[root / 'scripts' / 'test_alpha.py'],
                             [sys.executable, '-m', 'unittest', 'discover',
                              '-s', str(root / 'scripts'), '-p', 'test_alpha.py'],
                             'a module already in the suite directory keeps its plain invocation')

    def test_a_deeper_nested_package_module_keeps_the_same_suite_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_alpha.py': PASSING_MODULE})
            module = build_nested(root)
            deep = module.parent / 'deeper'
            deep.mkdir()
            (deep / '__init__.py').write_text('', encoding='utf-8')
            (deep / 'test_deep.py').write_text(PASSING_MODULE, encoding='utf-8')
            (root / 'scripts' / 'plain').mkdir()
            (root / 'scripts' / 'plain' / 'test_not_a_package.py').write_text(PASSING_MODULE, encoding='utf-8')
            plan = suite_plan(root)
            selected = [item for item, _ in plan]
            self.assertEqual(sorted(selected), sorted(discovered(root)))
            self.assertEqual(selected[0], root / 'scripts' / 'test_alpha.py',
                             'the established suite order stays first and nested packages follow')
            for nested in (module, deep / 'test_deep.py'):
                argv = dict((item, argv) for item, argv in plan)[nested]
                self.assertEqual(argv[-2:], ['-t', str(root / 'scripts')])
                self.assertEqual(argv[argv.index('-s') + 1], str(nested.parent))
            self.assertNotIn(root / 'scripts' / 'plain' / 'test_not_a_package.py', selected,
                             'unittest discovery does not enter a folder that is not a package')

    def test_the_real_checkout_still_selects_every_module_the_flat_glob_selected(self):
        plan = suite_plan(ROOT)
        selected = [module for module, _ in plan]
        for directory in suite_directories(ROOT):
            flat = {module for module in directory.glob('test_*.py') if module.is_file()}
            self.assertTrue(flat <= set(selected), f'nothing in {directory} may be dropped')
        self.assertEqual(len(selected), len(set(selected)))
        self.assertEqual(len(selected), len(discovered(ROOT)))

    def test_the_real_checkout_plans_every_discovered_module_exactly_once(self):
        plan = suite_plan(ROOT)
        selected = [module for module, _ in plan]
        self.assertEqual(sorted(selected), sorted(discovered(ROOT)))
        self.assertEqual(len(selected), len(set(selected)), 'no module may run twice')
        for name in SUITES:
            directory = ROOT / '.agents' / 'skills' / name / 'scripts'
            self.assertTrue(any(module.parent == directory for module in selected),
                            f'{name} regressions must remain covered')

    def test_no_planned_invocation_relaxes_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            nested_root = build_root(directory, {})
            nested_module = build_nested(nested_root)
            plans = [(ROOT, suite_plan(ROOT)), (nested_root, suite_plan(nested_root))]
        self.assertTrue(plans[0][1], 'the real checkout must still plan its modules')
        self.assertIn(nested_module, [module for module, _ in plans[1][1]])
        for root, plan in plans:
            for module, argv in plan:
                suite = next(directory for directory in suite_directories(root)
                             if module.is_relative_to(directory))
                nested = module.parent != suite
                options = [token for token in argv if token.startswith('-')]
                self.assertEqual(options, ['-m', '-s', '-p', '-t'] if nested else ['-m', '-s', '-p'],
                                 f'unexpected options for {module}')
                for token in options:
                    self.assertNotIn('skip', token)
                    self.assertNotIn('failfast', token)
                self.assertEqual(argv[0], sys.executable, 'the gate runs its own interpreter')
                self.assertEqual(argv[argv.index('-s') + 1], str(module.parent))
                self.assertEqual(argv[argv.index('-p') + 1], module.name)

    def test_a_missing_suite_directory_is_reported_instead_of_dropping_its_tests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_alpha.py': PASSING_MODULE})
            self.assertEqual(missing_suite_directories(root), [])
            shutil.rmtree(root / '.agents' / 'skills' / SUITES[0] / 'scripts')
            self.assertEqual(missing_suite_directories(root),
                             [root / '.agents' / 'skills' / SUITES[0] / 'scripts'])
            with captured() as messages:
                self.assertNotEqual(run_suites(root), 0)
            self.assertIn('SUITE DIRECTORY MISSING', messages.getvalue())
        self.assertEqual(missing_suite_directories(ROOT), [])


class GateRunTests(unittest.TestCase):
    """Every bounded invocation runs, fails, and times out as a reported gate result."""

    def test_every_module_runs_sequentially_inside_the_sixty_second_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_beta.py': PASSING_MODULE,
                                          'scripts/test_alpha.py': PASSING_MODULE,
                                          f'.agents/skills/{SUITES[2]}/scripts/test_ui.py': PASSING_MODULE})
            seen = []

            def recorder(argv, timeout=None, check=None):
                seen.append((argv[-1], timeout))
                return subprocess.CompletedProcess(argv, 0)

            self.assertEqual(run_suites(root, runner=recorder), 0)
            self.assertEqual([name for name, _ in seen],
                             ['test_ui.py', 'test_alpha.py', 'test_beta.py'],
                             'skill regressions run before the shared scripts modules')
            self.assertEqual({timeout for _, timeout in seen}, {60},
                             'the per-invocation bound is unchanged at 60 seconds')
            self.assertEqual(SUITE_TIMEOUT, 60, 'the gate bound must not be raised')

    def test_a_failing_child_fails_the_gate_and_propagates_its_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_bad.py': FAILING_MODULE,
                                          'scripts/test_good.py': PASSING_MODULE})
            with captured() as messages:
                code = run_suites(root)
            self.assertEqual(code, 1)
            message = messages.getvalue()
            self.assertIn('test_bad.py', message)
            self.assertIn('SUITE FAILED', message)
            self.assertNotIn('Traceback', message)

    def test_a_failing_child_stops_the_run_instead_of_being_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_bad.py': FAILING_MODULE,
                                          'scripts/test_later.py': PASSING_MODULE})
            seen = []

            def recorder(argv, timeout=None, check=None):
                seen.append(argv[-1])
                return subprocess.CompletedProcess(argv, 7 if argv[-1] == 'test_bad.py' else 0)

            with captured():
                code = run_suites(root, runner=recorder)
            self.assertEqual(code, 7, 'the child exit code is the gate exit code')
            self.assertEqual(seen, ['test_bad.py'], 'no later module runs after a failure')

    def test_a_timeout_is_a_reported_failure_and_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_slow.py': PASSING_MODULE})

            def stalling(argv, timeout=None, check=None):
                raise subprocess.TimeoutExpired(argv, timeout)

            with captured() as messages:
                self.assertNotEqual(run_suites(root, runner=stalling), 0)
            message = messages.getvalue()
            self.assertIn('SUITE TIMED OUT after 60s', message)
            self.assertIn('test_slow.py', message)
            self.assertNotIn('Traceback', message)

    def test_a_passing_tree_runs_every_module_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_alpha.py': PASSING_MODULE,
                                          f'.agents/skills/{SUITES[1]}/scripts/test_pack.py': PASSING_MODULE})
            with captured():
                self.assertEqual(run_suites(root), 0)

    def test_a_nested_package_module_runs_and_resolves_its_own_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_alpha.py': PASSING_MODULE})
            module = build_nested(root)
            with captured() as messages:
                self.assertEqual(run_suites(root), 0, messages.getvalue())
            result = subprocess.run(dict(suite_plan(root))[module], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Ran 1 test', result.stderr, 'the nested module must really execute')

    def test_a_failing_nested_package_module_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_alpha.py': PASSING_MODULE})
            build_nested(root, NESTED_FAILING_MODULE)
            with captured() as messages:
                code = run_suites(root)
            self.assertNotEqual(code, 0)
            message = messages.getvalue()
            self.assertIn('test_nested.py', message)
            self.assertIn('SUITE FAILED', message)
            self.assertNotIn('Traceback', message)

    def test_a_nested_package_module_keeps_the_same_sixty_second_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {})
            module = build_nested(root)
            seen = []

            def recorder(argv, timeout=None, check=None):
                seen.append((argv[argv.index('-p') + 1], timeout))
                return subprocess.CompletedProcess(argv, 0)

            self.assertEqual(run_suites(root, runner=recorder), 0)
            self.assertEqual([name for name, _ in seen], ['test_nested.py'])
            self.assertEqual({timeout for _, timeout in seen}, {60},
                             'a nested module is bounded exactly like every other module')


class GateCommandTests(unittest.TestCase):
    """The public command keeps its structure gate, suites, and skip semantics."""

    def test_structure_errors_stop_the_gate_before_any_suite_runs(self):
        calls = []
        with captured() as messages, patch('check_repository.inspect', return_value=['broken link']), \
                patch('check_repository.run_suites', side_effect=lambda root: calls.append(root)):
            self.assertEqual(main(argv=[], root=ROOT), 1)
        self.assertEqual(calls, [], 'no suite may run after a structure error')
        self.assertIn('broken link', messages.getvalue())

    def test_the_final_gate_runs_the_suites_and_skip_tests_still_skips_them(self):
        calls = []

        def failing(root):
            calls.append(root)
            return 3

        with captured(), patch('check_repository.inspect', return_value=[]), \
                patch('check_repository.run_suites', side_effect=failing):
            self.assertEqual(main(argv=[], root=ROOT), 3, 'a failing suite must fail the gate')
            self.assertEqual(calls, [ROOT])
            self.assertEqual(main(argv=['--skip-tests'], root=ROOT), 0)
        self.assertEqual(calls, [ROOT], '--skip-tests must still skip every suite')

    def test_an_end_to_end_gate_run_over_a_passing_tree_exits_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_ok.py': PASSING_MODULE,
                                          f'.agents/skills/{SUITES[3]}/scripts/test_packet.py': PASSING_MODULE})
            with captured(), patch('check_repository.inspect', return_value=[]):
                self.assertEqual(main(argv=[], root=root), 0)

    def test_an_end_to_end_gate_run_over_a_failing_tree_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = build_root(directory, {'scripts/test_ok.py': PASSING_MODULE,
                                          'scripts/test_bad.py': FAILING_MODULE})
            with captured() as messages, patch('check_repository.inspect', return_value=[]):
                self.assertNotEqual(main(argv=[], root=root), 0)
            self.assertIn('test_bad.py', messages.getvalue())


if __name__ == '__main__':
    unittest.main()