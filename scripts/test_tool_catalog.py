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

    def gate(self, stage=True, **options):
        if stage:  # the gate judges the staged index; staging is what a commit would capture
            self.git('add', '-A')
        return tc.gate(self.root, 'HEAD', **options)

    def authorize_legacy_change(self, path, owner='context-guardian',
                                reason='Reviewed legacy transition recorded for this exact change'):
        digest = tc._digest((self.root / path).read_bytes())
        self.catalog.setdefault('legacy_exceptions', []).append(
            {'path': path, 'sha256': digest, 'owner': owner, 'reason': reason})
        self.save()

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
        self.assertRejected('a changed legacy-unverified tool must adopt contract version 1')
        self.authorize_legacy_change('scripts/alpha.py')
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


def runnable_module(body='def add(a, b):\n    return a + b\n'):
    return body


class SnapshotRules(Repository):
    """The gate judges the staged index or the committed tree; the working tree never stands in for either."""

    def stage(self, *paths):
        self.git('add', *paths)

    def test_a_staged_cli_cannot_be_masked_by_a_clean_working_copy(self):
        self.write('scripts/staged_cli.py', TOOL_SOURCE)
        self.stage('scripts/staged_cli.py')
        self.write('scripts/staged_cli.py', 'def helper():\n    return 1\n')  # unstaged replacement
        errors, _ = self.gate(stage=False)
        self.assertTrue(any('scripts/staged_cli.py: unregistered operational entrypoint' in e for e in errors), errors)
        self.assertIn('argparse', self.git('show', ':scripts/staged_cli.py'))

    def test_the_staged_artifact_wins_when_the_working_copy_is_the_bad_one(self):
        self.write('scripts/beta.py', 'def helper():\n    return 1\n')
        self.stage('scripts/beta.py')
        self.write('scripts/beta.py', TOOL_SOURCE)  # an unstaged edit that is not part of this commit
        errors, _ = self.gate(stage=False)
        self.assertEqual(errors, [])

    def test_partially_staged_catalog_and_source_changes_cannot_conceal_a_violation(self):
        self.write('scripts/beta.py', TOOL_SOURCE + '# beta\n')
        self.catalog['tools'].append(legacy('beta', 'scripts/beta.py', **contract()))
        self.save()
        self.stage('scripts/beta.py')  # the registration stays unstaged
        errors, _ = self.gate(stage=False)
        self.assertTrue(any('unregistered operational entrypoint' in e for e in errors), errors)
        self.stage('documentation/TOOLS.json')
        self.assertEqual(self.gate(stage=False)[0], [])

    def test_evidence_is_checked_against_the_staged_bytes_not_the_edited_ones(self):
        item = Lifecycle.verified(self)
        self.commit('verified alpha')
        self.write('scripts/alpha.py', TOOL_SOURCE + '# edited, not staged\n')
        self.assertEqual(self.gate(stage=False)[0], [])
        self.stage('scripts/alpha.py')
        errors, _ = self.gate(stage=False)
        self.assertTrue(any('needs current evidence' in e for e in errors), (item['status'], errors))

    def test_a_custom_index_of_the_selected_repository_is_judged_not_the_default_one(self):
        custom = self.root / '.git' / 'custom-index'
        environment = dict(os.environ, GIT_INDEX_FILE=str(custom))
        for key in [k for k in environment if k.startswith('GIT_') and k != 'GIT_INDEX_FILE']:
            environment.pop(key)
        self.write('scripts/gamma.py', TOOL_SOURCE)
        subprocess.run(['git', '-C', str(self.root), 'read-tree', 'HEAD'], check=True, env=environment)
        subprocess.run(['git', '-C', str(self.root), 'add', 'scripts/gamma.py'], check=True, env=environment)
        self.assertEqual(self.gate(stage=False)[0], [])  # the default index never staged it
        errors, _ = self.gate(stage=False, index_file=str(custom))
        self.assertTrue(any('scripts/gamma.py: unregistered operational entrypoint' in e for e in errors), errors)
        hook = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}  # not the ambient hook of the outer commit
        hook['GIT_INDEX_FILE'] = str(custom)  # what a commit hook exports for this repository
        with patch.dict(os.environ, hook, clear=True):
            errors, _ = self.gate(stage=False)
        self.assertTrue(any('scripts/gamma.py' in e for e in errors), errors)

    def test_a_foreign_repository_selection_cannot_redirect_the_check(self):
        self.write('scripts/delta.py', TOOL_SOURCE)
        self.stage('scripts/delta.py')
        other = tempfile.TemporaryDirectory(prefix='crewloom-foreign-')
        self.addCleanup(other.cleanup)
        clean = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        subprocess.run(['git', 'init', '-q', other.name], check=True, env=clean)
        with patch.dict(os.environ, {'GIT_DIR': str(Path(other.name) / '.git'), 'GIT_WORK_TREE': other.name,
                                      'GIT_INDEX_FILE': str(Path(other.name) / '.git' / 'index')}):
            errors, _ = self.gate(stage=False)
        self.assertTrue(any('scripts/delta.py: unregistered operational entrypoint' in e for e in errors), errors)

    def test_unknown_or_unreadable_state_fails_visibly(self):
        self.assertTrue(self.gate(stage=False, snapshot='worktree')[0][0].startswith('snapshot: unknown snapshot'))
        errors, _ = tc.gate(self.root, 'HEAD', snapshot='index', index_file=str(self.root / 'missing-index'))
        self.assertTrue(errors and errors[0].startswith('snapshot:'), errors)
        oid = self.git('rev-parse', 'HEAD:scripts/alpha.py').strip()
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        subprocess.run(['git', '-C', str(self.root), 'update-index', '--index-info'], check=True, env=env,
                       input='100644 %s 1\tscripts/alpha.py\n' % oid, text=True)
        errors, _ = self.gate(stage=False)
        self.assertTrue(errors and 'unmerged' in errors[0], errors)
        outside = tempfile.TemporaryDirectory(prefix='crewloom-not-git-')
        self.addCleanup(outside.cleanup)
        errors, _ = tc.gate(outside.name, 'HEAD', snapshot='index')
        self.assertTrue(errors and errors[0].startswith('snapshot:'), errors)

    def test_the_commit_snapshot_judges_the_committed_tree_only(self):
        self.write('scripts/epsilon.py', TOOL_SOURCE + '# epsilon\n')
        self.commit('adds an unregistered cli')
        self.write('scripts/epsilon.py', 'def helper():\n    return 1\n')
        errors, _ = tc.gate(self.root, 'HEAD~1', snapshot='commit')
        self.assertTrue(any('scripts/epsilon.py: unregistered operational entrypoint' in e for e in errors), errors)
        self.git('checkout', '--', 'scripts/epsilon.py')
        self.catalog['tools'].append(legacy('epsilon', 'scripts/epsilon.py', **contract()))
        self.save()
        self.commit('registers it')
        self.assertEqual(tc.gate(self.root, 'HEAD~2', snapshot='commit')[0], [])
        errors, _ = tc.check_all(self.root, 'HEAD~2', snapshot='commit')
        self.assertEqual([e for e in errors if 'TOOLS.md' not in e], [])


