"""N04: the living tool catalog and its commit/CI gate. Every gate rule rejects a known violation and
accepts the corresponding clean case, in real temporary Git repositories."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import crewloom
import tool_catalog as tc

TOOL_SOURCE = ('import argparse\n\n\ndef main():\n    argparse.ArgumentParser().parse_args()\n    return 0\n\n\n'
               "if __name__ == '__main__':\n    raise SystemExit(main())\n")
TEST_SOURCE = ('import unittest\n\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n\n\n'
               "if __name__ == '__main__':\n    unittest.main()\n")


def legacy(ident, path, **extra):
    return dict({'id': ident, 'skill': 'context-guardian', 'path': path, 'description': ident + ' tool',
                 'example_args': '--help', 'dependencies': ['Python standard library'], 'effect': 'read-only'}, **extra)


def contract(**extra):
    return dict({'contract_version': 1, 'interface_version': '1.0.0', 'owner': 'context-guardian', 'status': 'draft',
                 'inputs': {'path': {'type': 'path', 'required': True, 'description': 'file'}},
                 'outputs': {'report': {'type': 'json', 'required': True, 'description': 'result'}},
                 'errors': {'bad': {'exit_code': 2, 'meaning': 'refused'}},
                 'capabilities': ['read-project-files'], 'limits': {'timeout_seconds': 30},
                 'acceptance': ['scripts/test_alpha.py'], 'evidence': []}, **extra)


class Repository(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-toolgate-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for folder in ('scripts', 'documentation'):
            (self.root / folder).mkdir()
        self.write('scripts/alpha.py', TOOL_SOURCE)
        self.write('scripts/test_alpha.py', TEST_SOURCE)
        self.catalog = {'catalog_version': 2, 'tools': [legacy('alpha', 'scripts/alpha.py')]}
        self.save()
        self.git('init', '-q')
        self.commit('base')

    def git(self, *argv):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        return subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                               *argv], check=True, capture_output=True, text=True, env=env, timeout=30).stdout

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-qm', message)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def save(self):
        self.write('documentation/TOOLS.json', json.dumps(self.catalog, indent=2))

    def gate(self):
        return tc.gate(self.root, 'HEAD')

    def assertRejected(self, fragment):
        errors, _ = self.gate()
        self.assertTrue(any(fragment in error for error in errors), (fragment, errors))

    def assertClean(self):
        errors, _ = self.gate()
        self.assertEqual(errors, [])


class CatalogRules(Repository):
    def test_a_clean_legacy_catalog_is_accepted_and_reported_as_unverified(self):
        self.assertClean()
        self.assertEqual(tc.discover(self.catalog)[0]['status'], 'legacy-unverified')

    def test_duplicate_ids_and_paths_unknown_fields_and_bad_versions_are_rejected(self):
        original = copy.deepcopy(self.catalog)
        self.catalog['tools'].append(legacy('alpha', 'scripts/alpha.py'))
        self.save()
        self.assertRejected("duplicate id 'alpha'")
        self.assertRejected("duplicate path 'scripts/alpha.py'")
        self.catalog = copy.deepcopy(original)
        self.catalog['tools'][0]['surprise'] = 1
        self.save()
        self.assertRejected('unsupported field(s): surprise')
        self.catalog['tools'][0] = dict(legacy('alpha', 'scripts/alpha.py'), **contract(contract_version=2))
        self.save()
        self.assertRejected('unsupported contract_version 2')
        self.catalog['catalog_version'] = 3
        self.save()
        self.assertRejected('unsupported catalog_version')

    def test_malformed_contract_shapes_are_rejected_not_ignored(self):
        for mutation, fragment in (
                (lambda c: c['inputs'].update(path={'type': 'quantum'}), 'needs a type'),
                (lambda c: c['errors'].update(bad={'exit_code': '2', 'meaning': 'x'}), 'integer exit_code'),
                (lambda c: c.update(capabilities=['root-shell']), 'capabilities must be unique values'),
                (lambda c: c.update(limits={'timeout_seconds': 0}), 'positive integer'),
                (lambda c: c.update(acceptance=['scripts/missing.py']), 'acceptance must list existing'),
                (lambda c: c.update(interface_version='one'), 'MAJOR.MINOR.PATCH'),
                (lambda c: c.pop('owner'), 'owner is required')):
            candidate = contract()
            mutation(candidate)
            self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **candidate)
            self.save()
            self.assertRejected(fragment)
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.save()
        self.assertClean()

    def test_escaping_or_missing_paths_are_rejected(self):
        self.catalog['tools'][0]['path'] = '../outside.py'
        self.save()
        self.assertRejected('path must stay inside the repository')
        self.catalog['tools'][0]['path'] = 'scripts/ghost.py'
        self.save()
        self.assertRejected('is not a regular file')


class IncrementalRules(Repository):
    def test_an_unregistered_operational_entrypoint_is_rejected_then_accepted_once_registered(self):
        self.write('scripts/beta.py', TOOL_SOURCE)
        self.assertRejected('scripts/beta.py: unregistered operational entrypoint')
        self.catalog['tools'].append(legacy('beta', 'scripts/beta.py', **contract()))
        self.save()
        self.write('scripts/beta.py', TOOL_SOURCE + '# distinct\n')
        self.assertClean()

    def test_an_internal_module_without_a_command_line_needs_no_registration(self):
        self.write('scripts/helper.py', 'def add(a, b):\n    return a + b\n')
        self.assertClean()

    def test_declared_non_operational_assets_are_accepted_with_a_reason_and_cannot_hide_a_tool(self):
        self.write('scripts/build_docs.py', TOOL_SOURCE + '# build\n')
        self.catalog['assets'] = {'build': [{'path': 'scripts/build_docs.py', 'reason': 'documentation build step'}]}
        self.save()
        self.assertClean()
        self.catalog['assets']['build'][0]['reason'] = ''
        self.save()
        self.assertRejected('assets.build entries need an existing path and a reason')
        self.catalog['assets'] = {'build': [{'path': 'scripts/alpha.py', 'reason': 'hide it'}]}
        self.save()
        self.assertRejected('both a registered tool and assets.build')

    def test_classification_spoofing_is_rejected_and_a_real_test_is_accepted(self):
        self.write('scripts/test_sneaky.py', TOOL_SOURCE)
        self.assertRejected('classification spoofing: named like a test but imports neither')
        self.write('scripts/test_sneaky.py', 'import unittest, argparse\n' + TEST_SOURCE.split('\n', 1)[1].replace(
            "unittest.main()", "argparse.ArgumentParser().parse_args()"))
        self.assertRejected('exposes its own command line')
        self.write('scripts/test_sneaky.py', TEST_SOURCE)
        self.assertClean()

    def test_parallel_implementations_and_byte_duplicates_are_rejected(self):
        self.catalog['tools'].append(legacy('alpha-v2', 'scripts/alpha_v2.py', **contract()))
        self.write('scripts/alpha_v2.py', TOOL_SOURCE)
        self.save()
        self.assertRejected('parallel implementation name')
        self.assertRejected('byte-identical to registered tool scripts/alpha.py')
        self.write('scripts/alpha_v2.py', TOOL_SOURCE + '# differs\n')
        self.catalog['tools'][-1]['path'] = 'scripts/alpha_v2.py'
        self.assertRejected('parallel implementation name')

    def test_an_undeclared_third_party_dependency_is_rejected_until_declared(self):
        self.write('scripts/alpha.py', 'import requests\n' + TOOL_SOURCE)
        self.assertRejected("undeclared dependency 'requests'")
        self.catalog['tools'][0]['dependencies'] = ['Python standard library', 'requests 2.x (network client)']
        self.save()
        self.assertClean()

    def test_a_new_tool_needs_a_contract_acceptance_and_may_not_start_active(self):
        self.write('scripts/beta.py', TOOL_SOURCE + '# beta\n')
        self.catalog['tools'].append(legacy('beta', 'scripts/beta.py'))
        self.save()
        self.assertRejected('a new tool must declare contract version 1')
        self.catalog['tools'][-1] = legacy('beta', 'scripts/beta.py', **contract(status='active', activation={'by': 'o', 'at': 't'}))
        self.save()
        self.assertRejected('cannot be introduced as active')
        self.catalog['tools'][-1] = legacy('beta', 'scripts/beta.py', **contract())
        self.save()
        self.assertClean()

    def test_compatibility_removal_path_change_and_command_change_need_a_record(self):
        self.catalog['tools'][0]['example_args'] = '--other'
        self.save()
        self.assertRejected('changed its command arguments without a compat_note')
        self.catalog['tools'][0]['compat_note'] = 'flag renamed; old flag still accepted'
        self.save()
        self.assertClean()
        self.catalog['tools'] = [legacy('other', 'scripts/test_alpha.py')]
        self.save()
        self.assertRejected('tool alpha was removed')
        self.catalog['tools'] = [legacy('alpha', 'scripts/test_alpha.py', **contract(
            status='retired', deprecation={'migration': 'use other'}, acceptance=['scripts/test_alpha.py']))]
        self.save()
        errors, _ = self.gate()
        self.assertFalse(any('compatibility' in e for e in errors), errors)
        self.catalog['tools'][0]['status'] = 'draft'
        self.catalog['tools'][0].pop('deprecation')
        self.save()
        self.assertRejected('changed path without a retired record')

    def test_the_baseline_inventories_older_code_and_holds_everything_after_it_to_the_standard(self):
        self.write('scripts/legacy_cli.py', TOOL_SOURCE + '# predates the standard\n')
        self.commit('legacy entrypoint, unregistered')
        baseline = self.git('rev-parse', 'HEAD').strip()
        self.catalog['gate_baseline'] = baseline
        self.save()
        self.assertClean()  # judged from the baseline: the older unregistered CLI is inventory, not a violation
        self.commit('adopt baseline')
        self.write('scripts/legacy_cli.py', TOOL_SOURCE + '# edited after the baseline\n')
        self.assertRejected('scripts/legacy_cli.py: unregistered operational entrypoint')
        self.git('checkout', '--', 'scripts/legacy_cli.py')
        self.write('scripts/gamma.py', TOOL_SOURCE + '# gamma\n')
        self.assertRejected('scripts/gamma.py: unregistered operational entrypoint')
        self.git('checkout', '--', '.')
        self.catalog['gate_baseline'] = 'f' * 40
        self.save()
        self.assertRejected('gate_baseline may not move')
        self.catalog['gate_baseline'] = 'nothex'
        self.save()
        self.assertRejected('gate_baseline must be a full 40-hex commit id')

    def test_inherited_hook_git_variables_cannot_redirect_the_gate_to_another_repository(self):
        other = tempfile.TemporaryDirectory(prefix='crewloom-other-repo-')
        self.addCleanup(other.cleanup)
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        subprocess.run(['git', 'init', '-q', other.name], check=True, capture_output=True, env=env)
        with patch.dict(os.environ, {'GIT_DIR': str(Path(other.name) / '.git'), 'GIT_INDEX_FILE': str(Path(other.name) / '.git/index')}):
            errors, notes = self.gate()  # what a commit hook exports for the repository being committed
        self.assertEqual((errors, notes), ([], []))

    def test_a_missing_base_is_visible_not_a_silent_pass(self):
        errors, notes = tc.gate(self.root, 'no-such-revision')
        self.assertEqual(errors, [])
        self.assertTrue(any('incremental checks skipped' in n for n in notes))


class Lifecycle(Repository):
    def verified(self):
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.save()
        return tc.record_evidence(self.root, 'alpha')

    def test_evidence_binds_to_the_exact_source_and_contract_and_goes_stale_when_either_changes(self):
        item = self.verified()
        self.assertEqual(item['status'], 'verified')
        self.assertEqual(tc.verification(item, self.root)['state'], 'current')
        self.assertClean()
        self.write('scripts/alpha.py', TOOL_SOURCE + '# changed behavior\n')
        self.assertRejected('needs current evidence')
        tc.record_evidence(self.root, 'alpha')
        self.assertClean()
        catalog = tc.load_catalog(self.root)
        catalog['tools'][0]['limits'] = {'timeout_seconds': 31}
        self.catalog = catalog
        self.save()
        self.assertRejected('needs current evidence')

    def test_a_failing_acceptance_records_nothing_and_a_missing_evidence_is_not_verification(self):
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.save()
        before = (self.root / 'documentation/TOOLS.json').read_text()
        failed = subprocess.CompletedProcess([], 1, '', 'AssertionError')
        with self.assertRaisesRegex(ValueError, 'no evidence was recorded'):
            tc.record_evidence(self.root, 'alpha', runner=lambda *a, **k: failed)
        self.assertEqual((self.root / 'documentation/TOOLS.json').read_text(), before)
        self.catalog['tools'][0]['status'] = 'verified'
        self.save()
        self.assertRejected('needs current evidence (no evidence is recorded)')

    def test_activation_needs_a_record_and_deprecation_a_migration(self):
        item = self.verified()
        self.catalog['tools'][0] = dict(item, status='active')
        self.save()
        self.assertRejected('active status needs an activation record')
        self.catalog['tools'][0] = dict(item, status='deprecated')
        self.save()
        self.assertRejected('needs deprecation.migration')
        self.catalog['tools'][0] = dict(item, status='deprecated', deprecation={'migration': 'use beta'})
        self.save()
        self.assertClean()

    def test_the_runner_refuses_draft_retired_and_stale_tools_but_keeps_legacy_ones_working(self):
        legacy_item = legacy('alpha', 'scripts/alpha.py')
        self.assertEqual(tc.execution_decision(legacy_item, self.root), (True, None))
        draft = legacy('alpha', 'scripts/alpha.py', **contract())
        self.assertFalse(tc.execution_decision(draft, self.root)[0])
        retired = legacy('alpha', 'scripts/alpha.py', **contract(status='retired', deprecation={'migration': 'x'}))
        self.assertFalse(tc.execution_decision(retired, self.root)[0])
        item = self.verified()
        self.assertEqual(tc.execution_decision(item, self.root), (True, None))
        self.write('scripts/alpha.py', TOOL_SOURCE + '# edited after verification\n')
        allowed, message = tc.execution_decision(item, self.root)
        self.assertFalse(allowed)
        self.assertIn('stale verification', message)
        warning = tc.execution_decision(dict(item, status='deprecated', deprecation={'migration': 'use beta'}), self.root)
        self.assertEqual(warning, (True, 'Tool alpha is deprecated: use beta'))

    def test_crewloom_run_enforces_the_lifecycle_before_dispatch(self):
        import contextlib
        import io
        draft = legacy('alpha', 'scripts/alpha.py', **contract())
        for status, fragment in (('draft', 'is draft and may not be run'), ('retired', 'is retired and may not be run')):
            item = dict(draft, status=status, deprecation={'migration': 'x'})
            errors = io.StringIO()
            with patch.object(crewloom, 'read_tools', return_value=[item]), \
                    patch.object(crewloom, 'tool_path', return_value=self.root / 'scripts/alpha.py'), \
                    patch.object(crewloom.resources, 'distribution_root', return_value=self.root), \
                    patch.object(sys, 'argv', ['crewloom', 'run', 'alpha']), \
                    patch.object(crewloom.subprocess, 'run', side_effect=AssertionError('must not dispatch')), \
                    contextlib.redirect_stderr(errors):
                with self.assertRaises(SystemExit) as raised:
                    crewloom.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn(fragment, errors.getvalue())
        legacy_item = legacy('alpha', 'scripts/alpha.py')
        calls = []
        with patch.object(crewloom, 'read_tools', return_value=[legacy_item]), \
                patch.object(crewloom, 'tool_path', return_value=self.root / 'scripts/alpha.py'), \
                patch.object(crewloom.resources, 'distribution_root', return_value=self.root), \
                patch.object(crewloom, 'log_run'), \
                patch.object(sys, 'argv', ['crewloom', 'run', '--project', str(self.root), 'alpha']), \
                patch.object(crewloom.subprocess, 'run', side_effect=lambda *a, **k: calls.append(a) or subprocess.CompletedProcess(a, 0)):
            self.assertEqual(crewloom.main(), 0)
        self.assertEqual(len(calls), 1, 'a legacy tool still dispatches for compatibility')


class GeneratedView(Repository):
    def test_the_human_view_is_generated_from_the_catalog_and_drift_is_rejected(self):
        self.write('documentation/TOOLS.md', 'Intro\n\n' + tc.MARK_BEGIN + '\nstale\n' + tc.MARK_END + '\n\nOutro\n')
        self.assertEqual(len(tc.check_rendered(self.root)), 1)
        text = tc.render_into((self.root / 'documentation/TOOLS.md').read_text(), self.catalog)
        self.write('documentation/TOOLS.md', text)
        self.assertEqual(tc.check_rendered(self.root), [])
        self.assertIn('| [alpha](../scripts/alpha.py) | legacy-unverified |', text)
        self.assertTrue(text.startswith('Intro') and text.rstrip().endswith('Outro'))
        self.write('documentation/TOOLS.md', text.replace('alpha tool', 'hand edited'))
        self.assertEqual(len(tc.check_rendered(self.root)), 1)
        with self.assertRaisesRegex(ValueError, 'markers are missing'):
            tc.render_into('no markers', self.catalog)

    def test_discovery_is_compact_and_description_loads_one_detailed_contract(self):
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.save()
        compact = tc.discover(self.catalog)[0]
        self.assertEqual(set(compact), {'id', 'status', 'effect', 'purpose'})
        detail = tc.describe(self.catalog, self.root, 'alpha')
        self.assertEqual(detail['inputs']['path']['type'], 'path')
        self.assertEqual(detail['verification']['state'], 'not-applicable')
        with self.assertRaisesRegex(ValueError, 'Unknown registered tool'):
            tc.describe(self.catalog, self.root, 'ghost')


if __name__ == '__main__':
    unittest.main()
