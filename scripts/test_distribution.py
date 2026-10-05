"""Real distribution acceptance: build a wheel and an sdist, then use them outside the checkout.

This suite builds and installs artifacts, so it needs a build environment and network
access for the pinned backend. It is therefore opt-in, exactly like the real Docker
checks, and it is the only place in the repository that proves the installed wheel
rather than the source tree actually works.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import venv
import zipfile
from pathlib import Path

import repo_map

ROOT = Path(__file__).resolve().parents[1]
BUILD_REQUIREMENTS = 'setuptools>=77,<81'
FORBIDDEN_PARTS = ('.crewloom', 'node_modules', '.next', '__pycache__', 'build', 'dist')
SECRET_PATTERN = re.compile(r'(?i)(api[_-]?key|secret|password|bearer\s+[A-Za-z0-9._-]{12,}|BEGIN [A-Z ]*PRIVATE KEY)')


def run(argv, cwd=None, env=None, timeout=900):
    merged = {**os.environ, **(env or {})}
    result = subprocess.run([str(item) for item in argv], cwd=None if cwd is None else str(cwd),
                            env=merged, capture_output=True, text=True, timeout=timeout)
    return result


@unittest.skipUnless(os.environ.get('CREWLOOM_DISTRIBUTION_TESTS') == '1',
                     'Enable real wheel and sdist build/install acceptance explicitly')
class InstalledDistributionTests(unittest.TestCase):
    """One build and one install shared by every assertion in this class."""

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix='crewloom-distribution-'))
        cls.reports = []
        try:
            cls._build_and_install()
        except Exception:
            shutil.rmtree(cls.work, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    @classmethod
    def _build_and_install(cls):
        cls.builder = cls.work / 'builder'
        venv.EnvBuilder(with_pip=True).create(str(cls.builder))
        installed = run([cls.builder / 'bin' / 'python', '-m', 'pip', 'install',
                         '--disable-pip-version-check', '--no-input', BUILD_REQUIREMENTS])
        if installed.returncode:
            raise unittest.SkipTest('Pinned build backend is unavailable: ' + installed.stderr[-400:])
        # Build from a pristine copy so a stale egg-info or build directory cannot mask a
        # packaging omission, and so the artifacts provably come from the declared sources.
        source = cls.work / 'source'
        shutil.copytree(ROOT, source, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', 'node_modules',
                                                      '.next', '.crewloom', 'build', 'dist',
                                                      '*.egg-info', '.git', '.tmp'))
        cls.dists = cls.work / 'dist'
        cls.dists.mkdir()
        # Wheel and sdist are built by separate interpreters. Building both through one
        # `setuptools.build_meta` session leaves the archive in a command-specific staging
        # directory, which would test the staging path instead of the declared contract.
        artifacts = {}
        for label, target in (('wheel', 'build_wheel'), ('sdist', 'build_sdist')):
            built = run([cls.builder / 'bin' / 'python', '-c',
                         'import setuptools.build_meta as backend,sys;print(backend.' + target + '(sys.argv[1]))',
                         cls.dists], cwd=source)
            cls.reports.append(('build-' + label, built))
            if built.returncode:
                raise AssertionError('Distribution build failed:\n' + built.stderr[-3000:])
            artifacts[label] = built.stdout.strip().splitlines()[-1]
        cls.wheel = cls.dists / artifacts['wheel']
        cls.sdist = cls.dists / artifacts['sdist']
        for path in (cls.wheel, cls.sdist):
            if not path.is_file():
                raise AssertionError('Build backend did not write ' + str(path))
        cls.target = cls.work / 'installed'
        venv.EnvBuilder(with_pip=True).create(str(cls.target))
        added = run([cls.target / 'bin' / 'python', '-m', 'pip', 'install',
                     '--disable-pip-version-check', '--no-input', '--no-deps', cls.wheel])
        cls.reports.append(('install-wheel', added))
        if added.returncode:
            raise AssertionError('Wheel install failed:\n' + added.stderr[-3000:])
        # Every command below runs from outside the checkout, with the repository removed
        # from PYTHONPATH, so nothing can accidentally fall back to source files.
        cls.project = cls.work / 'project'
        cls.project.mkdir()
        cls.cli = [cls.target / 'bin' / 'crewloom']
        cls.env = {'PYTHONPATH': '', 'CREWLOOM_NO_LOG': '1'}

    def crewloom(self, *args, cwd=None, env=None, stdin=None):
        command = self.cli + list(args)
        merged = {**self.env, **(env or {})}
        return subprocess.run([str(item) for item in command], cwd=str(cwd or self.project), env=merged,
                              input=stdin, capture_output=True, text=True, timeout=600)

    # ------------------------------------------------------------------ archives

    def test_wheel_and_sdist_contain_the_declared_public_material_only(self):
        wheel_names = zipfile.ZipFile(self.wheel).namelist()
        sdist_names = tarfile.open(self.sdist).getnames()
        for label, names in (('wheel', wheel_names), ('sdist', sdist_names)):
            with self.subTest(archive=label):
                self.assertFalse([name for name in names
                                  if any(part in FORBIDDEN_PARTS for part in Path(name).parts)],
                                 label + ' carries forbidden trees')
                self.assertFalse([name for name in names if name.endswith(('.pyc', '.pyo', '.log'))], label)
                self.assertFalse([name for name in names if 'runs.jsonl' in name or 'events.jsonl' in name], label)
        prefix = self.sdist.name[: -len('.tar.gz')]
        self.assertIn(prefix + '/LICENSE', sdist_names)
        self.assertIn(prefix + '/NOTICE', sdist_names)
        self.assertIn(prefix + '/README.md', sdist_names)
        self.assertIn(prefix + '/README.ar.md', sdist_names)
        self.assertTrue([name for name in sdist_names if '/documentation/TOOLS.json' in name])
        self.assertTrue([name for name in wheel_names if name.endswith('.dist-info/licenses/LICENSE')])
        self.assertTrue([name for name in wheel_names if name.endswith('.dist-info/licenses/NOTICE')])
        roles = [name for name in wheel_names if name.startswith('crewloom_data/.agents/skills/')
                 and name.endswith('/SKILL.md')]
        self.assertEqual(len(roles), 42, 'wheel must carry all 42 roles')

    def test_archives_carry_no_credential_material(self):
        for path in (self.wheel, self.sdist):
            blob = path.read_bytes()
            with self.subTest(archive=path.name):
                self.assertNotIn(b'PRIVATE KEY', blob)
                self.assertNotIn(b'CREWLOOM_REVIEWER_TOKEN=', blob)
                matches = SECRET_PATTERN.findall(blob.decode('utf-8', 'replace'))
                self.assertEqual([item for item in matches if 'password' in str(item).lower()], [], matches[:5])

    def test_sdist_rebuilds_the_same_wheel_layout(self):
        unpacked = self.work / 'unpacked'
        tarfile.open(self.sdist).extractall(unpacked, filter='data')
        rebuilt = self.work / 'rebuilt'
        rebuilt.mkdir()
        source = unpacked / self.sdist.name[: -len('.tar.gz')]
        result = run([self.builder / 'bin' / 'python', '-c',
                      'import setuptools.build_meta as backend,sys;print(backend.build_wheel(sys.argv[1]))',
                      rebuilt], cwd=source)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        names = set(zipfile.ZipFile(next(rebuilt.glob('*.whl'))).namelist())
        roles = [name for name in names if name.startswith('crewloom_data/.agents/skills/')
                 and name.endswith('/SKILL.md')]
        self.assertEqual(len(roles), 42)
        self.assertIn('crewloom_data/documentation/TOOLS.json', names)

    # ------------------------------------------------------------------ installed CLI

    def test_resources_resolve_inside_the_installation_not_the_checkout(self):
        result = run([self.target / 'bin' / 'python', '-c',
                      'import crewloom_resources as r, json;'
                      'print(json.dumps({"root": str(r.distribution_root()), "roles": r.role_ids(),'
                      ' "source": r.source_checkout()}))'])
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout)
        self.assertFalse(report['source'], 'an installed wheel must not report a source checkout')
        self.assertEqual(len(report['roles']), 42)
        self.assertNotIn(str(ROOT), report['root'])
        self.assertTrue(report['root'].endswith('crewloom_data'))

    def test_all_42_roles_discover_validate_and_show(self):
        listed = self.crewloom('list')
        self.assertEqual(listed.returncode, 0, listed.stderr)
        identifiers = listed.stdout.split()
        self.assertEqual(len(identifiers), 42)
        validated = self.crewloom('validate')
        self.assertEqual(validated.returncode, 0, validated.stderr[-2000:])
        self.assertIn('PASS: 42 skills', validated.stdout)
        for identifier in identifiers:
            shown = self.crewloom('show', identifier)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertIn('name: ' + identifier, shown.stdout)
        unknown = self.crewloom('show', '../outside')
        self.assertEqual(unknown.returncode, 2)
        self.assertNotIn('Traceback', unknown.stderr)

    def test_role_install_preserves_project_memory(self):
        target = self.work / 'installed-project'
        target.mkdir()
        brain = target / '.agents' / 'skills' / 'context-guardian' / 'brain'
        brain.mkdir(parents=True)
        (brain / 'ROADMAP_TODO.md').write_text('# Roadmap\n\n- [ ] local project work\n', encoding='utf-8')
        # A project that already uses a role must not be clobbered by a reinstall, so the
        # existing role is refreshed explicitly. Local memory is never a copied artifact.
        refused = run(self.cli + ['install', '--host', 'agents', '--target', str(target),
                                  '--skill', 'context-guardian'], cwd=self.work)
        self.assertEqual(refused.returncode, 2)
        self.assertIn('--force', refused.stderr)
        result = run(self.cli + ['install', '--host', 'agents', '--target', str(target), '--force'], cwd=self.work)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(len(list((target / '.agents' / 'skills').glob('*/SKILL.md'))), 42)
        self.assertEqual((brain / 'ROADMAP_TODO.md').read_text(encoding='utf-8'),
                         '# Roadmap\n\n- [ ] local project work\n')
        self.assertTrue((brain / 'ARCHITECTURE.md').is_file())
        self.assertFalse(list(target.rglob('__pycache__')))
        references = target / '.agents' / 'skills' / 'context-guardian' / 'references'
        self.assertTrue(references.is_dir(), 'role resources must travel with the role')
        self.assertTrue((references / 'PLAYBOOK.en.md').is_file(), 'role references must be packaged')

    def valid_packet(self):
        return {'title': 'A short article title', 'meta_description': 'm' * 140, 'slug': 'installed-run',
                'canonical': 'https://example.com/installed-run', 'wordcount': 900,
                'internal_links': [{'anchor': 'a', 'target': '/b'}], 'lang': 'en'}

    def test_context_pack_and_registered_tool_run_outside_the_checkout(self):
        pack = self.crewloom('context', 'context-guardian', '--out', 'pack.md')
        self.assertEqual(pack.returncode, 0, pack.stderr)
        text = (self.project / 'pack.md').read_text(encoding='utf-8')
        self.assertIn('# Context pack', text)
        self.assertIn('brain/ARCHITECTURE.md', text)
        arabic = self.crewloom('context', 'context-guardian', '--out', 'pack-ar.md', '--language', 'ar')
        self.assertEqual(arabic.returncode, 0, arabic.stderr)
        self.assertIn('حزمة', (self.project / 'pack-ar.md').read_text(encoding='utf-8'))
        (self.project / 'packet.json').write_text(json.dumps(self.valid_packet()), encoding='utf-8')
        # A valid packet must pass, which proves the installed role script really ran rather
        # than the CLI failing to find it: an unresolvable tool fails with a different message.
        tool = self.crewloom('run', 'seo-packet', '--', '--packet', 'packet.json')
        self.assertNotIn('Traceback', tool.stderr)
        self.assertNotIn('Unknown registered tool', tool.stderr)
        self.assertEqual(tool.returncode, 0, tool.stdout + tool.stderr)
        self.assertIn('PASS', tool.stdout)
        (self.project / 'packet.json').write_text(json.dumps({'title': 'x'}), encoding='utf-8')
        failed = self.crewloom('run', 'seo-packet', '--', '--packet', 'packet.json')
        self.assertEqual(failed.returncode, 2)
        self.assertIn('FAIL', failed.stdout, 'the tool must report its own verdict')
        self.assertFalse((self.project / '.crewloom' / 'runs.jsonl').exists(), 'opt-out must hold')

    def test_project_and_workflow_commands_work_from_the_installation(self):
        doctor = self.crewloom('workflow', 'doctor', '--project', str(self.project))
        report = json.loads(doctor.stdout)
        self.assertIn('python', report)
        self.assertNotIn('Traceback', doctor.stderr)
        # Doctor reports host truth rather than claiming readiness it cannot prove, so its
        # exit code follows Docker availability instead of a fixed expectation.
        self.assertEqual(report['isolated_execution_ready'], bool(report['docker']))
        self.assertEqual(report['isolated_execution_ready'], doctor.returncode == 0)
        reviewer = self.crewloom('reviewer', 'status', '--project', str(self.project))
        self.assertEqual(reviewer.returncode, 0, reviewer.stderr)
        self.assertEqual(json.loads(reviewer.stdout)['review_policy']['mode'], 'label')
        # Entering a real bound project needs an initialized checkout and an installed role,
        # because that is the state the CLI refuses to guess its way past.
        initialized = run(['git', 'init', '-q', '-b', 'main'], cwd=self.project,
                          env=repo_map.git_environment())
        self.assertEqual(initialized.returncode, 0, initialized.stderr[-2000:])
        installed = run(self.cli + ['install', '--host', 'agents', '--target', str(self.project),
                                    '--skill', 'context-guardian'], cwd=self.work)
        self.assertEqual(installed.returncode, 0, installed.stderr[-2000:])
        entered = self.crewloom('project', 'enter', '--project', str(self.project),
                                '--project-id', 'packaged-project', '--task-id', 'packaged-task',
                                '--role', 'context-guardian')
        self.assertEqual(entered.returncode, 0, entered.stdout + entered.stderr)
        self.assertEqual(json.loads(entered.stdout)['status'], 'active')
        status = self.crewloom('project', 'status', '--project', str(self.project))
        self.assertEqual(status.returncode, 0, status.stderr[-2000:])
        self.assertEqual(json.loads(status.stdout)['project_id'], 'packaged-project')
        registered = self.crewloom('reviewer', 'register', '--project', str(self.project),
                                   '--principal', 'packaged-reviewer')
        self.assertEqual(registered.returncode, 0, registered.stderr)
        issued = json.loads(registered.stdout)
        secret = Path(issued['token_file'])
        self.assertTrue(secret.is_file())
        self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('token', issued, 'the issued secret must not reach command output')
        stored = json.loads((self.project / '.crewloom' / 'reviewers.json').read_text(encoding='utf-8'))
        self.assertNotIn(secret.read_text(encoding='utf-8').strip(), json.dumps(stored),
                         'only the token hash may be stored')
        self.assertNotIn('crewloom.reviewers.json', '\n'.join(p.name for p in self.project.iterdir()),
                         'the issuance authority is runtime state, not a trackable project file')

    def test_missing_optional_dashboard_is_diagnosed_not_a_traceback(self):
        result = self.crewloom('dashboard', '--project', str(self.project))
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('Traceback', result.stderr)
        self.assertIn('Node dependencies are not', result.stderr)
        self.assertIn('checkout', result.stderr)
        self.assertNotIn('token', result.stdout.lower(),
                         'the generated secret must never be printed')

    def test_installed_cli_does_not_write_outside_the_selected_project(self):
        escape = self.crewloom('run', 'seo-packet', '--', '--packet', '../escape.json')
        self.assertEqual(escape.returncode, 2)
        self.assertIn('escapes selected project', escape.stderr)

    def test_archives_carry_no_private_runtime_state(self):
        for path in (self.wheel, self.sdist):
            names = zipfile.ZipFile(self.wheel).namelist() if path == self.wheel else tarfile.open(path).getnames()
            with self.subTest(archive=path.name):
                self.assertFalse([name for name in names if 'dashboard-token' in name or 'reviewer-token' in name])
                self.assertFalse([name for name in names if name.endswith('.crewloom/reviewers.json')])


if __name__ == '__main__':
    unittest.main()