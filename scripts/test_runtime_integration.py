"""Owned runtime integration: one host-authority answer, and honest public CLI delegation.

Two things are proved here that no other suite proves together.

The first is that the managed workflow and the native host guard now answer identically about
native host authority. A managed step and a host agent are different writers under different
engines, and a path one of them refuses while the other allows is exactly how a declared artifact
becomes a way to edit the guard that constrains it. The reservation is scoped to declared artifacts
only: Crewloom's own installer still writes its own control configuration.

The second is that `crewloom host`, `crewloom readiness` and `crewloom context study` forward the
caller's whole argv to the module that really owns the command, without re-declaring a single
option here and without reaching a provider. Delegates are mocked only to read the forwarded argv;
the real help commands are then run as actual processes so the chain is proven rather than assumed.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agency_readiness
import crewloom
import evaluate_hosts
import host_lifecycle as lifecycle
import project_binding as pb
import project_lessons
import repo_map
import reviewer_credentials
import task_coordinator
import workflow
import test_native_lifecycle_acceptance_boundaries as fixtures

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
PYPROJECT = ROOT / 'pyproject.toml'
DECLARED_MODULES = re.compile(r'^py-modules\s*=\s*\[(.*)\]\s*$', re.MULTILINE)


def declared_runtime_modules():
    """Every flat runtime module the distribution metadata declares, read from the metadata.

    The installed layout is these modules sitting flat beside one `crewloom_data` directory, so the
    simulation copies the declared list instead of a hand-written one and cannot drift from what
    the wheel would actually install.
    """
    found = DECLARED_MODULES.search(PYPROJECT.read_text(encoding='utf-8'))
    if not found:
        raise unittest.SkipTest('pyproject.toml no longer declares py-modules')
    return [item.strip().strip('"\'') for item in found.group(1).split(',') if item.strip()]

# The names both boundaries must answer for, as the frozen acceptance suite spells them. `.codex`,
# `.claude` and `.opencode` are the host configuration trees; `opencode.json` and `opencode.jsonc`
# at the project root are OpenCode's own project configuration.
HOST_AUTHORITY = ('opencode.json', 'opencode.jsonc', 'OPENCODE.JSONC', 'OPENCODE.JSON',
                  '.codex/config.toml', '.CODEX/config.toml', '.claude/settings.json',
                  '.opencode/plugins/guard.js')

# Ordinary project configuration, including names that merely start with or contain a reserved
# one. A reservation is a whole path component, never a prefix or a substring.
ORDINARY_CONFIGURATION = ('src/settings.json', 'docs/config.toml', 'src/opencode.py',
                          '.claude-notes.md', 'src/.codex-helper.py')

# The real provider surface. None of it may be reached by a command that only forwards argv.
PROVIDER_CALLS = ('provider_gateway.request', 'provider_gateway.generate', 'model_host.generate')


def cli(*arguments):
    """One real `crewloom` process in the source layout."""
    return subprocess.run([sys.executable, str(SCRIPTS / 'crewloom.py'), *arguments],
                          capture_output=True, text=True, cwd=str(ROOT), timeout=300)


class HostAuthorityAgreement(unittest.TestCase):
    """The managed workflow and the native guard must give the same answer about host authority."""

    def setUp(self):
        case = fixtures.NativeLifecycleBoundaries()
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.root = case.root
        self.record = case.guard_record()

    def workflow_refuses(self, relative):
        with self.assertRaises(ValueError, msg='declared_path accepted ' + relative):
            workflow.declared_path(self.root, relative)

    def guard_refuses(self, relative):
        with self.assertRaises(ValueError, msg='guard accepted ' + relative):
            lifecycle.guard_file_edits(
                self.root, self.record,
                '*** Begin Patch\n*** Add File: ' + relative + '\n+{}\n*** End Patch\n')

    def test_both_boundaries_refuse_every_reserved_host_authority_name(self):
        for name in HOST_AUTHORITY:
            with self.subTest(path=name):
                self.workflow_refuses(name)
                self.guard_refuses(name)

    def test_reserved_names_are_refused_under_case_and_normalization_folding(self):
        for name in ('OpenCode.Json', 'OPENCODE.JSONC', '.Codex/config.toml',
                     '.CLAUDE/Settings.json', '.OpenCode/plugins/Guard.js'):
            with self.subTest(path=name):
                self.workflow_refuses(name)
                self.guard_refuses(name)

    def test_a_symlink_cannot_alias_a_reserved_host_tree(self):
        (self.root / '.codex').mkdir()
        (self.root / 'vendor-alias').symlink_to(self.root / '.codex', target_is_directory=True)
        for name in ('vendor-alias/hooks.json', 'src/../.claude/settings.json'):
            with self.subTest(path=name):
                self.workflow_refuses(name)
                self.guard_refuses(name)

    def test_a_hardlink_cannot_alias_a_reserved_host_configuration_file(self):
        # A hardlink is one inode behind two names, so nothing in the declared path spells a
        # reserved tree. Both boundaries must still answer that the file it reaches is the host's
        # own configuration, and an ordinary file that merely shares a name keeps working.
        authority = self.root / 'opencode.json'
        authority.write_text('{"plugin": []}\n', encoding='utf-8')
        os.link(authority, self.root / 'ordinary.json')
        self.assertTrue(authority.samefile(self.root / 'ordinary.json'))
        for name in ('ordinary.json',):
            with self.subTest(path=name):
                self.workflow_refuses(name)
                self.guard_refuses(name)
        self.assertEqual(workflow.declared_path(self.root, 'src/ordinary.json'),
                         self.root / 'src' / 'ordinary.json')

    def test_ordinary_project_configuration_is_never_reserved(self):
        for name in ORDINARY_CONFIGURATION:
            with self.subTest(path=name):
                self.assertEqual(workflow.declared_path(self.root, name),
                                 self.root / name)
                document = self.record.copy()
                document['declared_outputs'] = [name]
                document['declared_output_keys'] = sorted(lifecycle.declared_output_keys([name]))
                result = lifecycle.guard_file_edits(
                    self.root, document,
                    '*** Begin Patch\n*** Add File: ' + name + '\n+{}\n*** End Patch\n')
                self.assertIn(name, result['targets'])

    def test_the_reservation_is_scoped_to_declared_artifacts_not_the_installer(self):
        # The installer writes `.codex/hooks.json` and `.claude/settings.json` as control metadata.
        # That write is authorized and must not be caught by the artifact reservation.
        for relative in ('.codex/hooks.json', '.claude/settings.json',
                         '.opencode/plugins/crewloom-lifecycle.js'):
            with self.subTest(path=relative):
                self.assertEqual(pb.writable(self.root, relative), self.root / relative)
                self.assertEqual(workflow.safe_path(self.root, relative), self.root / relative)
        with patch.object(lifecycle, '_version_of', return_value='codex-cli 0.155.1'):
            report = lifecycle.install(self.root, 'native-boundary', 'codex', 'context-guardian',
                                       criteria_path='criteria.md', sources=['src/output.py'],
                                       declared_outputs=['src/output.py'])
        self.assertTrue((self.root / '.codex/hooks.json').is_file())
        self.assertEqual(report['control_relative'], '.codex/hooks.json')


class DelegatedArgv(unittest.TestCase):
    """The forwarded argv, read from a mocked delegate that never runs its real body."""

    def invoke(self, module, arguments, code=7):
        """The argv one mocked delegate received, and the exit code it gave back."""
        recorded = []

        def delegate(argv):
            recorded.append(argv)
            return code

        with patch.object(sys, 'argv', ['crewloom', *arguments]), \
                patch.object(module, 'main', delegate):
            returned = crewloom.main()
        self.assertEqual(len(recorded), 1, 'the delegate was not called exactly once')
        self.assertEqual(returned, code, "the owning module's exit code must pass through unchanged")
        return recorded[0]

    def no_provider(self):
        calls = []
        patches = [patch(target, side_effect=lambda *a, _t=target, **k: calls.append(_t))
                   for target in PROVIDER_CALLS]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return calls

    def test_host_forwards_its_whole_argv_to_the_owning_module(self):
        argv = ['host', 'install', '--project', '/tmp/p', '--project-id', 'p', '--host', 'codex',
                '--role', 'context-guardian', '--output', 'src/x.py', '--context-limit', '4096']
        self.assertEqual(self.invoke(lifecycle, argv), argv[1:])

    def test_readiness_forwards_a_leading_flag_that_a_remainder_placeholder_would_refuse(self):
        # `readiness` has no subcommand, so its first argument is a flag. This is the exact shape
        # `argparse.REMAINDER` cannot carry, and the reason forwarding is decided before parsing.
        argv = ['readiness', '--project-id', 'p', '--project-root', '/tmp/p',
                '--agency-root', '/tmp/agency', '--registry', 'registry.json', '--language', 'ar']
        self.assertEqual(self.invoke(agency_readiness, argv), argv[1:])

    def test_context_study_forwards_to_the_one_real_evaluate_hosts_entry_point(self):
        argv = ['context', 'study', '--output', '/tmp/study', '--study-host', 'codex',
                '--study-host', 'opencode', '--repeats', '2', '--case-runs', '3']
        forwarded = self.invoke(evaluate_hosts, argv)
        # `--study` is the selector the owning module already understands, so this command and the
        # legacy `evaluate-hosts` invocation stay one code path. No caller flag is dropped.
        self.assertEqual(forwarded, ['--study', '--output', '/tmp/study', '--study-host', 'codex',
                                     '--study-host', 'opencode', '--repeats', '2', '--case-runs', '3'])

    def test_forwarding_reaches_no_provider(self):
        calls = self.no_provider()
        for module, argv in ((lifecycle, ['host', 'versions']),
                             (agency_readiness, ['readiness', '--project-id', 'p']),
                             (evaluate_hosts, ['context', 'study', '--output', '/tmp/study'])):
            with self.subTest(command=argv[0]):
                with patch.object(sys, 'argv', ['crewloom', *argv]), \
                        patch.object(module, 'main', return_value=0):
                    self.assertEqual(crewloom.main(), 0)
        self.assertEqual(calls, [], 'a forwarding command reached the provider surface')

    def test_a_real_delegated_command_reads_project_state_without_a_provider(self):
        # The delegate is NOT mocked here: this proves the real hand-over runs the real engine,
        # read-only, on a real bound project, and still touches no provider.
        calls = self.no_provider()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=str(root), env=repo_map.git_environment(), check=True)
        crewloom.install_skills(root, 'agents', ['context-guardian'], False)
        pb.bootstrap(root, project_id='delegated-read')
        with patch.object(sys, 'argv', ['crewloom', 'host', 'status', '--project', str(root)]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(crewloom.main(), 0)
        report = json.loads(output.getvalue())
        self.assertEqual([host['host'] for host in report['hosts']], list(lifecycle.HOSTS))
        self.assertFalse(any(host['installed'] for host in report['hosts']),
                         'a read-only report must not claim an installation')
        self.assertEqual(calls, [])

    def test_unrelated_commands_are_never_pre_dispatched(self):
        self.assertIsNone(crewloom.delegated_command(['list']))
        self.assertIsNone(crewloom.delegated_command(['context', 'context-guardian']))
        self.assertIsNone(crewloom.delegated_command(['evaluate-hosts', '--output', '/tmp/o']))
        self.assertIsNone(crewloom.delegated_command([]))
        self.assertEqual(crewloom.delegated_command(['host']), ('host_lifecycle', []))


class LegacyInvocation(unittest.TestCase):
    """Backward compatibility: the pre-existing commands keep the behaviour they already had."""

    def test_legacy_evaluate_hosts_keeps_its_own_choices_and_flags(self):
        result = cli('evaluate-hosts', '--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--host {codex,claude}', result.stdout)
        for flag in ('--codex-model', '--claude-model', '--repeats', '--seed', '--timeout'):
            self.assertIn(flag, result.stdout)

    def test_the_study_flags_reach_the_study_command_and_not_evaluate_hosts(self):
        study = cli('context', 'study', '--help')
        self.assertEqual(study.returncode, 0, study.stderr)
        self.assertIn('--study-host {codex,opencode}', study.stdout)
        self.assertNotIn('--codex-model', study.stdout)
        refused = cli('context', 'study', '--study-host', 'claude')
        self.assertEqual(refused.returncode, 2)
        self.assertNotIn('Traceback', refused.stderr)

    def test_the_context_pack_command_is_unchanged(self):
        result = cli('context', '--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--language {en,ar}', result.stdout)
        self.assertIn('skill', result.stdout)
        self.assertIsNone(crewloom.delegated_command(['context', 'context-guardian', '--out', 'p.md']),
                          'the context pack command must not be treated as the study command')

    def test_existing_remainder_commands_keep_their_documented_shape(self):
        # `project`, `workflow`, `coordinator`, `lesson` and `reviewer` still forward through
        # `argparse.REMAINDER`, which requires a subcommand word before any flag. This records
        # their actual reachability rather than changing it.
        owners = {'project': pb, 'lesson': project_lessons, 'reviewer': reviewer_credentials,
                  'workflow': workflow, 'coordinator': task_coordinator}
        for command, word in (('project', 'enter'), ('workflow', 'run'), ('coordinator', 'status'),
                              ('lesson', 'list'), ('reviewer', 'list')):
            with self.subTest(command=command):
                recorded = []
                argv = [command, word, '--project', '.', '--help']
                with patch.object(sys, 'argv', ['crewloom', *argv]), \
                        patch.object(owners[command], 'main', recorded.append):
                    crewloom.main()
                self.assertEqual(len(recorded), 1)
                self.assertEqual(recorded[0], argv[1:])

    def test_the_top_level_help_lists_every_delegated_command(self):
        result = cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in crewloom.DELEGATED:
            self.assertIn(command, result.stdout)


class RealHelpCommands(unittest.TestCase):
    """The child parsers, run as real processes. Source layout and installed layout."""

    HELP = ((('host', '--help'), 'Native host lifecycle adapter for one bound project'),
            (('host', 'install', '--help'), '--acceptance-step'),
            (('host', 'status', '--help'), '--project-id'),
            (('readiness', '--help'), '--max-evidence-age-seconds'),
            (('context', 'study', '--help'), '--study-host {codex,opencode}'))

    def assert_real_help(self, runner, label):
        for arguments, expected in self.HELP:
            with self.subTest(layout=label, command=' '.join(arguments)):
                result = runner(*arguments)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn('Traceback', result.stderr)
                self.assertIn(expected, result.stdout)
                # The outer placeholder usage names no option at all; the real child help does.
                self.assertNotIn('positional arguments:\n  host_arguments', result.stdout)

    def test_source_layout_help_reaches_the_real_child_parsers(self):
        self.assert_real_help(cli, 'source')

    def test_installed_layout_help_reaches_the_real_child_parsers(self):
        # The wheel keeps the CLI modules flat beside one `crewloom_data` directory. Building it
        # needs the pinned backend and network, so this reproduces the layout instead of claiming
        # the wheel: same declared `py-modules`, same packaged data root, and an assertion that
        # the packaged branch is the one that answered.
        work = Path(tempfile.mkdtemp(prefix='crewloom-installed-layout-'))
        self.addCleanup(shutil.rmtree, work, True)
        site = work / 'site'
        site.mkdir()
        data = site / 'crewloom_data'
        (data / '.agents').mkdir(parents=True)
        shutil.copytree(ROOT / '.agents' / 'skills', data / '.agents' / 'skills')
        shutil.copytree(ROOT / 'documentation', data / 'documentation')
        shutil.copytree(ROOT / 'adapters', data / 'adapters')
        declared = declared_runtime_modules()
        for name in declared:
            shutil.copy2(SCRIPTS / (name + '.py'), site / (name + '.py'))
        for required in ('crewloom', 'host_lifecycle', 'agency_readiness', 'evaluate_hosts'):
            self.assertIn(required, declared,
                          'the delegated modules must ship as flat runtime modules')
        probe = ('import json,sys;'
                 'sys.path.insert(0, sys.argv[1]);'
                 'import crewloom_resources as r;'
                 'print(json.dumps({"source": r.source_checkout(), "root": str(r.distribution_root()),'
                 ' "roles": len(r.role_ids())}))')
        layout = subprocess.run([sys.executable, '-c', probe, str(site)],
                                capture_output=True, text=True, cwd=str(work), timeout=300)
        self.assertEqual(layout.returncode, 0, layout.stderr[-2000:])
        report = json.loads(layout.stdout)
        self.assertFalse(report['source'], 'the packaged layout was not the one that answered')
        self.assertTrue(report['root'].endswith('crewloom_data'))
        self.assertEqual(report['roles'], 42)

        def installed(*arguments):
            script = ('import sys;'
                      'sys.path.insert(0, sys.argv[1]);'
                      'import crewloom;'
                      'sys.argv = ["crewloom", *sys.argv[2:]];'
                      'raise SystemExit(crewloom.main())')
            return subprocess.run([sys.executable, '-c', script, str(site), *arguments],
                                  capture_output=True, text=True, cwd=str(work), timeout=300,
                                  env={**os.environ, 'CREWLOOM_NO_LOG': '1'})

        self.assert_real_help(installed, 'installed')
        listed = installed('list')
        self.assertEqual(listed.returncode, 0, listed.stderr[-2000:])
        self.assertEqual(len(listed.stdout.split()), 42)
        pack = installed('context', 'context-guardian', '--out', str(work / 'pack.md'))
        self.assertEqual(pack.returncode, 0, pack.stderr[-2000:])
        self.assertIn('# Context pack', (work / 'pack.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()