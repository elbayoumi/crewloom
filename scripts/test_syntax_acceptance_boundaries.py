"""Independent real-AST navigation and configuration-isolation acceptance."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import repo_map as mapping


HAS_SYNTAX = all(importlib.util.find_spec(name) for name in (
    'tree_sitter', 'tree_sitter_javascript', 'tree_sitter_typescript'))


@unittest.skipUnless(HAS_SYNTAX, 'Install the syntax extra to run real AST acceptance')
class SyntaxNavigationBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, env=mapping.git_environment(), check=True)
        (self.root / 'src' / 'left').mkdir(parents=True)
        (self.root / 'src' / 'right').mkdir()
        (self.root / 'src' / 'left' / 'util.ts').write_text('export const helper = () => 1;\n')
        (self.root / 'src' / 'right' / 'util.ts').write_text('export const helper = () => 2;\n')

    def configure(self, target):
        value = json.dumps({
            'compilerOptions': {'baseUrl': '.', 'paths': {'@tools/*': [target + '/*']}}}, indent=2)
        (self.root / 'tsconfig.json').write_text('// project-local alias configuration\n' + value[:-1] + ',\n}\n')

    def test_ast_ignores_fake_declarations_and_finds_arrows_interfaces_methods(self):
        (self.root / 'src' / 'main.ts').write_text(
            '// export function commentGhost() {}\n'
            'const label = "function stringGhost() {}";\n'
            'const template = `\nexport function stringGhost() {}\n`;\n'
            'export interface Account { name: string; }\n'
            'export const makeAccount = (name: string) => ({ name });\n'
            'export class Store { save(name: string) { return makeAccount(name); } }\n')
        value, _ = mapping.build(self.root)
        entry = value['files']['src/main.ts']
        self.assertNotIn('approximate', entry['parser'])
        names = {item['name'] for item in entry['symbols']}
        self.assertTrue({'Account', 'makeAccount', 'Store', 'save'} <= names, names)
        self.assertNotIn('commentGhost', names)
        self.assertNotIn('stringGhost', names)

    def test_alias_and_barrel_reexport_have_real_project_neighbours(self):
        self.configure('src/left')
        (self.root / 'src' / 'main.ts').write_text("import { helper } from '@tools/util';\nexport const main = () => helper();\n")
        (self.root / 'src' / 'barrel.ts').write_text("export { helper } from './left/util';\n")
        value, _ = mapping.build(self.root)
        self.assertIn('src/left/util.ts', value['files']['src/main.ts']['neighbours'])
        self.assertIn('src/left/util.ts', value['files']['src/barrel.ts']['neighbours'])

    def test_alias_config_change_refreshes_edges_of_unchanged_source(self):
        self.configure('src/left')
        (self.root / 'src' / 'main.ts').write_text("import { helper } from '@tools/util';\nexport const main = () => helper();\n")
        first, _ = mapping.build(self.root)
        self.configure('src/right')
        second, _ = mapping.build(self.root)
        self.assertEqual(first['files']['src/main.ts']['sha256'], second['files']['src/main.ts']['sha256'])
        self.assertIn('src/left/util.ts', first['files']['src/main.ts']['neighbours'])
        self.assertIn('src/right/util.ts', second['files']['src/main.ts']['neighbours'])
        self.assertNotIn('src/left/util.ts', second['files']['src/main.ts']['neighbours'])

    def test_warm_ast_cache_reuses_unchanged_parses(self):
        mapping.build(self.root)
        _, stats = mapping.build(self.root)
        self.assertEqual(stats['parsed'], 0)
        self.assertEqual(stats['reused'], 2)

    def test_tsconfig_extends_cannot_escape_project_even_to_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory).resolve() / 'foreign.json'
            foreign.write_text('{"compilerOptions":{"baseUrl":"."}}')
            (self.root / 'tsconfig.json').write_text(json.dumps({'extends': str(foreign)}))
            with self.assertRaises(ValueError):
                mapping.build(self.root)
            self.assertFalse((self.root / '.crewloom' / 'index' / 'map.json').exists())

    def test_circular_tsconfig_extends_fails_closed(self):
        (self.root / 'tsconfig.json').write_text('{"extends":"./tsconfig.child.json"}')
        (self.root / 'tsconfig.child.json').write_text('{"extends":"./tsconfig.json"}')
        with self.assertRaises(ValueError):
            mapping.build(self.root)

    def test_alias_base_url_cannot_point_outside_the_project(self):
        (self.root / 'tsconfig.json').write_text(json.dumps({
            'compilerOptions': {'baseUrl': '..', 'paths': {'@tools/*': ['*']}}}))
        with self.assertRaises(ValueError):
            mapping.build(self.root)
        self.assertFalse((self.root / '.crewloom' / 'index' / 'map.json').exists())

    def test_declared_alias_target_cannot_escape_the_project(self):
        (self.root / 'tsconfig.json').write_text(json.dumps({
            'compilerOptions': {'baseUrl': '.', 'paths': {'@tools/*': ['../foreign/*']}}}))
        (self.root / 'src' / 'main.ts').write_text("import { helper } from '@tools/util';\n")
        with self.assertRaises(ValueError):
            mapping.build(self.root)
        self.assertFalse((self.root / '.crewloom' / 'index' / 'map.json').exists())

    def test_tsconfig_cannot_extend_protected_runtime_state(self):
        private = self.root / '.crewloom'
        private.mkdir()
        authority = private / 'reviewers.json'
        authority.write_text('{"compilerOptions":{"baseUrl":"."},"private_fixture":true}')
        authority.chmod(0o600)
        (self.root / 'tsconfig.json').write_text('{"extends":"./.crewloom/reviewers.json"}')
        with self.assertRaises(ValueError):
            mapping.build(self.root)
        self.assertFalse((private / 'index' / 'map.json').exists())
        self.assertEqual(authority.read_text(), '{"compilerOptions":{"baseUrl":"."},"private_fixture":true}')


if __name__ == '__main__':
    unittest.main()
