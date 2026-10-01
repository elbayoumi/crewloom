"""Regression coverage for `crewloom install` and its refusals."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts' / 'crewloom.py'


def cli(*args):
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, timeout=30)


class InstallTests(unittest.TestCase):
    def test_installs_selected_role_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            ok = cli('install', '--host', 'claude', '--target', directory, '--skill', 'seo-growth-engineer')
            self.assertEqual(ok.returncode, 0, ok.stderr)
            installed = Path(directory) / '.claude' / 'skills' / 'seo-growth-engineer'
            self.assertTrue((installed / 'SKILL.md').is_file())
            self.assertFalse(list(installed.rglob('__pycache__')))
            again = cli('install', '--host', 'claude', '--target', directory, '--skill', 'seo-growth-engineer')
            self.assertEqual(again.returncode, 2)
            self.assertIn('--force', again.stderr)
            forced = cli('install', '--host', 'claude', '--target', directory, '--skill', 'seo-growth-engineer', '--force')
            self.assertEqual(forced.returncode, 0)

    def test_unknown_and_invalid_roles_and_missing_target_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory, '--skill', 'nope').returncode, 2)
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory, '--skill', '../x').returncode, 2)
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory + '/missing').returncode, 2)
            self.assertFalse((Path(directory) / '.agents').exists())

    def test_installs_all_roles_for_agents_host(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cli('install', '--host', 'agents', '--target', directory).returncode, 0)
            self.assertEqual(len(list((Path(directory) / '.agents' / 'skills').glob('*/SKILL.md'))), 42)


if __name__ == '__main__':
    unittest.main()

class ProjectIsolationTests(unittest.TestCase):
    def test_same_relative_input_uses_selected_project_and_separate_logs(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name, data in [('one', json.loads((ROOT/'examples/workflows/valid.json').read_text())), ('two', [])]:
                project=root/name; project.mkdir()
                (project/'workflow.json').write_text(json.dumps(data))
            one=cli('run','--project',str(root/'one'),'workflow-contract','--','workflow.json')
            two=cli('run','--project',str(root/'two'),'workflow-contract','--','workflow.json')
            self.assertNotEqual(one.returncode,two.returncode)
            for name in ('one','two'):
                log=root/name/'.crewloom/runs.jsonl'
                records=[json.loads(line) for line in log.read_text().splitlines()]
                self.assertEqual(len(records),1)
                self.assertEqual(records[0]['project_root'],str((root/name).resolve()))

    def test_cross_project_path_and_symlink_install_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); one=root/'one'; two=root/'two'; one.mkdir();two.mkdir()
            (two/'input.json').write_text('{}')
            for arg in ('../two/input.json', str(two/'input.json')):
                result=cli('run','--project',str(one),'workflow-contract','--',arg)
                self.assertEqual(result.returncode,2)
                self.assertIn('escapes selected project',result.stderr)
            (one/'.agents').symlink_to(two,target_is_directory=True)
            self.assertEqual(cli('install','--host','agents','--target',str(one),'--skill','context-guardian').returncode,2)
            self.assertFalse((two/'skills').exists())
            (one/'.crewloom').mkdir()
            (two/'runs.jsonl').write_text('')
            (one/'.crewloom/runs.jsonl').symlink_to(two/'runs.jsonl')
            result=cli('run','--project',str(one),'budget-pacing','--','--daily-budget','100','--days-elapsed','1','--actual-spend','100')
            self.assertEqual(result.returncode,2)
            self.assertEqual((two/'runs.jsonl').read_text(),'')

    def test_context_uses_project_memory_and_rejects_other_project_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); one=root/'one';two=root/'two';one.mkdir();two.mkdir()
            self.assertEqual(cli('install','--host','agents','--target',str(one),'--skill','context-guardian').returncode,0)
            brain=one/'.agents/skills/context-guardian/brain/ARCHITECTURE.md'
            brain.write_text('# Architecture\nPROJECT_ONE_ONLY')
            out=one/'context.md'
            result=cli('context','--project',str(one),'context-guardian','--out',str(out))
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('PROJECT_ONE_ONLY',out.read_text())
            self.assertNotEqual(cli('context','--project',str(one),'context-guardian','--out',str(two/'context.md')).returncode,0)
            self.assertFalse((two/'context.md').exists())
            self.assertNotEqual(cli('context','--project',str(two),'context-guardian','--out',str(two/'context.md')).returncode,0)
