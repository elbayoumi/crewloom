"""Producer-side acceptance for the mandatory repository scope gate.

The frozen independent boundaries live in `test_repository_scope_boundaries.py` and cover the six
cases an outside reader must be able to rely on. This file covers what that suite cannot express:
every refusal the contract itself can earn, the laundering routes that must not work, the names
only behaviour a real filesystem answers, and two real Git commits decided by this repository's own
active pre-commit hook rather than by a stub or a `--no-verify`.

Every case is offline and binds one disposable tree. Nothing here is written outside its own
temporary directory, no host provider is called, no global configuration is touched, and the hook is
activated with `core.hooksPath` so the refusal is demonstrated on the real gate.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import check_repository as check
import repo_map

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent

# The runtime modules the real gate loads, copied byte for byte into a disposable checkout so the
# hook runs the same code this repository runs rather than a re-implementation of it. `crewloom`
# resolves the real role validator out of the checkout, and `workflow` supplies the one name
# comparison both the gate and the managed boundary use.
GATE_MODULES = ('check_repository.py', 'crewloom.py', 'crewloom_resources.py', 'workflow.py', 'project_binding.py',
                'repo_map.py', 'js_syntax.py')
VALIDATOR = '.agents/skills/skill-forge-recruiter/scripts/validate_skill.py'
HOOK = '.githooks/pre-commit'

SKILL_MD = """---
name: scope-fixture
description: A disposable role that exists only so the real gate has something to validate.
---

# Scope fixture role

This role exists only inside one disposable checkout. Its job is to be found by the same discovery
and the same structure validator the real gate uses, so a scope refusal in these tests is caused by
the project scope and by nothing else.

## Working memory

Its working memory is five files written for this fixture only. Nothing here is shipped.

## When to use

Never outside this test module. It has no production use, no activation trigger and no consumer.
"""

BRAIN_FILES = ('ARCHITECTURE.md', 'COMPLETED.md', 'ROADMAP_TODO.md', 'CHALLENGES.md', 'IDEAS_VAULT.md')
SKILL = 'scope-fixture'

IGNORED_SAMPLE = ('.git', '.crewloom', '__pycache__', 'node_modules', '.next', 'build', 'dist',
                  '.venv', '.tox', '.mypy_cache', '.pytest_cache', 'crewloom.egg-info',
                  '.localized', '.Spotlight-V100', '.Trashes')
IGNORED_SAMPLE_FILES = ('.DS_Store', 'Thumbs.db', 'desktop.ini')


class ScopeFixture(unittest.TestCase):
    """A disposable checkout carrying this repository's real scope contract."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='crewloom-scope-own-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        (self.root / 'LICENSE').write_text('Fixture license\n', encoding='utf-8')
        (self.root / check.SCOPE_CONTRACT).write_bytes((ROOT / check.SCOPE_CONTRACT).read_bytes())

    def contract(self):
        return json.loads((self.root / check.SCOPE_CONTRACT).read_text(encoding='utf-8'))

    def write_contract(self, document):
        (self.root / check.SCOPE_CONTRACT).write_text(json.dumps(document, indent=2) + '\n',
                                                      encoding='utf-8')

    def edit_contract(self, **changes):
        document = self.contract()
        document.update(changes)
        self.write_contract(document)

    def snapshot(self):
        """Every byte and every top-level name below this root, for a read-only assertion."""
        return ({str(path.relative_to(self.root)): path.read_bytes()
                 for path in self.root.rglob('*') if path.is_file()},
                sorted(path.name for path in self.root.iterdir()))

    def inspect(self):
        # The role validator is exercised separately; these cases are about the project scope only.
        with patch.object(check, 'load_validator',
                          return_value=SimpleNamespace(check=lambda name: [])):
            return check.inspect(self.root)

    def messages(self, errors):
        return '\n'.join(errors)


