"""Adversarial artifact scope tests, including actual filesystem permissions."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import execution_policy as policy
import workflow as w


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'input.txt').write_text('original')
        self.step={'argv':['python3','-c','pass'],'inputs':['input.txt'],'outputs':['output.txt']}

    def test_only_declared_inputs_visible_and_output_published(self):
        (self.root/'secret.txt').write_text('private')
        def execute(stage,*args,**kwargs):
            self.assertFalse((stage/'secret.txt').exists());self.assertEqual(kwargs['writable'],['output.txt'])
            (stage/'output.txt').write_text('verified');return {'exit_code':0}
        with patch.object(w,'docker_execute',side_effect=execute):policy.execute(self.root,self.step,'image',10)
        self.assertEqual((self.root/'output.txt').read_text(),'verified')
        self.assertEqual((self.root/'input.txt').read_text(),'original')

    def test_failed_command_cannot_change_project(self):
        def execute(stage,*args,**kwargs):
            (stage/'input.txt').write_text('tampered');(stage/'output.txt').write_text('unsafe');return {'exit_code':1}
        with patch.object(w,'docker_execute',side_effect=execute):policy.execute(self.root,self.step,'image',10)
        self.assertFalse((self.root/'output.txt').exists());self.assertEqual((self.root/'input.txt').read_text(),'original')

    def test_symlink_and_hardlink_destinations_rejected(self):
        for kind in ('symlink','hardlink'):
            path=self.root/'output.txt'
            if kind=='symlink':path.symlink_to(self.root/'input.txt')
            else:os.link(self.root/'input.txt',path)
            with self.subTest(kind=kind),self.assertRaises(ValueError):policy.destinations(self.root,['output.txt'])
            path.unlink()

    def test_input_changed_during_execution_rejects_all_outputs(self):
        def execute(stage,*args,**kwargs):
            (self.root/'input.txt').write_text('changed');(stage/'output.txt').write_text('artifact');return {'exit_code':0}
        with patch.object(w,'docker_execute',side_effect=execute),self.assertRaisesRegex(ValueError,'Inputs changed'):
            policy.execute(self.root,self.step,'image',10)
        self.assertFalse((self.root/'output.txt').exists())

    def test_output_budget_and_empty_outputs_rejected(self):
        for data in (b'',b'x'*(policy.MAX_OUTPUT_BYTES+1)):
            with self.assertRaises(ValueError):policy.publish(self.root,{'output.txt':data},w.hashes(self.root,['input.txt']))
        self.assertFalse((self.root/'output.txt').exists())


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','Enable live Docker acceptance explicitly')
class ContainerPolicyTests(unittest.TestCase):
    def test_runtime_git_policy_and_other_inputs_are_inaccessible_or_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'secret.txt').write_text('private')
            script="""from pathlib import Path
import json
checks={'private_absent':not Path('secret.txt').exists(),'git_absent':not Path('.git').exists()}
for name,path in [('input_readonly','probe.py'),('runtime_readonly','.crewloom/tamper'),('undeclared_denied','extra.txt')]:
 try:Path(path).write_text('bad');checks[name]=False
 except OSError:checks[name]=True
Path('result.json').write_text(json.dumps(checks))
"""
            (root/'probe.py').write_text(script)
            image=w.inspect_image(w.DEFAULT_IMAGE)
            result=policy.execute(root,{'argv':['python3','probe.py'],'inputs':['probe.py'],'outputs':['result.json']},image,20)
            self.assertEqual(result['exit_code'],0,result.get('output'))
            self.assertTrue(all(json.loads((root/'result.json').read_text()).values()))
            self.assertEqual((root/'probe.py').read_text(),script);self.assertEqual((root/'secret.txt').read_text(),'private')


if __name__=='__main__':unittest.main()
