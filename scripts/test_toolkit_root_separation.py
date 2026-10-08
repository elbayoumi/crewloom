"""N01: applications keep their own roots; the toolkit installation is never an application workspace."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import crewloom
import crewloom_resources
import project_binding as binding
import repo_map

TOOLKIT = crewloom_resources.distribution_root().resolve()
SCRIPT = TOOLKIT / 'scripts' / 'project_binding.py'


def run_cli(project, *extra, cwd):
    """Run the shipped CLI from an unrelated working directory with absolute paths only."""
    result = subprocess.run([sys.executable, str(SCRIPT), 'enter', '--project', str(project), '--project-id',
                             extra[0], '--task-id', 'task-1', '--role', 'context-guardian', '--seed', 'app.py'],
                            cwd=str(cwd), env=repo_map.git_environment(), capture_output=True, text=True, timeout=60)
    return result.returncode, (json.loads(result.stdout) if result.stdout.strip().startswith('{') else {})


class ToolkitRootSeparation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-roots-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.elsewhere = self.base / 'unrelated-cwd'
        self.elsewhere.mkdir()

    def application(self, group):
        root = self.base / group / 'shop'
        root.mkdir(parents=True)
        subprocess.run(['git', '-C', str(root), 'init', '-q'], env=repo_map.git_environment(), check=True, timeout=20)
        (root / 'app.py').write_text('def checkout():\n    return 1\n', encoding='utf-8')
        _, errors = crewloom.install_skills(root, 'agents', ['context-guardian'], False)
        self.assertEqual(errors, [])
        return root

    def test_a_root_inside_the_toolkit_is_refused_before_any_write(self):
        before = sorted(p.name for p in (TOOLKIT / 'examples').iterdir())
        with self.assertRaisesRegex(ValueError, 'trusted Crewloom runtime'):
            binding.project_root(TOOLKIT / 'examples')
        code, out = run_cli(TOOLKIT / 'examples', 'shop', cwd=self.elsewhere)
        self.assertNotEqual(code, 0)
        self.assertEqual(out.get('status'), 'rejected')
        self.assertEqual(sorted(p.name for p in (TOOLKIT / 'examples').iterdir()), before)
        self.assertFalse((TOOLKIT / 'examples' / '.crewloom').exists())

    def test_a_symlink_into_the_toolkit_resolves_and_is_refused(self):
        link = self.base / 'innocent-name'
        os.symlink(TOOLKIT / 'documentation', link)
        with self.assertRaisesRegex(ValueError, 'trusted Crewloom runtime'):
            binding.project_root(link)
        code, out = run_cli(link, 'shop', cwd=self.elsewhere)
        self.assertEqual((code != 0, out.get('status')), (True, 'rejected'))

    def test_similarly_named_applications_bind_independently_from_an_unrelated_directory(self):
        roots = [self.application('a'), self.application('b')]
        outcomes = [run_cli(root, 'shop', cwd=self.elsewhere) for root in roots]
        self.assertEqual([code for code, _ in outcomes], [0, 0], outcomes)
        bindings = [json.loads((root / '.crewloom' / 'binding.json').read_text()) for root in roots]
        self.assertEqual([b['project_root'] for b in bindings], [str(root) for root in roots])
        self.assertNotEqual(bindings[0]['checkout_id'], bindings[1]['checkout_id'])
        for root in roots:  # runtime state stays in each application's own ignored namespace
            self.assertTrue((root / '.crewloom').is_dir())
        self.assertFalse((TOOLKIT / '.crewloom' / 'tasks' / 'task-1').exists())
        self.assertEqual(sorted(p.name for p in self.elsewhere.iterdir()), [], 'cwd is never used as a root')

    def test_a_binding_copied_between_applications_is_refused(self):
        first, second = self.application('a'), self.application('b')
        self.assertEqual(run_cli(first, 'shop', cwd=self.elsewhere)[0], 0)
        (second / '.crewloom').mkdir()
        (second / '.crewloom' / 'binding.json').write_bytes((first / '.crewloom' / 'binding.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'another checkout'):
            binding.load_binding(second)

    def test_application_state_never_enters_toolkit_memory(self):
        root = self.application('a')
        self.assertEqual(run_cli(root, 'shop', cwd=self.elsewhere)[0], 0)
        status = subprocess.run(['git', '-C', str(TOOLKIT), 'status', '--porcelain', '--', 'Brain', 'MASTER_BRAIN.md'],
                                env=repo_map.git_environment(), capture_output=True, text=True, timeout=30).stdout
        self.assertNotIn(str(root), status)
        for memory in (TOOLKIT / 'Brain').glob('*.md'):
            self.assertNotIn(str(root), memory.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
