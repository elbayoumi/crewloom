"""Supervisor-owned native lifecycle identity, version and edit-boundary checks."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import crewloom
import host_lifecycle as lifecycle
import project_binding as binding
import repo_map


class NativeLifecycleBoundaries(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        subprocess.run(['git','init','-q'],cwd=str(self.root),env=repo_map.git_environment(),check=True)
        installed,errors=crewloom.install_skills(self.root,'agents',['context-guardian'],False)
        self.assertFalse(errors);self.assertIn('context-guardian',installed)
        binding.bootstrap(self.root,project_id='native-boundary')
        (self.root/'src').mkdir();(self.root/'src/output.py').write_text('VALUE=1\n',encoding='utf-8')
        (self.root/'criteria.md').write_text('Output VALUE must equal one.',encoding='utf-8')

    def snapshot(self):
        return {str(p.relative_to(self.root)):(p.read_bytes(),p.stat().st_mode,p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file() and not p.is_symlink()}

    def install(self):
        with patch.object(lifecycle,'_version_of',return_value='codex-cli 0.155.1'):
            return lifecycle.install(self.root,'native-boundary','codex','context-guardian',
                criteria_path='criteria.md',sources=['src/output.py'],declared_outputs=['src/output.py'])

    def guard_record(self,outputs=None):
        outputs=outputs or ['src/output.py']
        return {'declared_outputs':outputs,'declared_output_keys':sorted(lifecycle.declared_output_keys(outputs)),
                'control_relative':'.codex/hooks.json'}

    def test_valid_explicit_installation_creates_owned_adapter(self):
        self.install()
        report=lifecycle.status(self.root,'native-boundary','codex')
        self.assertTrue(report['installed'],report)
        self.assertFalse(report['verified_executor'],report)

    def test_unknown_actual_host_version_is_refused_before_writes(self):
        before=self.snapshot()
        with patch.object(lifecycle,'_version_of',return_value='codex-cli 9.9.9'):
            with self.assertRaises(ValueError):
                lifecycle.install(self.root,'native-boundary','codex','context-guardian',
                    criteria_path='criteria.md',declared_outputs=['src/output.py'])
        self.assertEqual(self.snapshot(),before)

    def test_foreign_project_identity_is_refused_before_writes(self):
        before=self.snapshot()
        with self.assertRaises(ValueError):
            lifecycle.install(self.root,'another-project','codex','context-guardian',declared_outputs=['src/output.py'])
        self.assertEqual(self.snapshot(),before)

    def test_altered_adapter_cannot_record_a_new_callback(self):
        self.install()
        control=self.root/'.codex/hooks.json';document=json.loads(control.read_text())
        document['hooks']['PreToolUse']=[]
        control.write_text(json.dumps(document),encoding='utf-8')
        before=self.snapshot()
        with self.assertRaises(ValueError):
            lifecycle.callback(self.root,'native-boundary','codex','UserPromptSubmit',
                {'cwd':str(self.root),'session_id':'s','turn_id':'t','hook_event_name':'UserPromptSubmit'})
        self.assertEqual(self.snapshot(),before)

    def test_foreign_callback_cwd_is_refused_before_writes(self):
        self.install();before=self.snapshot()
        with self.assertRaises(ValueError):
            lifecycle.callback(self.root,'native-boundary','codex','UserPromptSubmit',
                {'cwd':str(self.root.parent),'session_id':'s','turn_id':'t','hook_event_name':'UserPromptSubmit'})
        self.assertEqual(self.snapshot(),before)

    def test_declared_patch_destination_is_allowed(self):
        result=lifecycle.guard_file_edits(self.root,self.guard_record(),
            '*** Begin Patch\n*** Update File: src/output.py\n@@\n-VALUE=1\n+VALUE=2\n*** End Patch\n')
        self.assertIn('src/output.py',result['targets'])

    def test_one_foreign_destination_refuses_the_entire_patch_group(self):
        before=self.snapshot()
        with self.assertRaises(ValueError):
            lifecycle.guard_file_edits(self.root,self.guard_record(),
                '*** Begin Patch\n*** Update File: src/output.py\n@@\n-VALUE=1\n+VALUE=2\n*** Add File: ../foreign.py\n+VALUE=3\n*** End Patch\n')
        self.assertEqual(self.snapshot(),before)

    def test_declaring_runtime_authority_does_not_make_it_editable(self):
        with self.assertRaises(ValueError):
            lifecycle.guard_file_edits(self.root,self.guard_record(['.crewloom/binding.json']),
                '*** Begin Patch\n*** Delete File: .crewloom/binding.json\n*** End Patch\n')

    def test_symlinked_declared_output_is_refused(self):
        foreign=self.root/'foreign.py';foreign.write_text('protected',encoding='utf-8')
        (self.root/'src/output.py').unlink();(self.root/'src/output.py').symlink_to(foreign)
        with self.assertRaises(ValueError):
            lifecycle.guard_file_edits(self.root,self.guard_record(),
                '*** Begin Patch\n*** Delete File: src/output.py\n*** End Patch\n')
        self.assertEqual(foreign.read_text(),'protected')


if __name__=='__main__':
    unittest.main()
