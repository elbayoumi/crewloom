"""Workflow invariants and optional real-Docker acceptance checks."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import workflow as w


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'input.txt').write_text('input')
        self.plan={'schema_version':1,'id':'test-feature','steps':[{'id':'build','role':'fullstack-mvp-engineer','summary':'Build output','argv':['python3','build.py'],'inputs':['input.txt'],'outputs':['output.txt']}]}
        self.write_plan()

    def write_plan(self):
        (self.root/'workflow.json').write_text(json.dumps(self.plan))
        return w.read_plan(self.root,'workflow.json')

    def execute(self, root, argv, image, timeout, **kwargs):
        (root/'output.txt').write_text('verified-output')
        return {'exit_code':0,'duration_ms':1,'output':'','image_id':image}

    def run_plan(self):
        plan,fingerprint=self.write_plan()
        return w.run(self.root,plan,fingerprint,'image')

    def test_resume_does_not_repeat_complete_command(self):
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=self.execute) as execute:
            self.assertEqual(self.run_plan()['status'],'complete')
            self.assertEqual(self.run_plan()['status'],'complete')
            self.assertEqual(execute.call_count,1)

    def test_changed_completed_artifact_rejected(self):
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=self.execute):
            self.run_plan();(self.root/'output.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'Stale evidence'):self.run_plan()

    def test_changed_input_rejected(self):
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=self.execute):
            self.run_plan();(self.root/'input.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'Stale evidence'):self.run_plan()

    def test_cross_project_and_symlink_paths_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            (self.root/'redirect').symlink_to(Path(other),target_is_directory=True)
            (self.root/'.crewloom').mkdir();(self.root/'state-alias').symlink_to(self.root/'.crewloom',target_is_directory=True)
            for path in ('../foreign.txt','redirect/foreign.txt','/etc/passwd','.crewloom/state.json','state-alias/state.json'):
                with self.subTest(path=path),self.assertRaises(ValueError):w.safe_path(self.root,path)

    def test_duplicate_artifact_owner_rejected(self):
        duplicate=dict(self.plan['steps'][0],id='review');self.plan['steps'].append(duplicate)
        with self.assertRaisesRegex(ValueError,'one owner'):self.write_plan()

    def test_unknown_role_rejected(self):
        self.plan['steps'][0]['role']='unknown-role'
        with self.assertRaisesRegex(ValueError,'Unknown role'):self.write_plan()

    def test_changed_plan_and_copied_project_state_rejected(self):
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=self.execute):self.run_plan()
        self.plan['steps'][0]['summary']='changed'
        with self.assertRaisesRegex(ValueError,'another project or plan'):self.run_plan()
        plan,fingerprint=self.write_plan();folder=w.runtime(self.root,self.plan['id']);state=json.loads((folder/'state.json').read_text());state['plan_sha256']=fingerprint;state['project_root']='/another/project';w.save(folder,state)
        with self.assertRaises(ValueError):w.state_for(self.root,plan,fingerprint)

    def test_two_unchanged_failures_block_third_attempt(self):
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',return_value={'exit_code':1,'output':'failure'}) as execute:
            self.assertEqual(self.run_plan()['status'],'failed');self.assertEqual(self.run_plan()['status'],'failed')
            with self.assertRaisesRegex(ValueError,'Two attempts'):self.run_plan()
            self.assertEqual(execute.call_count,2)

    def test_new_workflow_id_cannot_reset_failed_attempt_budget(self):
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',return_value={'exit_code':1,'output':'failure'}) as execute:
            self.run_plan();self.run_plan();self.plan['id']='renamed-workflow'
            with self.assertRaisesRegex(ValueError,'Two attempts'):self.run_plan()
            self.assertEqual(execute.call_count,2)
            (self.root/'input.txt').write_text('changed cause')
            self.assertEqual(self.run_plan()['status'],'failed')
            self.assertEqual(execute.call_count,3)

    def test_old_output_cannot_make_noop_pass(self):
        (self.root/'output.txt').write_text('old')
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',return_value={'exit_code':0,'output':''}):
            result=self.run_plan();self.assertEqual(result['status'],'failed')

    def test_missing_docker_fails_closed(self):
        with patch.object(w,'inspect_image',side_effect=ValueError('Docker unavailable')),patch.object(w,'docker_execute') as execute:
            with self.assertRaisesRegex(ValueError,'Docker unavailable'):self.run_plan()
            execute.assert_not_called()

    def test_lock_rejects_concurrent_execution(self):
        folder=w.runtime(self.root,self.plan['id'])
        with w.lock(folder):
            with self.assertRaisesRegex(ValueError,'locked'):
                with w.lock(folder):pass

    def test_malformed_state_fails_closed(self):
        plan,fingerprint=self.write_plan();folder=w.runtime(self.root,plan['id']);folder.mkdir(parents=True)
        (folder/'state.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'Malformed'):w.state_for(self.root,plan,fingerprint)

    def test_in_place_source_edit_preserves_consumed_input_evidence(self):
        self.plan['steps'][0]['inputs'].append('output.txt');(self.root/'output.txt').write_text('before')
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=self.execute):
            result=self.run_plan();self.assertEqual(result['status'],'complete')
            self.assertNotEqual(result['completed']['build']['inputs']['output.txt'],result['completed']['build']['outputs']['output.txt'])
            self.assertEqual(self.run_plan()['status'],'complete')

    def test_task_handoff_and_independent_reviewer_identifier(self):
        self.plan['steps'][0]['kind']='task';self.plan['steps'][0].pop('argv')
        plan,fingerprint=self.write_plan()
        self.assertEqual(w.run(self.root,plan,fingerprint,'image')['status'],'awaiting_task')
        (self.root/'output.txt').write_text('agent-produced artifact')
        with self.assertRaises(ValueError):w.run(self.root,plan,fingerprint,'image','build','fullstack-mvp-engineer')
        result=w.run(self.root,plan,fingerprint,'image','build','reviewer-a')
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['completed']['build']['reviewer'],'reviewer-a')


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','Enable real Docker integration checks explicitly')
class DockerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.image=w.inspect_image(w.DEFAULT_IMAGE)

    def test_software_feature_end_to_end_and_resume(self):
        shutil.copytree(w.LIBRARY/'examples/software-workflow/project',self.root,dirs_exist_ok=True)
        plan,fingerprint=w.read_plan(self.root,'workflow.json')
        first=w.run(self.root,plan,fingerprint,w.DEFAULT_IMAGE)
        second=w.run(self.root,plan,fingerprint,w.DEFAULT_IMAGE)
        self.assertEqual(first['status'],'complete');self.assertEqual(len(second['completed']),6)
        self.assertTrue(all(item['attempt_count']==1 for item in second['completed'].values()))
        self.assertEqual(json.loads((self.root/'artifacts/delivery.json').read_text())['tests']['exit_code'],0)

    def test_network_library_and_runtime_state_are_restricted(self):
        script="""import json,socket,pathlib