class ContractSchemaBoundaries(ScopeFixture):
    """A contract that cannot be trusted is refused, and its reason is the one real reason."""

    def test_a_missing_contract_reports_that_nothing_in_this_root_is_owned(self):
        (self.root / check.SCOPE_CONTRACT).unlink()
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('Missing ' + check.SCOPE_CONTRACT, errors[0])
        self.assertIn('own canonical root and repository', errors[0])

    def test_a_malformed_or_non_object_contract_is_reported_not_skipped(self):
        (self.root / check.SCOPE_CONTRACT).write_text('{"project_id": ', encoding='utf-8')
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('Malformed ' + check.SCOPE_CONTRACT, errors[0])
        (self.root / check.SCOPE_CONTRACT).write_text('["directories", "files"]', encoding='utf-8')
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('JSON object', errors[0])

    def test_a_contract_that_is_a_symlink_is_refused_before_it_is_read(self):
        real = self.root / 'scope-elsewhere.json'
        real.write_bytes((ROOT / check.SCOPE_CONTRACT).read_bytes())
        (self.root / check.SCOPE_CONTRACT).unlink()
        (self.root / check.SCOPE_CONTRACT).symlink_to(real)
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('may not be a symlink', errors[0])

    def test_an_unsupported_schema_version_is_refused(self):
        self.edit_contract(schema_version=2)
        self.assertIn('schema_version must be 1',
                      self.messages(check.scope_errors(self.root)))

    def test_a_foreign_or_malformed_project_identity_is_refused(self):
        for value, expected in (('sms-forwarder', 'declares a different project'),
                                ('Crewloom Toolkit', 'lowercase kebab-case text'),
                                ('', 'lowercase kebab-case text'),
                                (7, 'lowercase kebab-case text')):
            with self.subTest(project_id=value):
                self.edit_contract(project_id=value)
                self.assertIn(expected, self.messages(check.scope_errors(self.root)))
                self.edit_contract(project_id=check.SCOPE_PROJECT)
        self.assertEqual(check.scope_errors(self.root), [])

    def test_an_empty_registration_list_is_refused(self):
        self.edit_contract(directories=[])
        self.assertIn('directories must be a nonempty list',
                      self.messages(check.scope_errors(self.root)))
        self.edit_contract(directories=['scripts'], files=[])
        self.assertIn('files must be a nonempty list', self.messages(check.scope_errors(self.root)))

    def test_a_reviewed_scope_change_must_carry_its_own_policy_note(self):
        self.edit_contract(purpose='   ')
        self.assertIn('purpose must record the reviewed policy',
                      self.messages(check.scope_errors(self.root)))

    def test_the_contract_must_register_itself(self):
        document = self.contract()
        document['files'] = [name for name in document['files'] if name != check.SCOPE_CONTRACT]
        self.write_contract(document)
        self.assertIn('must register itself in files', self.messages(check.scope_errors(self.root)))

    def test_a_broken_contract_does_not_cascade_into_every_entry_looking_unregistered(self):
        self.edit_contract(project_id='sms-forwarder')
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertNotIn('Unregistered top-level', self.messages(errors))


