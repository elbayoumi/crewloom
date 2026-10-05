"""Independent map quality checks for parse errors and unsupported module calls."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

import repo_map as mapping


HAS_SYNTAX = all(importlib.util.find_spec(name) for name in (
    'tree_sitter', 'tree_sitter_javascript', 'tree_sitter_typescript'))


@unittest.skipUnless(HAS_SYNTAX, 'Install the syntax extra for AST quality checks')
class SyntaxQualityBoundaries(unittest.TestCase):
    def map_for(self, source):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=root,
                       env=mapping.git_environment(), check=True)
        (root / 'main.ts').write_text(source)
        value, _ = mapping.build(root)
        return value

    def test_syntax_errors_cannot_be_reported_as_a_complete_graph(self):
        value = self.map_for('export const broken = =>;\n')
        self.assertFalse(value['files']['main.ts']['complete'])
        self.assertIn('main.ts', value['incomplete_files'])
        self.assertFalse(value['graph_complete'])

    def test_ordinary_function_calls_are_not_unresolved_module_calls(self):
        value = self.map_for('export function calculate(x: number) { return Math.abs(x); }\n')
        notes = value['files']['main.ts']['notes']
        self.assertFalse(any('indirect-module' in note for note in notes), notes)
        self.assertTrue(value['graph_complete'])

    def test_nonliteral_dynamic_import_is_explicitly_incomplete(self):
        value = self.map_for('export async function load(name: string) { return import(name); }\n')
        self.assertFalse(value['graph_complete'])
        self.assertTrue(value['files']['main.ts']['notes'])


if __name__ == '__main__':
    unittest.main()
