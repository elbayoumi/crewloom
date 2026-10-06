"""R01/R08: the running Crewloom identifies its version, resolved roots, revision and source/wheel state."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import test_packaging as packaging

SCRIPTS = Path(__file__).resolve().parent
REPORT = ('import json, crewloom_resources as r; print(json.dumps(r.source_identity()))')


def git(root, *argv):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    return subprocess.run(['git', '-C', str(root), '-c', 'user.name=F', '-c', 'user.email=f@example.invalid',
                           *argv], env=env, check=True, capture_output=True, text=True, timeout=30).stdout


def identity(code_dir, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env['PYTHONPATH'] = str(code_dir)
    result = subprocess.run([sys.executable, '-c', REPORT], cwd=str(cwd), env=env, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


class SourceIdentity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-identity-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.elsewhere = self.base / 'unrelated-cwd'
        self.elsewhere.mkdir()

    def checkout(self, version='1.2.3'):
        root = self.base / 'checkout'
        (root / 'scripts').mkdir(parents=True)
        (root / '.agents/skills/stub').mkdir(parents=True)
        (root / '.agents/skills/stub/SKILL.md').write_text('stub\n', encoding='utf-8')
        (root / 'pyproject.toml').write_text('[project]\nname = "crewloom"\nversion = "%s"\n' % version, encoding='utf-8')
        shutil.copyfile(SCRIPTS / 'crewloom_resources.py', root / 'scripts/crewloom_resources.py')
        git(root, 'init', '-q')
        git(root, 'add', '--', '.')
        git(root, 'commit', '-qm', 'fixture')
        return root

    def test_checkout_reports_roots_revision_and_exact_dirty_count_from_any_directory(self):
        root = self.checkout()
        clean = identity(root / 'scripts', self.elsewhere)
        self.assertEqual(clean['layout'], 'source-checkout')
        self.assertEqual(clean['code_root'], str(root / 'scripts'))
        self.assertEqual(clean['resource_root'], str(root))
        self.assertEqual(clean['revision'], git(root, 'rev-parse', 'HEAD').strip())
        self.assertEqual(clean['declared_version'], '1.2.3')
        self.assertEqual(clean['dirty_paths'], 0)
        (root / 'scripts/extra.py').write_text('x = 1\n', encoding='utf-8')
        (root / 'pyproject.toml').write_text('[project]\nversion = "1.2.3"\n# edited\n', encoding='utf-8')
        self.assertEqual(identity(root / 'scripts', self.elsewhere)['dirty_paths'], 2)

    def test_installed_metadata_that_disagrees_with_the_source_is_visible(self):
        root = self.checkout('1.2.3')
        stale = root / 'scripts/crewloom-0.0.1.dist-info'
        stale.mkdir()
        (stale / 'METADATA').write_text('Metadata-Version: 2.1\nName: crewloom\nVersion: 0.0.1\n', encoding='utf-8')
        report = identity(root / 'scripts', self.elsewhere)
        self.assertEqual((report['distribution_version'], report['declared_version']), ('0.0.1', '1.2.3'))
        self.assertIs(report['versions_agree'], False)
        self.assertTrue(report['metadata_beside_checkout_code'])

    def test_missing_facts_are_unknown_not_guessed(self):
        root = self.checkout()
        shutil.rmtree(root / '.git')
        report = identity(root / 'scripts', self.elsewhere)
        for name in ('revision', 'dirty_paths', 'distribution_version', 'editable_install'):
            self.assertIsNone(report[name], name)
            self.assertIn(name, report['unknown'])
        self.assertIsNone(report['versions_agree'])

    def test_installed_wheel_layout_has_no_revision_or_dirty_claim(self):
        python, version = packaging.RealArchiveCanaries.builder()
        if python is None:
            self.skipTest('no setuptools builder inside the declared range')
        import zipfile
        wheel_dir = self.base / 'wheel'
        wheel_dir.mkdir()
        built = subprocess.run([python, '-c', 'import setuptools.build_meta as b,sys;print(b.build_wheel(sys.argv[1]))',
                                str(wheel_dir)], cwd=str(SCRIPTS.parent), capture_output=True, text=True, timeout=300)
        self.assertEqual(built.returncode, 0, built.stderr[-500:])
        installed = self.base / 'site'
        with zipfile.ZipFile(wheel_dir / built.stdout.strip().splitlines()[-1]) as archive:
            archive.extractall(installed)
        report = identity(installed, self.elsewhere)
        self.assertEqual(report['layout'], 'installed-data')
        self.assertEqual(report['resource_root'], str(installed / 'crewloom_data'))
        self.assertEqual(report['code_root'], str(installed))
        self.assertIsNone(report['revision'])
        self.assertIsNone(report['dirty_paths'])
        self.assertEqual(report['distribution_version'], packaging.pyproject()['project']['version'])
        self.assertFalse(report['metadata_beside_checkout_code'])

    def test_the_cli_prints_the_same_facts(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        result = subprocess.run([sys.executable, str(SCRIPTS / 'crewloom.py'), 'source', '--json'],
                                cwd=str(self.elsewhere), env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['resource_root'], str(SCRIPTS.parent))
        self.assertEqual(report['declared_version'], packaging.pyproject()['project']['version'])
        text = subprocess.run([sys.executable, str(SCRIPTS / 'crewloom.py'), 'source'], cwd=str(self.elsewhere),
                              env=env, capture_output=True, text=True, timeout=60).stdout
        self.assertIn('revision', text)


if __name__ == '__main__':
    unittest.main()
