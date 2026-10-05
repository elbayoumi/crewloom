"""Independent coordinator CLI preflight: invalid DAGs must preserve the complete project state."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))
import crewloom
import project_binding as pb
import repo_map


class CoordinatorPreflightBoundaries(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-coordinator-acceptance-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Coordinator acceptance fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        installed, errors = crewloom.install_skills(self.root, 'agents', ['context-guardian'], False)
        self.assertFalse(errors)
        self.assertEqual(installed, ['context-guardian'])
        config = pb.default_config('coordinator-fixture', 'enforced')
        config['policy']['managed_lifecycle'] = True
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config))
        pb.bootstrap(self.root, project_id='coordinator-fixture')
        (self.root / 'input.txt').write_text('frozen fixture input\n')
        (self.root / 'builder.py').write_text('from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text("fixture")\n')
        (self.root / 'criteria.md').write_text('- A declared output exists and passes its independent checks.\n')
        (self.root / 'workflows').mkdir()
        for name in ('left', 'right', 'combine', 'integration'):
            workflow = {'schema_version': 1, 'id': name + '-workflow', 'criteria': 'criteria.md',
                        'steps': [{'id': 'build', 'role': 'context-guardian',
                                   'summary': 'Build one independently scoped artifact',
                                   'argv': ['python3', 'builder.py', name + '.txt'], 'inputs': ['input.txt', 'builder.py'] + (['left.txt', 'right.txt', 'combine.txt'] if name == 'integration' else ['left.txt', 'right.txt'] if name == 'combine' else []),
                                   'outputs': [name + '.txt']}]}
            (self.root / 'workflows' / (name + '.json')).write_text(json.dumps(workflow))
        self.plan = {'schema_version': 1, 'id': 'feature-batch', 'project_id': 'coordinator-fixture',
                     'base': 'HEAD', 'workers': 2,
                     'tasks': [{'id': 'left', 'workflow': 'workflows/left.json', 'depends_on': []},
                               {'id': 'right', 'workflow': 'workflows/right.json', 'depends_on': []},
                               {'id': 'combine', 'workflow': 'workflows/combine.json',
                                'depends_on': ['left', 'right']}],
                     'integration': {'workflow': 'workflows/integration.json'}}
        self.write_plan()
        self.git('add', '.')
        self.git('commit', '-qm', 'Freeze the isolated coordinator fixture')

    def git(self, *arguments):
        return subprocess.run(['git', *arguments], cwd=self.root, env=repo_map.git_environment(),
                              capture_output=True, text=True, check=True, timeout=20).stdout.strip()

    def write_plan(self):
        (self.root / 'coordinator.json').write_text(json.dumps(self.plan))

    def snapshot(self):
        return {str(p.relative_to(self.root)): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                                p.stat().st_mode, p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}

    def validate(self, project_id='coordinator-fixture'):
        return subprocess.run([sys.executable, str(SOURCE / 'crewloom.py'), 'coordinator', 'validate',
                               '--project', str(self.root), '--project-id', project_id,
                               '--manifest', 'coordinator.json'], cwd=self.root,
                              env=repo_map.git_environment(), capture_output=True, text=True, timeout=30)

    def refused_without_writes(self, project_id='coordinator-fixture'):
        # Commit malformed data so the isolated assertion tests that data, not dirty Git status.
        self.write_plan()
        self.git('add', 'coordinator.json')
        self.git('commit', '--allow-empty', '-qm', 'Freeze a known invalid manifest')
        before = self.snapshot()
        result = self.validate(project_id)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('error', result.stdout.lower() + result.stderr.lower())
        self.assertEqual(self.snapshot(), before, 'Rejected coordinator preflight mutated project state')

    def test_a_valid_bound_dag_can_be_validated_without_writing_project_state(self):
        before = self.snapshot()
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_a_cycle_is_refused_before_any_state_or_worktree_write(self):
        self.plan['tasks'][0]['depends_on'] = ['combine']
        self.refused_without_writes()

    def test_missing_dependencies_are_refused_before_writes(self):
        self.plan['tasks'][0]['depends_on'] = ['missing']
        self.refused_without_writes()

    def test_duplicate_task_ids_are_refused_before_writes(self):
        self.plan['tasks'][1]['id'] = 'left'
        self.refused_without_writes()

    def test_option_like_git_refs_are_refused_before_writes(self):
        self.plan['base'] = '--help'
        self.refused_without_writes()

    def test_foreign_project_identity_is_refused_before_writes(self):
        self.refused_without_writes('another-project')

    def test_worker_limit_is_enforced_without_writes(self):
        self.plan['workers'] = 5
        self.refused_without_writes()

    def test_staged_user_changes_are_refused_and_preserved(self):
        (self.root / 'input.txt').write_text('independent staged user changes\n')
        self.git('add', 'input.txt')
        before = self.snapshot()
        result = self.validate()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