class ClassificationRules(Repository):
    def assertOperational(self, relative, text, mode=None):
        self.write(relative, text)
        if mode:
            os.chmod(self.root / relative, 0o755)
        self.assertRejected('%s: unregistered operational entrypoint' % relative)
        os.unlink(self.root / relative)
        self.git('rm', '-q', '--cached', '--ignore-unmatch', relative)

    def test_unguarded_and_alternative_operational_entrypoints_are_rejected(self):
        self.assertOperational('scripts/argv_dump.py', 'import sys; print(sys.argv[1:])\n')
        self.assertOperational('scripts/runs_main.py', 'def main():\n    return 0\n\n\nmain()\n')
        self.assertOperational('scripts/bare_guard.py', "def main():\n    return 0\n\n\nif __name__ == '__main__':\n    main()\n")
        self.assertOperational('scripts/flipped_guard.py', "def go():\n    return 0\n\n\nif '__main__' == __name__:\n    go()\n")
        self.assertOperational('scripts/tuple_guard.py', "if __name__ in ('__main__',):\n    print('x')\n")
        self.assertOperational('scripts/fetches.py', "import subprocess\nRESULT = subprocess.run(['true'])\n")
        self.assertOperational('scripts/writes.py', "from pathlib import Path\nPath('x').write_text('y')\n")
        self.assertOperational('scripts/loops.py', 'for item in range(3):\n    pass\n')
        self.assertOperational('scripts/exec_bit.py', 'def noop():\n    return 0\n', mode='+x')
        self.assertOperational('scripts/pkg/__main__.py', 'def noop():\n    return 0\n')
        self.assertOperational('scripts/launch.sh', '#!/bin/sh\necho hi\n')
        self.assertOperational('.agents/skills/demo/scripts/runner.py', 'import sys\nsys.exit(0)\n')

    def test_operational_code_cannot_hide_as_a_test(self):
        for name, text, fragment in (
                ('test_hidden.py', 'import unittest\nimport subprocess\nsubprocess.run(["true"])\n', 'executes operational code'),
                ('test_cli.py', "import unittest, argparse\nif __name__ == '__main__':\n    argparse.ArgumentParser().parse_args()\n",
                 'exposes its own command line'),
                ('test_runs.py', "import unittest\nif __name__ == '__main__':\n    print('deploy')\n", 'exposes its own command line'),
                ('probe_test.py', 'import unittest\nprint(open("x").read())\n', 'executes operational code')):
            self.write('scripts/' + name, text)
            self.assertRejected('scripts/%s: classification spoofing: named like a test' % name)
            self.assertRejected(fragment)
            os.unlink(self.root / 'scripts' / name)

    def test_legitimate_internal_modules_tests_and_private_fixtures_remain_usable(self):
        self.write('scripts/constants.py', '"""Docstring."""\nimport os\nimport sys\nsys.path.insert(0, os.getcwd())\nLIMIT = 3\n\n\n'
                   'class Box:\n    size = LIMIT\n\n\ndef run():\n    print(sys.argv)\n')
        self.write('scripts/test_extra.py', 'import os\nimport unittest\nimport sys\nsys.path.insert(0, os.getcwd())\n\n\n'
                   'class T(unittest.TestCase):\n    def test_x(self):\n        self.assertTrue(True)\n\n\n'
                   "if __name__ == '__main__':\n    unittest.main()\n")
        self.assertClean()
        self.write('scripts/fake_host.py', "import sys\nif __name__ == '__main__':\n    sys.stdout.write('ok')\n")
        self.write('scripts/test_uses_fixture.py', 'import unittest\nFIXTURE = "fake_host.py"\n\n\nclass T(unittest.TestCase):\n'
                   '    def test_x(self):\n        self.assertTrue(FIXTURE)\n')
        self.catalog['assets'] = {'fixtures': [{'path': 'scripts/fake_host.py', 'reason': 'stand-in host process'}]}
        self.save()
        self.assertClean()

    def test_a_category_label_never_exempts_operational_code(self):
        self.write('scripts/sneaky.py', TOOL_SOURCE + '# sneaky\n')
        for kind in ('internal', 'fixtures'):
            self.catalog['assets'] = {kind: [{'path': 'scripts/sneaky.py', 'reason': 'trust me'}]}
            self.save()
            self.assertRejected('scripts/sneaky.py: declared as assets.%s but it is operational code' % kind)
        self.catalog['assets'] = {'build': [{'path': 'scripts/sneaky.py', 'reason': 'documentation build step'}]}
        self.save()
        self.assertClean()
        self.write('pyproject.toml', '[project.scripts]\nsneaky = "sneaky:main"\n')
        self.catalog['assets'] = {'internal': [{'path': 'scripts/sneaky.py', 'reason': 'published console script'}]}
        self.save()
        self.assertClean()

    def test_a_changed_legacy_tool_needs_the_current_standard_or_a_matching_reviewed_exception(self):
        self.write('scripts/alpha.py', TOOL_SOURCE + '# behavior change\n')
        self.assertRejected('a changed legacy-unverified tool must adopt contract version 1')
        self.authorize_legacy_change('scripts/alpha.py', reason='too short')
        self.assertRejected('legacy_exceptions entries need path')
        self.catalog['legacy_exceptions'] = []
        self.authorize_legacy_change('scripts/alpha.py')
        errors, notes = self.gate()
        self.assertEqual(errors, [])
        self.assertTrue(any('changed under a reviewed legacy exception' in n for n in notes), notes)
        self.write('scripts/alpha.py', TOOL_SOURCE + '# a second behavior change\n')
        self.assertRejected('legacy exception does not match the current bytes')
        self.assertRejected('a changed legacy-unverified tool must adopt contract version 1')

    def test_an_unchanged_legacy_tool_stays_compatible_and_adopting_a_contract_ends_the_exception(self):
        self.assertClean()
        self.write('scripts/alpha.py', TOOL_SOURCE + '# now with a contract\n')
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.authorize_legacy_change('scripts/alpha.py')
        self.assertRejected('legacy exception for scripts/alpha.py is obsolete')
        self.catalog['legacy_exceptions'] = []
        self.save()
        self.assertClean()


