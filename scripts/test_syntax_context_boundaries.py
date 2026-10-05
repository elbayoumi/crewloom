"""Independent frozen-context checks for mutable module resolution configuration."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import crewloom
import project_binding as binding
import project_context as context
import repo_map


HAS_SYNTAX = all(importlib.util.find_spec(name) for name in (
    'tree_sitter', 'tree_sitter_javascript', 'tree_sitter_typescript'))


@unittest.skipUnless(HAS_SYNTAX, 'Install the syntax extra for resolution context checks')
class SyntaxContextBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root,
                       env=repo_map.git_environment(), check=True)
        _, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        self.assertEqual(errors, [])
        for side in ('left', 'right'):
            (self.root / 'src' / side).mkdir(parents=True)
            (self.root / 'src' / side / 'util.ts').write_text('export const helper = () => 1;\n')
        (self.root / 'src' / 'main.ts').write_text(
            "import { helper } from '@tools/util';\nexport const main = () => helper();\n")
        (self.root / 'ACCEPTANCE.md').write_text('- main uses the configured project-local helper\n')
        (self.root / 'AGENTS.md').write_text('# Project rules\nPreserve scope.\n')
        config = binding.default_config('alias-freshness', 'enforced')
        config['source_roots'] = ['src']
        (self.root / binding.CONFIG_NAME).write_text(json.dumps(config))
        self.configure('src/left')

    def configure(self, target):
        (self.root / 'tsconfig.json').write_text(json.dumps({
            'compilerOptions': {'baseUrl': '.', 'paths': {'@tools/*': [target + '/*']}}}))

    def enter(self):
        return binding.enter(self.root, 'alias-freshness', 'alias-change', 'context-guardian',
                             seeds=['src/main.ts'], sources=['src/main.ts'],
                             criteria_path='ACCEPTANCE.md')['context']

    def test_alias_change_blocks_publication_against_the_old_frozen_context(self):
        self.enter()
        local = binding.load_binding(self.root)
        context.require_fresh(self.root, local, 'alias-change')
        self.configure('src/right')
        with self.assertRaises(ValueError):
            context.require_fresh(self.root, local, 'alias-change')

    def test_reentry_after_alias_change_refreshes_the_semantic_generation(self):
        first = self.enter()
        source_before = (self.root / 'src' / 'main.ts').read_bytes()
        self.configure('src/right')
        second = self.enter()
        self.assertEqual((self.root / 'src' / 'main.ts').read_bytes(), source_before)
        self.assertGreater(second['generation'], first['generation'])
        self.assertNotEqual(second['semantic_sha256'], first['semantic_sha256'])
        context.require_fresh(self.root, binding.load_binding(self.root), 'alias-change')


if __name__ == '__main__':
    unittest.main()
