"""Distribution contract: declared packaging, resolved resources, and archive exclusions."""
import glob
import json
import os
import sys
import unittest
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10 have no TOML reader in the standard library
    tomllib = None

import crewloom_resources as resources
from crewloom_resources import ResourceError

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / 'pyproject.toml'
MANIFEST = ROOT / 'MANIFEST.in'
FORBIDDEN_TREES = ('.crewloom', 'node_modules', '.next', '__pycache__', 'build', 'dist')
LICENSES = ('LICENSE', 'NOTICE')


def pyproject():
    if tomllib is None:
        raise unittest.SkipTest('tomllib needs Python 3.11 or newer')
    with PYPROJECT.open('rb') as handle:
        return tomllib.load(handle)


def matched_files(patterns):
    """Reproduce exactly which files setuptools' package_data globs select from the repository."""
    found = set()
    for pattern in patterns:
        for name in glob.glob(pattern, root_dir=str(ROOT), recursive=True):
            path = ROOT / name
            if path.is_file():
                found.add(name)
    return found


def declared_files(directory, skip=()):
    out = set()
    for path in (ROOT / directory).rglob('*'):
        if not path.is_file() or any(part in skip for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix == '.pyc' or path.suffix == '.pyo' or '__pycache__' in path.parts:
            continue
        out.add(path.relative_to(ROOT).as_posix())
    return out


class DistributionMetadata(unittest.TestCase):
    def test_version_is_development_metadata_and_claims_no_tag(self):
        version = pyproject()['project']['version']
        self.assertTrue(version.startswith('0.6.0'), version)
        self.assertIn('dev', version.split('0.6.0')[-1], 'A development build must not look like a release tag')

    def test_declared_license_notice_and_english_docs(self):
        project = pyproject()['project']
        self.assertEqual(project['license'], 'Apache-2.0')
        self.assertEqual(tuple(project['license-files']), LICENSES)
        for name in LICENSES + ('README.md', 'README.ar.md'):
            self.assertTrue((ROOT / name).is_file(), name)

    def test_build_backend_is_pinned_to_a_declared_range(self):
        build = pyproject()['build-system']
        self.assertEqual(build['build-backend'], 'setuptools.build_meta')
        requirement = build['requires']
        self.assertEqual(len(requirement), 1, requirement)
        self.assertRegex(requirement[0], r'^setuptools>=\d+,\s*<\d+$')

    def test_roles_and_documentation_are_packaged_once_from_their_repository_location(self):
        config = pyproject()['tool']['setuptools']
        self.assertEqual(config['package-dir'][''], 'scripts')
        self.assertEqual(config['package-dir']['crewloom_data'], '.')
        # Installed roles must keep the depth they have in a checkout, so a role script that
        # climbs four levels above itself still finds `.agents/skills` beside its installation.
        self.assertEqual(resources.roles_dir().relative_to(resources.distribution_root()),
                         resources.ROLES_DIRECTORY)
        self.assertEqual(len(resources.role_ids()), 42)

    def test_every_flat_runtime_module_is_declared_and_exists(self):
        modules = pyproject()['tool']['setuptools']['py-modules']
        self.assertEqual(len(modules), len(set(modules)), 'A runtime module is declared twice')
        missing = [name for name in modules if not (ROOT / 'scripts' / (name + '.py')).is_file()]
        self.assertEqual(missing, [], 'Declared runtime modules without a source: ' + ', '.join(missing))
        # `repo_map` imports `js_syntax` at module scope, so an installed map needs it present
        # even where the optional grammars are not: it falls back and reports the fallback.
        self.assertIn('js_syntax', modules)
        self.assertIn('execution_policy', modules)

    def test_the_optional_syntax_extra_pins_the_verified_grammar_versions(self):
        project = pyproject()['project']
        self.assertEqual(project['dependencies'], [], 'The core toolkit must stay dependency free')
        extra = project.get('optional-dependencies', {}).get('syntax')
        self.assertEqual(sorted(extra or []), ['tree-sitter-javascript==0.23.1',
                                               'tree-sitter-typescript==0.23.2',
                                               'tree-sitter==0.23.2'])
        for requirement in extra:
            self.assertRegex(requirement, r'^[a-z0-9-]+==[0-9]+\.[0-9]+\.[0-9]+$')


class PackagedDataRegressions(unittest.TestCase):
    def test_every_role_resource_is_covered_by_a_declared_pattern(self):
        patterns = pyproject()['tool']['setuptools']['package-data']['crewloom_data']
        selected = matched_files(patterns)
        missing = declared_files('.agents/skills') - selected
        self.assertEqual(missing, set(), 'Role resources missing from package-data: ' + ', '.join(sorted(missing)))

    def test_every_documentation_file_and_public_asset_is_covered(self):
        patterns = pyproject()['tool']['setuptools']['package-data']['crewloom_data']
        selected = matched_files(patterns)
        missing = (declared_files('documentation') | declared_files('assets', skip=('dashboard-demo.mp4', 'dashboard-demo.gif'))) - selected
        self.assertEqual(missing, set(), 'Documentation or public assets missing: ' + ', '.join(sorted(missing)))

    def test_runtime_registry_and_optional_node_assets_are_declared_separately(self):
        patterns = pyproject()['tool']['setuptools']['package-data']['crewloom_data']
        selected = matched_files(patterns)
        self.assertIn('documentation/TOOLS.json', selected)
        # Node assets are deliberately absent from the wheel; `crewloom dashboard` diagnoses that.
        self.assertFalse([name for name in selected if name.startswith('dashboard/')])
        self.assertEqual([name for name in selected if name.startswith('assets/')], ['assets/crewloom-banner.svg'])


class ResourceResolverRegressions(unittest.TestCase):
    def test_resolver_maps_every_registered_namespace(self):
        self.assertTrue((ROOT / 'pyproject.toml').is_file())
        self.assertTrue(resources.resolve('scripts/crewloom.py').is_file())
        self.assertTrue(resources.resolve('.agents/skills/context-guardian/SKILL.md').is_file())
        self.assertTrue(resources.resolve('documentation/TOOLS.json').is_file())
        self.assertEqual(resources.module_file('execution_policy.py'), resources.MODULE_DIR / 'execution_policy.py')

    def test_every_registered_tool_resolves_inside_the_installation(self):
        registry = json.loads(resources.require('documentation/TOOLS.json').read_text(encoding='utf-8'))['tools']
        roots = [root.resolve() for root in resources.installed_roots()]
        self.assertTrue(registry)
        for item in registry:
            path = resources.resolve(item['path']).resolve()
            with self.subTest(tool=item['id']):
                self.assertTrue(path.is_file(), item['path'])
                self.assertTrue(any(root == path or root in path.parents for root in roots), item['path'])

    def test_escaping_and_unknown_lookups_are_refused(self):
        for value in ('../outside.md', '/etc/passwd', 'scripts/../../outside', ''):
            with self.subTest(value=value), self.assertRaises(ResourceError):
                resources.resolve(value)
        with self.assertRaisesRegex(ResourceError, 'not part of this installation'):
            resources.require('documentation/ABSENT.md')
        with self.assertRaisesRegex(ResourceError, 'not part of this installation'):
            resources.role_dir('absent-role')

    def test_installed_distribution_does_not_claim_a_dashboard(self):
        self.assertTrue(resources.dashboard_dir().is_dir())
        original = resources._source_root
        resources._source_root = lambda: None
        try:
            with self.assertRaisesRegex(ResourceError, 'Node dependencies are not'):
                resources.dashboard_dir()
        finally:
            resources._source_root = original

    def test_missing_resources_fail_with_a_diagnostic_not_a_traceback(self):
        original_source, original_packaged = resources._source_root, resources._packaged_root
        resources._source_root = resources._packaged_root = lambda: None
        try:
            for call in (resources.distribution_root, resources.roles_dir, resources.role_ids,
                         resources.documentation_dir, resources.source_checkout):
                with self.subTest(call=call.__name__), self.assertRaisesRegex(ResourceError, 'unavailable'):
                    call()
        finally:
            resources._source_root, resources._packaged_root = original_source, original_packaged


class ArchiveExclusionRegressions(unittest.TestCase):
    def manifest(self):
        return MANIFEST.read_text(encoding='utf-8')

    def test_forbidden_trees_are_excluded_from_the_sdist(self):
        text = self.manifest()
        for tree in FORBIDDEN_TREES:
            with self.subTest(tree=tree):
                self.assertTrue(any(tree in line for line in text.splitlines()), tree)
        for line in text.splitlines():
            self.assertNotRegex(line.strip(), r'^recursive-include\s+\.crewloom')

    def test_client_records_and_logs_are_not_declared_in_the_sdist(self):
        self.assertNotIn('runs.jsonl', self.manifest())
        self.assertNotIn('events.jsonl', self.manifest())
        self.assertRegex(self.manifest(), r'global-exclude.*\.log')

    def test_sdist_keeps_the_source_layout_so_a_checkout_runs_from_the_archive(self):
        text = self.manifest()
        for line in ('recursive-include .agents *.md *.py', 'recursive-include scripts *.py',
                     'recursive-include documentation *.md *.json *.txt'):
            self.assertIn(line, text)


if __name__ == '__main__':
    unittest.main()