class AcceptanceBinding(Lifecycle):
    def tool_with_helper(self):
        self.write('scripts/support.py', 'VALUE = 1\n')
        self.write('scripts/alpha.py', 'import argparse\nimport support\n' + TOOL_SOURCE.split('\n', 1)[1] + '\n')
        self.write('scripts/test_replacement.py', TEST_SOURCE)
        return self.verified()

    def test_evidence_binds_the_acceptance_list_and_bodies(self):
        item = self.tool_with_helper()
        state = tc.verification(item, self.root)
        self.assertEqual(state['state'], 'current', state)
        record = item['evidence'][0]
        self.assertEqual(record['provenance'], tc.PROVENANCE_VERSION)
        self.assertEqual(record['counts']['executed'], 1)
        self.assertIn('scripts/support.py', record['support_sha256'])
        swapped = dict(item, acceptance=['scripts/test_replacement.py'])
        self.assertEqual(tc.verification(swapped, self.root)['state'], 'stale')
        self.assertFalse(tc.execution_decision(swapped, self.root)[0])
        self.write('scripts/test_alpha.py', TEST_SOURCE.replace('assertTrue(True)', 'assertTrue(1)'))
        state = tc.verification(item, self.root)
        self.assertEqual(state['state'], 'stale')
        self.assertIn('acceptance scripts/test_alpha.py changed', state['detail'])
        self.assertFalse(tc.execution_decision(item, self.root)[0])

    def test_changed_supporting_code_invalidates_but_unrelated_files_do_not(self):
        item = self.tool_with_helper()
        self.write('scripts/unrelated.py', 'OTHER = 1\n')
        self.write('scripts/other_tool.py', TOOL_SOURCE + '# other\n')
        self.assertEqual(tc.verification(item, self.root)['state'], 'current')
        self.write('scripts/support.py', 'VALUE = 2\n')
        state = tc.verification(item, self.root)
        self.assertEqual(state['state'], 'stale')
        self.assertIn('supporting implementation changed (scripts/support.py)', state['detail'])
        self.assertFalse(tc.execution_decision(item, self.root)[0])
        errors, _ = self.gate()
        self.assertTrue(any('needs current evidence (supporting implementation changed' in e for e in errors), errors)

    def test_every_declared_acceptance_must_be_covered(self):
        self.write('scripts/test_second.py', TEST_SOURCE)
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract(acceptance=[
            'scripts/test_alpha.py', 'scripts/test_second.py']))
        self.save()
        item = tc.record_evidence(self.root, 'alpha')
        self.assertEqual({r['test'] for r in item['evidence']}, {'scripts/test_alpha.py', 'scripts/test_second.py'})
        partial = dict(item, evidence=item['evidence'][:1])
        state = tc.verification(partial, self.root)
        self.assertEqual(state['state'], 'stale')
        self.assertIn('has no recorded evidence', state['detail'])

    def test_evidence_from_before_provenance_is_stale(self):
        item = self.verified()
        legacy_record = {key: value for key, value in item['evidence'][0].items()
                         if key in ('test', 'command', 'exit_code', 'source_sha256', 'contract_sha256', 'recorded_at')}
        state = tc.verification(dict(item, evidence=[legacy_record]), self.root)
        self.assertEqual(state['state'], 'stale')
        self.assertIn('predates provenance', state['detail'])

    def test_a_change_during_acceptance_cannot_receive_evidence(self):
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.save()
        before = (self.root / 'documentation/TOOLS.json').read_text()
        real = subprocess.run

        def mutating(command, **options):
            result = real(command, **options)
            self.write('scripts/alpha.py', TOOL_SOURCE + '# changed while the tests ran\n')
            return result
        with self.assertRaisesRegex(ValueError, 'changed while acceptance ran'):
            tc.record_evidence(self.root, 'alpha', runner=mutating)
        self.assertEqual((self.root / 'documentation/TOOLS.json').read_text(), before)