class RegisteredPathBoundaries(ScopeFixture):
    """A registered name is one real top-level name inside this root, and nothing else."""

    def test_escaping_absolute_and_nested_names_are_refused(self):
        for name in ('/etc', '../outside', 'scripts/../outside', 'nested/name', 'nested\\name',
                     '.', '..'):
            with self.subTest(name=name):
                self.edit_contract(directories=['scripts', name])
                self.assertIn('directories name must be one top-level name inside this root',
                              self.messages(check.scope_errors(self.root)))
                self.edit_contract(directories=['scripts'])

    def test_an_empty_or_nul_bearing_name_is_refused(self):
        for name, expected in (('', 'must hold nonempty text names'),
                               ('name\x00byte', 'contains a NUL byte')):
            with self.subTest(name=name):
                self.edit_contract(directories=['scripts', name])
                self.assertIn(expected, self.messages(check.scope_errors(self.root)))
                self.edit_contract(directories=['scripts'])

    def test_a_non_text_entry_is_refused_rather_than_coerced(self):
        for name in (None, 7, ['scripts'], {'name': 'scripts'}):
            with self.subTest(name=name):
                self.edit_contract(files=['LICENSE', name])
                self.assertIn('files must hold nonempty text names',
                              self.messages(check.scope_errors(self.root)))
                self.edit_contract(files=[name for name in self.contract()['files']
                                          if isinstance(name, str)])

    def test_generated_ignored_and_operating_system_content_cannot_be_registered(self):
        for name in IGNORED_SAMPLE + IGNORED_SAMPLE_FILES:
            with self.subTest(name=name):
                self.edit_contract(directories=['scripts', name])
                self.assertIn('may not register generated, ignored or operating system metadata',
                              self.messages(check.scope_errors(self.root)))
                self.edit_contract(directories=['scripts'])

    def test_two_registered_names_that_compare_as_one_are_refused(self):
        document = self.contract()
        self.write_contract(dict(document, files=document['files'] + ['readme.md']))
        self.assertIn('name collides with an already registered name: readme.md and README.md',
                      self.messages(check.scope_errors(self.root)))
        self.edit_contract(files=['LICENSE', 'LICENSE'])
        self.assertIn('name collides with an already registered name',
                      self.messages(check.scope_errors(self.root)))
        self.edit_contract(directories=['scripts'], files=['LICENSE', 'SCRIPTS'])
        self.assertIn('name collides with an already registered name',
                      self.messages(check.scope_errors(self.root)))

    def test_an_on_disk_name_that_folds_onto_a_registered_name_is_reported(self):
        # `Documentation` is registered and `documentation` is what the directory is really called.
        # On a case-insensitive filesystem they are one entry under two spellings; on a
        # case-sensitive one they are two names for one decision. Both are the same refusal.
        self.edit_contract(directories=['Documentation'])
        (self.root / 'documentation').mkdir()
        (self.root / 'documentation' / 'map.md').write_text('# map\n', encoding='utf-8')
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('resolves through a folded alias', errors[0])
        self.assertIn('register one spelling', errors[0])

    def test_the_real_registered_contract_has_no_duplicate_or_ignored_names(self):
        document = self.contract()
        names = [name for kind in check.SCOPE_KINDS for name in document[kind]]
        self.assertEqual(len(names), len(set(names)), 'a name is registered twice')
        self.assertEqual(len(names), len({check.folded(name) for name in names}),
                         'two registered names compare as one')
        for name in names:
            self.assertFalse(check.folded(name) in check.IGNORED_KEYS, name)


