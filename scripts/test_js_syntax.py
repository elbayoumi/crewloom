"""Real JS/TS extraction, alias, package and configuration-isolation regressions.

The cases that need the optional `crewloom[syntax]` extra skip without it, and the labelled
fallback is verified in both environments so neither path is left untested.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import js_syntax
import repo_map as m


def git(root, *argv):
    identity = ['-c', 'user.name=Crewloom Fixture', '-c', 'user.email=fixture@example.invalid']
    subprocess.run(['git', *(identity if argv and argv[0] == 'commit' else []), *argv],
                   cwd=root, check=True, capture_output=True, env=m.git_environment())


class JavaScriptProject(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        git(self.root, 'init', '-q')
        git(self.root, 'config', 'user.name', 'Crewloom Fixture')
        git(self.root, 'config', 'user.email', 'fixture@example.invalid')
        (self.root / 'tsconfig.json').write_text('// project alias configuration\n{\n'
                                                 '  "compilerOptions": {\n'
                                                 '    "baseUrl": ".",\n'
                                                 '    "paths": {"@lib/*": ["src/lib/*"],\n'
                                                 '              "exact": ["src/exact.ts"]},\n'
                                                 '  },\n}\n')
        (self.root / 'src' / 'lib').mkdir(parents=True)
        (self.root / 'src' / 'lib' / 'util.ts').write_text('export const helper = () => 1;\n')
        (self.root / 'src' / 'exact.ts').write_text('export const exact = 1;\n')

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path


@unittest.skipUnless(m.JS_GRAMMAR, 'Install the syntax extra for real AST regressions')
class RealSyntaxRegressions(JavaScriptProject):
    def test_only_real_declarations_become_symbols(self):
        self.write('src/fake.ts', '// export function commentGhost() {}\n'
                                   '/* export const blockGhost = 1; */\n'
                                   'const label = "export function stringGhost() {}";\n'
                                   'const template = `\nexport const templateGhost = 1;\n`;\n'
                                   'export const real = 1;\n')
        entry = m.build(self.root)[0]['files']['src/fake.ts']
        names = {item['name'] for item in entry['symbols']}
        self.assertEqual(names, {'label', 'template', 'real'})
        self.assertEqual(entry['parser'], 'ts-ast')

    def test_nested_definitions_arrows_interfaces_and_methods_are_found(self):
        self.write('src/nested.ts', 'export interface Account { name: string }\n'
                                    'export type Id = string;\n'
                                    'export class Store {\n'
                                    '  private field = () => 1;\n'
                                    '  save(name: string) { return name; }\n'
                                    '  static make() { return new Store(); }\n'
                                    '}\n'
                                    'export function outer() {\n'
                                    '  function inner() { return 2; }\n'
                                    '  return inner();\n'
                                    '}\n')
        entry = m.build(self.root)[0]['files']['src/nested.ts']
        found = {(item['name'], item['kind']) for item in entry['symbols']}
        self.assertTrue({('Account', 'interface'), ('Id', 'type'), ('Store', 'class'),
                         ('save', 'method'), ('make', 'method'), ('field', 'arrow'),
                         ('outer', 'function'), ('inner', 'function')} <= found, found)
        # A nested definition keeps its own real line range.
        inner = next(item for item in entry['symbols'] if item['name'] == 'inner')
        self.assertEqual(inner['line'], 9)

    def test_syntax_error_stays_visible_as_incomplete(self):
        self.write('src/broken.ts', 'export const ok = 1;\nexport function bad( {\n')
        value, _ = m.build(self.root)
        entry = value['files']['src/broken.ts']
        self.assertIn('ts-syntax-error-partial', entry['notes'])
        self.assertFalse(entry['complete'])
        self.assertIn('src/broken.ts', value['incomplete_files'])
        self.assertEqual({item['name'] for item in entry['symbols']}, {'ok'})

    def test_symbol_and_import_truncation_caps_still_apply(self):
        self.write('src/wide.ts', ''.join('export const symbol_%d = %d;\n' % (index, index)
                                          for index in range(m.MAX_SYMBOLS + 20)))
        entry = m.build(self.root)[0]['files']['src/wide.ts']
        self.assertEqual(len(entry['symbols']), m.MAX_SYMBOLS)
        self.assertEqual(entry['symbols_truncated'], 20)

    def test_paths_alias_barrel_reexport_and_dynamic_import(self):
        self.write('src/main.ts', "import { helper } from '@lib/util';\n"
                                  "import { exact } from 'exact';\n"
                                  "export { helper } from './lib/util';\n"
                                  "const lazy = () => import('./lib/util');\n"
                                  "const legacy = require('left-pad');\n"
                                  "export const main = () => helper() + exact + lazy() + legacy;\n")
        value, _ = m.build(self.root)
        entry = value['files']['src/main.ts']
        self.assertEqual(entry['neighbours'], ['src/exact.ts', 'src/lib/util.ts'])
        self.assertIn('ts-dynamic-import-resolved:./lib/util', entry['notes'])
        self.assertEqual(entry['external'], ['left-pad'])
        self.assertIn('left-pad', entry['unresolved'])
        self.assertFalse(value['graph_complete'])

    def test_ambiguous_alias_reports_every_matching_project_file(self):
        self.write('tsconfig.second.json', '')
        self.write('src/one/util.ts', 'export const helper = 1;\n')
        self.write('src/main.ts', "import { helper } from '@lib/util';\n")
        self.write('extra.tsconfig.json', '{"compilerOptions": {"paths": {"@lib/*": ["src/one/*"]}}}\n')
        self.root.joinpath('tsconfig.json').write_text(
            '{"extends": "./extra.tsconfig.json", "compilerOptions": {"baseUrl": ".",'
            ' "paths": {"@lib/*": ["src/lib/*"]}}}\n')
        entry = m.build(self.root)[0]['files']['src/main.ts']
        self.assertEqual(entry['neighbours'], ['src/lib/util.ts', 'src/one/util.ts'])
        self.assertIn('ts-alias-ambiguous:@lib/util', entry['notes'])

    def test_workspace_local_package_resolves_through_declared_exports(self):
        self.write('package.json', '{"name": "root", "workspaces": ["packages/*"]}\n')
        self.write('packages/core/package.json', '{"name": "@app/core",'
                                                 ' "exports": {".": "./src/index.ts", "./util": {"types": "./src/util.ts"}}}\n')
        self.write('packages/core/src/index.ts', 'export const core = 1;\n')
        self.write('packages/core/src/util.ts', 'export const helper = 2;\n')
        self.write('src/main.ts', "import { core } from '@app/core';\n"
                                  "import { helper } from '@app/core/util';\n"
                                  "import { missing } from '@app/core/absent';\n")
        entry = m.build(self.root)[0]['files']['src/main.ts']
        self.assertEqual(entry['neighbours'], ['packages/core/src/index.ts', 'packages/core/src/util.ts'])
        self.assertIn('ts-workspace-package-not-indexed', entry['notes'])
        self.assertIn('@app/core/absent', entry['unresolved'])

    def test_circular_imports_resolve_without_looping(self):
        self.write('src/left.ts', "import { right } from './right';\nexport const left = 1;\n")
        self.write('src/right.ts', "import { left } from './left';\nexport const right = left;\n")
        value, _ = m.build(self.root)
        self.assertEqual(value['files']['src/left.ts']['neighbours'], ['src/right.ts'])
        self.assertEqual(value['files']['src/right.ts']['neighbours'], ['src/left.ts'])
        self.assertTrue(value['graph_complete'])

    def test_inherited_alias_configuration_applies(self):
        self.write('base.tsconfig.json', '{\n  // shared aliases\n'
                                         '  "compilerOptions": {"baseUrl": ".", "paths": {"@lib/*": ["src/lib/*"]}},\n}\n')
        self.root.joinpath('tsconfig.json').write_text('{"extends": "./base.tsconfig.json"}\n')
        self.write('src/main.ts', "import { helper } from '@lib/util';\n")
        entry = m.build(self.root)[0]['files']['src/main.ts']
        self.assertEqual(entry['neighbours'], ['src/lib/util.ts'])

    def test_configuration_digest_tracks_configuration_not_sources(self):
        first = m.build(self.root)[0]
        self.write('src/extra.ts', 'export const extra = 1;\n')
        second = m.build(self.root)[0]
        self.assertEqual(first['config_sha256'], second['config_sha256'])
        self.write('tsconfig.json', self.root.joinpath('tsconfig.json').read_text().replace(
            'src/lib/*', 'src/other/*'))
        third = m.build(self.root)[0]
        self.assertNotEqual(second['config_sha256'], third['config_sha256'])

    def test_symlinked_configuration_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory).resolve() / 'foreign.json'
            foreign.write_text('{"compilerOptions": {"baseUrl": "."}}')
            (self.root / 'linked.json').symlink_to(foreign)
            self.root.joinpath('tsconfig.json').write_text('{"extends": "./linked.json"}\n')
            with self.assertRaises(ValueError):
                m.build(self.root)

    def test_escaping_absolute_specifier_is_refused_and_reported(self):
        self.write('src/main.ts', "import { helper } from '/etc/passwd';\n")
        entry = m.build(self.root)[0]['files']['src/main.ts']
        self.assertEqual(entry['neighbours'], [])
        self.assertIn('ts-resolution-refused:/etc/passwd', entry['notes'])


class FallbackRegressions(JavaScriptProject):
    """The labelled approximate extractor stays honest when the extra is absent."""

    def test_fallback_is_labelled_approximate_without_the_extra(self):
        self.write('src/app.ts', "import { helper } from '@lib/util';\nexport const app = () => helper;\n")
        with patch.object(m, 'JS_GRAMMAR', False):
            value, stats = m.build(self.root)
        entry = value['files']['src/app.ts']
        self.assertEqual(entry['parser'], 'approximate-js-ts')
        self.assertIn('js-ts-symbols-approximate-no-tree-sitter', value['unsupported'])
        self.assertFalse(value['syntax']['available'])
        self.assertEqual(stats['syntax'], 'approximate-js-ts')
        # Alias resolution does not depend on the grammar, so the edge is still real.
        self.assertEqual(entry['neighbours'], ['src/lib/util.ts'])

    def test_real_extraction_is_used_when_the_extra_is_installed(self):
        if not m.JS_GRAMMAR:
            self.skipTest('the syntax extra is not installed in this environment')
        self.write('src/app.ts', 'export const app = () => 1;\n')
        value, _ = m.build(self.root)
        self.assertEqual(value['files']['src/app.ts']['parser'], 'ts-ast')
        self.assertTrue(value['syntax']['available'])
        self.assertEqual(sorted(value['syntax']['packages']), sorted(js_syntax.PACKAGES))
        self.assertEqual(value['syntax']['revision'], js_syntax.revision())

    def test_configuration_isolation_applies_without_the_extra(self):
        self.write('src/app.ts', 'export const app = 1;\n')
        self.root.joinpath('tsconfig.json').write_text('{"extends": "./tsconfig.child.json"}\n')
        self.write('tsconfig.child.json', '{"extends": "./tsconfig.json"}\n')
        with patch.object(m, 'JS_GRAMMAR', False), self.assertRaises(ValueError):
            m.build(self.root)


class JsoncReaderRegressions(unittest.TestCase):
    def test_comments_and_trailing_commas_are_accepted_outside_strings_only(self):
        value = json.loads(js_syntax._strip_comments(
            '// leading\n{"a": "http://not-a-comment", /* inline */ "b": [1, 2,],\n}'))
        self.assertEqual(value, {'a': 'http://not-a-comment', 'b': [1, 2]})
        # A block-comment opener inside a string is string content, so the reader preserves it
        # rather than swallowing the rest of the file; an opener outside a string is a comment
        # and an unterminated one is refused where it is found.
        self.assertEqual(js_syntax._strip_comments('{"a": "/* not a comment"}'),
                         '{"a": "/* not a comment"}')
        with self.assertRaises(ValueError):
            js_syntax._strip_comments('{"a": 1, /* unterminated')
        with self.assertRaises(ValueError):
            json.loads(js_syntax._strip_comments('{"a": "/* unterminated'))


if __name__ == '__main__':
    unittest.main()