class MeaningfulAcceptance(Lifecycle):
    def record(self, source):
        self.write('scripts/test_alpha.py', source)
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.save()
        return tc.record_evidence(self.root, 'alpha')

    def assertRefused(self, source, fragment):
        with self.assertRaisesRegex(ValueError, fragment):
            self.record(source)
        self.assertEqual(tc.load_catalog(self.root)['tools'][0].get('evidence'), [])

    def test_zero_discovered_tests_cannot_promote_on_any_supported_python(self):
        self.assertRefused('import unittest\n', 'no tests were discovered')
        self.assertRefused('import unittest\n\n\nclass Empty(unittest.TestCase):\n    pass\n', 'no tests were discovered')

    def test_wholly_skipped_failing_and_erroring_acceptance_cannot_promote(self):
        skipped = ('import unittest\n\n\nclass T(unittest.TestCase):\n    @unittest.skip("never")\n'
                   '    def test_a(self):\n        pass\n')
        self.assertRefused(skipped, 'every test was skipped')
        failing = TEST_SOURCE.replace('assertTrue(True)', 'assertTrue(False)')
        self.assertRefused(failing, 'tests failed or errored')
        erroring = TEST_SOURCE.replace('self.assertTrue(True)', 'raise RuntimeError("boom")')
        self.assertRefused(erroring, 'tests failed or errored')
        self.assertRefused('import unittest\nimport not_a_real_module_xyz\n', 'tests failed or errored')

    def test_a_meaningful_suite_promotes_and_the_counts_are_retained(self):
        mixed = ('import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertTrue(True)\n\n'
                 '    @unittest.skip("not here")\n    def test_b(self):\n        pass\n')
        item = self.record(mixed)
        self.assertEqual(item['status'], 'verified')
        self.assertEqual(item['evidence'][0]['counts'], {'discovered': 2, 'run': 2, 'executed': 1, 'skipped': 1,
                                                         'failures': 0, 'errors': 0, 'expected_failures': 0,
                                                         'unexpected_successes': 0})

    def test_counts_that_do_not_describe_passing_acceptance_never_count_as_current(self):
        item = self.record(TEST_SOURCE)
        for change in ({'executed': 0, 'skipped': 1}, {'discovered': 0}, {'failures': 1}):
            record = dict(item['evidence'][0], counts=dict(item['evidence'][0]['counts'], **change))
            state = tc.verification(dict(item, evidence=[record]), self.root)
            self.assertEqual(state['state'], 'stale', change)
        malformed = dict(item['evidence'][0], counts={'run': 1})
        self.assertEqual(tc.verification(dict(item, evidence=[malformed]), self.root)['state'], 'stale')

    def test_a_runner_with_no_structured_result_records_nothing(self):
        self.write('scripts/test_alpha.py', TEST_SOURCE)
        self.catalog['tools'][0] = legacy('alpha', 'scripts/alpha.py', **contract())
        self.save()
        with self.assertRaisesRegex(ValueError, 'no structured result'):
            tc.record_evidence(self.root, 'alpha', runner=lambda *a, **k: subprocess.CompletedProcess([], 0, '', ''))


if __name__ == '__main__':
    unittest.main()
