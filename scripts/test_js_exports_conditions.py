"""Root ``exports`` condition maps name the package root instead of being refused.

A package whose ``exports`` object is a map of condition names ("types", "import", ...) has no
subpath keys at all: it declares only what the package root resolves to under each condition.
Refusing that shape falls back to a ``main``/``index`` the package never declared, so a
resolvable root import is reported as an unindexed workspace package.
"""
import js_syntax
import repo_map as m
from test_js_syntax import JavaScriptProject

CONDITION_ROOT = '{"types": "./types/index.d.ts", "import": "./src/index.ts"}'
MIXED_ROOT = '{".": "./src/index.ts", "import": "./src/esm.ts"}'
INDEXED = ('src/main.ts', 'packages/core/src/index.ts', 'packages/core/types/index.d.ts',
           'packages/core/src/esm.ts')


class RootConditionMapRegressions(JavaScriptProject):
    def package(self, exports):
        self.write('package.json', '{"name": "root", "workspaces": ["packages/*"]}\n')
        self.write('packages/core/package.json', '{"name": "@app/core", "exports": ' + exports + '}\n')
        self.write('packages/core/src/index.ts', 'export const core = 1;\n')
        self.write('packages/core/src/esm.ts', 'export const core = 1;\n')
        self.write('packages/core/types/index.d.ts', 'export declare const core: number;\n')

    def resolver(self, exports):
        self.package(exports)
        found = js_syntax.Resolver(self.root, ['package.json', 'packages/core/package.json'])
        found.bind(INDEXED)
        return found

    def test_root_condition_map_resolves_the_package_root(self):
        self.package(CONDITION_ROOT)
        self.write('src/main.ts', "import { core } from '@app/core';\n")
        entry = m.build(self.root)[0]['files']['src/main.ts']
        # `types` is the first condition a real resolver considers, so the declaration file it
        # names is the edge this index reports for the package root.
        self.assertEqual(entry['neighbours'], ['packages/core/types/index.d.ts'])
        self.assertEqual(entry['unresolved'], [])
        self.assertNotIn('ts-workspace-package-not-indexed', entry['notes'])

    def test_condition_map_declares_the_root_and_no_subpath(self):
        found = self.resolver(CONDITION_ROOT)
        record = found.packages['@app/core']
        self.assertEqual(found._export_target(record, ''), './types/index.d.ts')
        self.assertEqual(found.resolve('src/main.ts', {'module': '@app/core'}),
                         (['packages/core/types/index.d.ts'], 'resolved'))
        # A subpath is not named by a condition map, so the root target is never reused for one.
        self.assertIsNone(found._export_target(record, './util'))
        self.assertEqual(found.resolve('src/main.ts', {'module': '@app/core/util'}),
                         ([], 'workspace-package-not-indexed'))

    def test_map_mixing_subpaths_and_conditions_stays_refused(self):
        found = self.resolver(MIXED_ROOT)
        record = found.packages['@app/core']
        self.assertIsNone(found._export_target(record, ''))
        self.assertEqual(found.resolve('src/main.ts', {'module': '@app/core'}),
                         ([], 'workspace-package-not-indexed'))


if __name__ == '__main__':
    import unittest
    unittest.main()