results={'library':not pathlib.Path('/crewloom/README.md').exists()}
for name,file in [('runtime','/workspace/.crewloom/tamper')]:
 try:pathlib.Path(file).write_text('tamper');results[name]=False
 except OSError:results[name]=True
try:socket.create_connection(('1.1.1.1',443),timeout=1);results['network']=False
except OSError:results['network']=True
pathlib.Path('isolation.json').write_text(json.dumps(results))
"""
        (self.root/'probe.py').write_text(script)
        result=w.docker_execute(self.root,['python3','probe.py'],self.image,20)
        self.assertEqual(result['exit_code'],0,result['output'])
        self.assertEqual(json.loads((self.root/'isolation.json').read_text()),{'library':True,'runtime':True,'network':True})

    def test_other_project_not_mounted(self):
        with tempfile.TemporaryDirectory() as other:
            secret=Path(other).resolve()/'private.txt';secret.write_text('OTHER_PROJECT')
            (self.root/'redirect').symlink_to(secret)
            result=w.docker_execute(self.root,['python3','-c',"from pathlib import Path; assert not Path('redirect').exists()"],self.image,20)
            self.assertEqual(result['exit_code'],0,result['output'])
            self.assertEqual(secret.read_text(),'OTHER_PROJECT')

    def test_output_capture_is_bounded(self):
        result=w.docker_execute(self.root,['python3','-c',"print('x'*100000)"],self.image,20)
        self.assertEqual(result['exit_code'],0)
        self.assertLessEqual(len(result['output'].encode()),65536)
        self.assertTrue(result['output_truncated'])

    def test_timeout_terminates_command(self):
        result=w.docker_execute(self.root,['python3','-c','import time; time.sleep(30)'],self.image,2)
        self.assertEqual(result['exit_code'],124)
        self.assertTrue(result['timed_out'])


if __name__=='__main__':unittest.main()