class ForeignEntryBoundaries(ScopeFixture):
    """An unregistered top-level file or directory is refused however it was hidden."""

    def declare(self):
        return json.loads((ROOT / check.SCOPE_CONTRACT).read_text(encoding='utf-8'))

    def test_an_unregistered_top_level_file_and_directory_are_both_reported(self):
        (self.root / 'package.json').write_text('{"name":"unrelated-app"}\n', encoding='utf-8')
        (self.root / 'sms-forwarder').mkdir()
        (self.root / 'sms-forwarder' / 'settings.gradle.kts').write_text('name = "SMS"\n',
                                                                      encoding='utf-8')
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 2, errors)
        self.assertIn('Unregistered top-level file: package.json', errors[0])
        self.assertIn('Unregistered top-level directory: sms-forwarder', errors[1])
        for error in errors:
            self.assertIn('its own canonical root and repository', error)
            self.assertIn('reviewed scope change', error)

    def test_every_control_plane_ignore_file_still_fails_to_register_a_foreign_project(self):
        # `.gitignore`, `.git/info/exclude` and a nested project's own ignore file are all ways to
        # hide a tree from Git. None of them is a project registration decision, and `.gitignore`
        # is itself a registered file of this project rather than an input to this gate.
        (self.root / '.gitignore').write_text('sms-forwarder/\n', encoding='utf-8')
        (self.root / '.git' / 'info').mkdir(parents=True)
        (self.root / '.git' / 'info' / 'exclude').write_text('sms-forwarder/\n', encoding='utf-8')
        (self.root / 'sms-forwarder').mkdir()
        (self.root / 'sms-forwarder' / '.gitignore').write_text('build/\n', encoding='utf-8')
        (self.root / 'sms-forwarder' / 'settings.gradle.kts').write_text('name = "SMS"\n',
                                                                        encoding='utf-8')
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('Unregistered top-level directory: sms-forwarder', errors[0])

    def test_registering_the_foreign_project_without_its_own_policy_note_is_still_refused(self):
        # The reviewed way to widen the scope does not work either: it needs the note with it.
        (self.root / 'sms-forwarder').mkdir()
        (self.root / 'sms-forwarder' / 'settings.gradle.kts').write_text('name = "SMS"\n',
                                                                        encoding='utf-8')
        self.assertTrue(check.scope_errors(self.root))
        document = self.contract()
        document['directories'] = sorted(document['directories'] + ['sms-forwarder'])
        document['purpose'] = '   '
        self.write_contract(document)
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('purpose must record the reviewed policy', errors[0])
        document['purpose'] = 'This checkout now also contains the sms-forwarder application.'
        self.write_contract(document)
        self.assertEqual(check.scope_errors(self.root), [],
                         'a reviewed scope change with its policy note is accepted')

    def test_controlled_ephemeral_and_operating_system_metadata_stay_ignored(self):
        for name in IGNORED_SAMPLE:
            (self.root / name).mkdir()
            (self.root / name / 'artifact.txt').write_text('generated\n', encoding='utf-8')
        for name in IGNORED_SAMPLE_FILES:
            (self.root / name).write_bytes(b'\x00\x01desktop metadata')
        (self.root / '.agents' / 'skills' / SKILL).mkdir(parents=True)
        (self.root / '.agents' / 'skills' / SKILL / 'SKILL.md').write_text('Fixture role\n',
                                                                         encoding='utf-8')
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts' / 'good.py').write_text('value = 1\n', encoding='utf-8')
        self.assertEqual(check.scope_errors(self.root), [])
        # The fixture's empty `.git` directory is not a repository: privacy verification fails
        # closed, and nothing else (no scope, syntax or link error) is reported.
        self.assertEqual(self.inspect(), ['Cannot verify project publication privacy: '
                                          'Cannot verify the selected project Git index'])

    def test_a_symlinked_top_level_entry_is_named_not_followed(self):
        outside = Path(tempfile.mkdtemp(prefix='crewloom-scope-outside-'))
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(outside)], check=False))
        (outside / 'real-app').mkdir()
        (outside / 'real-app' / 'app.json').write_text('{"name":"outside"}\n', encoding='utf-8')
        (self.root / 'linked-app').symlink_to(outside / 'real-app', target_is_directory=True)
        errors = check.scope_errors(self.root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('Unregistered top-level directory: linked-app', errors[0])
        self.assertNotIn('app.json', self.messages(errors))

    def test_the_gate_reports_names_and_never_a_payload_body_or_a_write(self):
        secret = 'AWS_SECRET_ACCESS_KEY=never-print-this-value\n'
        (self.root / 'sms-forwarder').mkdir()
        (self.root / 'sms-forwarder' / 'keystore.properties').write_text(secret, encoding='utf-8')
        (self.root / 'package.json').write_text(secret, encoding='utf-8')
        before = self.snapshot()
        errors = check.scope_errors(self.root)
        self.assertNotIn('never-print-this-value', self.messages(errors))
        self.assertNotIn('AWS_SECRET', self.messages(errors))
        self.assertEqual(self.snapshot(), before, 'reading the scope wrote to this checkout')
        self.assertIn('Unregistered top-level file: package.json', self.messages(errors))


class ScopeGateWiringBoundaries(ScopeFixture):
    """The existing inspect and public command consume the scope result and act on it."""

    def test_inspect_surfaces_scope_errors_beside_its_other_findings(self):
        (self.root / '.agents' / 'skills' / SKILL).mkdir(parents=True)
        (self.root / '.agents' / 'skills' / SKILL / 'SKILL.md').write_text('Fixture role\n',
                                                                         encoding='utf-8')
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts' / 'good.py').write_text('value = 1\n', encoding='utf-8')
        self.assertEqual(self.inspect(), [])
        (self.root / 'sms-forwarder').mkdir()
        errors = self.inspect()
        self.assertEqual([error for error in errors if 'sms-forwarder' in error],
                         ['Unregistered top-level directory: sms-forwarder belongs to no project '
                          'declared by ' + check.SCOPE_CONTRACT + '. Keep an independent application '
                          'in its own canonical root and repository, or add it to ' + check.SCOPE_CONTRACT
                          + ' as a reviewed scope change with its own policy note.'])

    def test_the_public_command_fails_on_a_scope_violation_and_passes_on_a_clean_tree(self):
        (self.root / '.agents' / 'skills' / SKILL).mkdir(parents=True)
        (self.root / '.agents' / 'skills' / SKILL / 'SKILL.md').write_text('Fixture role\n',
                                                                         encoding='utf-8')
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts' / 'good.py').write_text('value = 1\n', encoding='utf-8')
        messages = io.StringIO()
        with contextlib.redirect_stderr(messages):
            with patch.object(check, 'load_validator',
                              return_value=SimpleNamespace(check=lambda name: [])):
                self.assertEqual(check.main(argv=['--skip-tests'], root=self.root), 0)
                (self.root / 'sms-forwarder').mkdir()
                (self.root / 'sms-forwarder' / 'app.json').write_text('{}\n', encoding='utf-8')
                self.assertEqual(check.main(argv=['--skip-tests'], root=self.root), 1)
        self.assertIn('Unregistered top-level directory: sms-forwarder', messages.getvalue())

    def test_this_real_checkout_declares_exactly_the_content_it_holds(self):
        self.assertEqual(check.scope_errors(ROOT), [])
        held = {path.name for path in ROOT.iterdir()}
        allowed = set(check.IGNORED_KEYS)
        registered = {check.folded(name) for kind in check.SCOPE_KINDS
                      for name in self.contract()[kind]}
        for name in sorted(held):
            if check.folded(name) in allowed or check.folded(name) in registered:
                continue
            self.fail('unregistered top-level entry in this checkout: ' + name)


class RealHookCommitBoundaries(unittest.TestCase):
    """Two real commits, decided by this repository's own active pre-commit hook."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='crewloom-scope-commit-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.checkout()
        self.git('init', '-q')
        self.git('config', 'gc.auto', '0')
        self.git('config', 'maintenance.auto', 'false')
        self.git('config', 'user.name', 'Scope fixture')
        self.git('config', 'user.email', 'scope@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        # The hook is activated, never bypassed: no `--no-verify` appears anywhere in this file.
        self.git('config', 'core.hooksPath', '.githooks')

    def checkout(self):
        """A disposable tree the real gate accepts, built from this repository's real files."""
        for relative in GATE_MODULES:
            target = self.root / 'scripts' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((SOURCE / relative).read_bytes())
        validator = self.root / VALIDATOR
        validator.parent.mkdir(parents=True, exist_ok=True)
        validator.write_bytes((ROOT / VALIDATOR).read_bytes())
        role = self.root / '.agents' / 'skills' / SKILL
        role.mkdir(parents=True)
        (role / 'SKILL.md').write_text(SKILL_MD, encoding='utf-8')
        (role / 'brain').mkdir()
        for name in BRAIN_FILES:
            (role / 'brain' / name).write_text('# ' + name + '\n\nFixture memory only.\n',
                                               encoding='utf-8')
        for name in check.SUITES:
            (self.root / '.agents' / 'skills' / name / 'scripts').mkdir(parents=True, exist_ok=True)
        (self.root / 'LICENSE').write_text('Fixture license\n', encoding='utf-8')
        (self.root / '.gitignore').write_text('__pycache__/\n', encoding='utf-8')
        (self.root / check.SCOPE_CONTRACT).write_bytes((ROOT / check.SCOPE_CONTRACT).read_bytes())
        hook = self.root / HOOK
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_bytes((ROOT / HOOK).read_bytes())
        os.chmod(str(hook), 0o755)

    def git(self, *arguments):
        return subprocess.run(['git', *arguments], cwd=self.root, capture_output=True, text=True,
                              env=repo_map.git_environment(), timeout=60)

    def commit(self, message):
        staged = self.git('add', '-A')
        self.assertEqual(staged.returncode, 0, staged.stderr)
        return self.git('commit', '-m', message)

    def head(self):
        return self.git('rev-parse', 'HEAD').stdout.strip()

    def test_a_clean_change_is_accepted_by_this_repositorys_own_hook(self):
        (self.root / 'scripts' / 'module.py').write_text('VALUE = 1\n', encoding='utf-8')
        (self.root / 'documentation').mkdir()
        (self.root / 'documentation' / 'MAP.md').write_text('# map\n', encoding='utf-8')
        result = self.commit('Add a registered script module and documentation')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), 'the hook accepted a clean change silently')
        listed = self.git('show', '--name-only', '--format=', 'HEAD').stdout.split()
        self.assertIn('scripts/module.py', listed)
        self.assertIn('documentation/MAP.md', listed)

    def test_an_independent_project_is_refused_by_the_hook_and_is_never_committed(self):
        clean = self.commit('Freeze the registered checkout')
        self.assertEqual(clean.returncode, 0, clean.stderr)
        before = self.head()
        app = self.root / 'sms-forwarder'
        app.mkdir()
        (app / 'settings.gradle.kts').write_text('rootProject.name = "SMS"\n', encoding='utf-8')
        (app / 'src').mkdir()
        (app / 'src' / 'Main.kt').write_text('fun main() { println("sms") }\n', encoding='utf-8')
        (self.root / '.gitignore').write_text('__pycache__/\nsms-forwarder/\n', encoding='utf-8')
        refused = self.commit('Add the independent sms-forwarder project')
        self.assertNotEqual(refused.returncode, 0,
                            'the active hook accepted an unregistered independent project')
        self.assertIn('Unregistered top-level directory: sms-forwarder', refused.stderr)
        self.assertIn('belongs to no project declared by ' + check.SCOPE_CONTRACT, refused.stderr)
        self.assertEqual(self.head(), before, 'the violating change reached a commit')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD').stdout.strip(), '1')

    def test_the_fixture_hook_is_this_repositorys_hook_and_the_tree_it_validates(self):
        self.assertEqual((self.root / HOOK).read_bytes(), (ROOT / HOOK).read_bytes())
        self.assertEqual(self.git('config', 'core.hooksPath').stdout.strip(), '.githooks')
        for relative in GATE_MODULES:
            self.assertEqual((self.root / 'scripts' / relative).read_bytes(),
                             (SOURCE / relative).read_bytes(), relative)
        self.assertIn('check_repository.py', (self.root / HOOK).read_text(encoding='utf-8'))


class BuildToolOutputsStayRegistered(unittest.TestCase):
    """The sdist ships this gate, so the files the build itself writes at its root must pass it."""

    def test_the_root_files_a_source_distribution_adds_are_registered(self):
        registered = set(json.loads((ROOT / 'REPOSITORY_SCOPE.json').read_text(encoding='utf-8'))['files'])
        for name in ('PKG-INFO', 'setup.cfg'):
            self.assertIn(name, registered, name + ' is written by the build and must not be refused')


if __name__ == '__main__':
    unittest.main()
