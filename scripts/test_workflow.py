"""Workflow invariants and optional real-Docker acceptance checks."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import workflow as w
import repo_map


def repair_fixture(root):
    """Run the real runner with a deterministic provider and an independent verifier."""
    import crewloom
    import project_binding as pb
    subprocess.run(['git', 'init', '-q'], cwd=root, env=repo_map.git_environment(), check=True)
    pb.bootstrap(root, project_id='repair-integration', mode='off')
    _, errors = crewloom.install_skills(root, 'agents', ['fullstack-mvp-engineer'], False)
    if errors:
        raise AssertionError(errors)
    (root/'contract.txt').write_text('output.txt must contain exactly correct')
    (root/'verify.py').write_text("from pathlib import Path\nassert Path('output.txt').read_text() == 'correct', 'wrong candidate'\nPath('receipt.json').write_text('{\"passed\":true}')\n")
    producer = {'id': 'generate', 'kind': 'model', 'role': 'fullstack-mvp-engineer',
                'summary': 'Implement the contract', 'host': 'openai', 'model': 'fixture-model',
                'inputs': ['contract.txt'], 'outputs': ['output.txt']}
    verifier = {'id': 'verify', 'kind': 'command', 'role': 'fullstack-mvp-engineer',
                'summary': 'Verify the contract', 'argv': ['python3', 'verify.py'],
                'inputs': ['output.txt', 'verify.py'], 'outputs': ['receipt.json']}
    plan = {'schema_version': 1, 'id': 'original', 'steps': [producer, verifier]}
    (root/'workflow.json').write_text(json.dumps(plan))
    return w.read_plan(root, 'workflow.json')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, repo_map.git_environment(), clear=True)
        environment.start(); self.addCleanup(environment.stop)
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

    def test_repair_feedback_is_bound_to_actual_failed_candidate_and_verifier(self):
        import project_binding as pb
        pb.bootstrap(self.root, project_id='repair-fixture')
        binding = pb.load_binding(self.root)
        producer = {'id': 'generate', 'kind': 'model', 'role': 'fullstack-mvp-engineer',
                    'summary': 'Generate', 'host': 'codex', 'model': 'fixture-model',
                    'inputs': ['input.txt'], 'outputs': ['output.txt']}
        verifier = dict(self.plan['steps'][0], id='verify', inputs=['output.txt'], outputs=['receipt.json'])
        original = {'schema_version': 1, 'id': 'original', 'steps': [producer, verifier]}
        (self.root/'original.json').write_text(json.dumps(original))
        _, fingerprint = w.read_plan(self.root, 'original.json')
        (self.root/'candidate.txt').write_text('broken candidate')
        candidate_hash = w.hashes(self.root, ['candidate.txt'])['candidate.txt']
        prior = {'project_root': str(self.root), 'project_id': binding['project_id'],
                 'checkout_id': binding['checkout_id'], 'plan_sha256': fingerprint,
                 'status': 'failed', 'steps': {
                     'generate': {'status': 'complete', 'inputs': w.hashes(self.root, ['input.txt']), 'outputs': {'output.txt': candidate_hash}},
                     'verify': {'status': 'failed', 'error': 'Command failed: verify',
                                'inputs': {'output.txt': candidate_hash},
                                'attempts': [{'status': 'finished', 'exit_code': 1,
                                              'image_id': 'sha256:fixture',
                                              'output': 'expected correct arithmetic'}]}}}
        folder = self.root/'.crewloom/workflows/original'; folder.mkdir(parents=True)
        state_path = folder/'state.json'; state_path.write_text(json.dumps(prior))
        repair = dict(producer, inputs=['input.txt', 'candidate.txt'], repair_from={
            'plan': 'original.json', 'failed_step': 'verify', 'model_step': 'generate',
            'candidates': {'output.txt': 'candidate.txt'}})
        plan = {'schema_version': 1, 'id': 'repair-one', 'steps': [repair, verifier]}
        feedback = w.repair_feedback(self.root, plan, repair)
        self.assertEqual(feedback['diagnostic'], 'expected correct arithmetic')
        self.assertEqual(feedback['repair_attempt'], 1)
        self.assertIn('untrusted input', feedback['instruction'])
        (self.root/'candidate.txt').write_text('different candidate')
        with self.assertRaisesRegex(ValueError, 'differs'):
            w.repair_feedback(self.root, plan, repair)
        (self.root/'candidate.txt').write_text('broken candidate')
        (self.root/'input.txt').write_text('changed contract')
        with self.assertRaisesRegex(ValueError, 'generation inputs changed'):
            w.repair_feedback(self.root, plan, repair)
        (self.root/'input.txt').write_text('input')
        prior['checkout_id'] = '0'*32; state_path.write_text(json.dumps(prior))
        with self.assertRaisesRegex(ValueError, 'bound checkout'):
            w.repair_feedback(self.root, plan, repair)
        prior['checkout_id'] = binding['checkout_id']; state_path.write_text(json.dumps(prior))
        plan['steps'][1] = dict(verifier, argv=['python3', 'always_pass.py'])
        with self.assertRaisesRegex(ValueError, 'unchanged verifier'):
            w.repair_feedback(self.root, plan, repair)

    def test_resume_does_not_repeat_complete_command(self):
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=self.execute) as execute:
            self.assertEqual(self.run_plan()['status'],'complete')
            self.assertEqual(self.run_plan()['status'],'complete')
            self.assertEqual(execute.call_count,1)

    def test_repair_payload_reuse_budget_and_private_preparation(self):
        import model_host
        import privacy
        import copy
        plan, fingerprint = repair_fixture(self.root)
        def verify(root, argv, image, timeout, **kwargs):
            if (root/'output.txt').read_text() != 'correct':
                return {'exit_code': 1, 'image_id': image, 'output': 'wrong candidate'}
            (root/'receipt.json').write_text('{"passed":true}')
            return {'exit_code': 0, 'image_id': image, 'output': ''}
        def generate(host, prompt, outputs, timeout, model):
            calls.append(prompt)
            return {'output.txt': 'correct' if len(calls) == 2 else 'broken'}, {}
        calls = []
        with patch.object(model_host, 'generate', side_effect=generate), patch.object(w, 'inspect_image', return_value='sha256:fixture'), patch.object(w, 'docker_execute', side_effect=verify):
            self.assertEqual(w.run(self.root, plan, fingerprint, 'image')['status'], 'failed')
            source_state = self.root/'.crewloom/workflows/original/state.json'
            original_bytes = source_state.read_bytes()
            prepared = w.prepare_repair(self.root, 'workflow.json', 'repair-one', 'generate', 'verify')
            repaired, checksum = w.read_plan(self.root, prepared['plan'])
            self.assertEqual(w.run(self.root, repaired, checksum, 'image')['status'], 'complete')
            self.assertEqual(w.run(self.root, repaired, checksum, 'image')['status'], 'complete')
            self.assertEqual(len(calls), 2)
            self.assertIn('wrong candidate', calls[-1])
            self.assertIn('broken', calls[-1])
            self.assertIn('untrusted input', calls[-1])
            self.assertEqual(source_state.read_bytes(), original_bytes)
            candidate = repaired['steps'][0]['repair_from']['candidates']['output.txt']
            self.assertEqual(subprocess.run(['git', 'check-ignore', candidate], cwd=self.root, env=repo_map.git_environment(), capture_output=True).returncode, 0)
            subprocess.run(['git', 'add', '-f', candidate], cwd=self.root, env=repo_map.git_environment(), check=True)
            self.assertTrue(any(item['path'] == candidate for item in privacy.check(self.root)))
            with self.assertRaisesRegex(ValueError, 'already has execution history'):
                w.prepare_repair(self.root, 'workflow.json', 'repair-one', 'generate', 'verify')
            # Preserve a separate recorded failed second candidate to exercise ancestry.
            state_path = self.root/'.crewloom/workflows/repair-one/state.json'
            state = json.loads(state_path.read_text())
            state['status'] = 'failed'
            state['steps']['verify']['status'] = 'failed'
            state_path.write_text(json.dumps(state))
            second = w.prepare_repair(self.root, prepared['plan'], 'repair-two', 'generate', 'verify')
            second_plan, _ = w.read_plan(self.root, second['plan'])
            self.assertEqual(w.repair_feedback(self.root, second_plan, second_plan['steps'][0])['repair_attempt'], 2)
            _, second_checksum = w.read_plan(self.root, second['plan'])
            with patch.object(model_host, 'build_prompt', return_value='x' * model_host.MAX_TEXT):
                self.assertEqual(w.run(self.root, second_plan, second_checksum, 'image')['status'], 'failed')
            self.assertEqual(len(calls), 2, 'Oversized feedback must be refused before a provider call')
            with patch.object(w, 'inspect_image', return_value='sha256:substituted'):
                with self.assertRaisesRegex(ValueError, 'original verifier image'):
                    w.run(self.root, second_plan, second_checksum, 'image')
            branching = w.prepare_repair(self.root, 'workflow.json', 'repair-branch', 'generate', 'verify')
            branch_plan, branch_checksum = w.read_plan(self.root, branching['plan'])
            blocked = w.run(self.root, branch_plan, branch_checksum, 'image')
            self.assertEqual(blocked['status'], 'failed')
            branch_state = json.loads((self.root/'.crewloom/workflows/repair-branch/state.json').read_text())
            self.assertIn('Two model repair requests exhausted', branch_state['error'])
            self.assertEqual(len(calls), 3, 'A new workflow ID cannot reset the repair request budget')
            third = copy.deepcopy(second_plan)
            third['id'] = 'repair-three'
            third['steps'][0]['repair_from']['plan'] = second['plan']
            with self.assertRaisesRegex(ValueError, 'limited to two'):
                w.repair_feedback(self.root, third, third['steps'][0])

    def test_local_provider_is_forwarded_and_frozen_before_publication_and_reuse(self):
        import model_host
        plan, _ = repair_fixture(self.root)
        profile = {'schema_version': 1, 'provider_id': 'local',
                   'base_url': 'http://127.0.0.1:43217/v1', 'models': ['fixture-small'],
                   'prompt_budget_bytes': 65536}
        path = self.root/'.crewloom/private/providers/local.json'
        path.parent.mkdir(parents=True); path.write_text(json.dumps(profile)); path.chmod(0o600)
        plan['steps'][0].update(host='opencode', model='local/fixture-small',
                               opencode_provider='.crewloom/private/providers/local.json')
        (self.root/'workflow.json').write_text(json.dumps(plan))
        plan, checksum = w.read_plan(self.root, 'workflow.json')
        calls = []
        def generate(host, prompt, outputs, timeout, model, **kwargs):
            calls.append(kwargs['provider_profile'])
            self.assertEqual(host, 'opencode'); self.assertEqual(model, 'local/fixture-small')
            self.assertIn('provider_profile_sha256', prompt)
            self.assertNotIn(profile['base_url'], prompt)
            if len(calls) == 1:
                changed = dict(profile, prompt_budget_bytes=65537)
                path.write_text(json.dumps(changed))
            return {'output.txt': 'correct'}, {}
        def verify(root, argv, image, timeout, **kwargs):
            (root/'receipt.json').write_text('{"passed":true}')
            return {'exit_code': 0, 'image_id': image, 'output': ''}
        with patch.object(model_host, 'generate', side_effect=generate), patch.object(w, 'inspect_image', return_value='sha256:fixture'), patch.object(w, 'docker_execute', side_effect=verify):
            self.assertEqual(w.run(self.root, plan, checksum, 'image', allow_host_cli=True)['status'], 'failed')
            self.assertFalse((self.root/'output.txt').exists())
            self.assertEqual(w.run(self.root, plan, checksum, 'image', allow_host_cli=True)['status'], 'complete')
            self.assertEqual(w.run(self.root, plan, checksum, 'image', allow_host_cli=True)['status'], 'complete')
            self.assertEqual(len(calls), 2)
            path.write_text(json.dumps(dict(profile, prompt_budget_bytes=65538)))
            with self.assertRaisesRegex(ValueError, 'Model context changed'):
                w.run(self.root, plan, checksum, 'image', allow_host_cli=True)

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

    def test_agent_packet_is_portable_bound_and_does_not_accept_or_generate(self):
        import crewloom
        import project_binding as pb
        import model_host as mh
        pb.bootstrap(self.root, project_id='packet-project', mode='off')
        _, errors = crewloom.install_skills(self.root, 'agents', ['fullstack-mvp-engineer'], False)
        self.assertFalse(errors)
        self.plan['steps'][0]['kind'] = 'task'; self.plan['steps'][0].pop('argv')
        self.plan['language'] = 'ar'
        plan, fingerprint = self.write_plan()
        with self.assertRaisesRegex(ValueError, 'awaiting task'):
            w.agent_packet(self.root, plan, fingerprint)
        self.assertEqual(w.run(self.root, plan, fingerprint, 'image')['status'], 'awaiting_task')
        state_path = w.runtime(self.root, plan['id'])/'state.json'
        original = state_path.read_bytes()
        with patch.object(mh, 'generate') as generate:
            packet = w.agent_packet(self.root, plan, fingerprint)
            generate.assert_not_called()
        self.assertEqual(packet['project_id'], 'packet-project')
        self.assertEqual(packet['checkout_id'], pb.load_binding(self.root)['checkout_id'])
        self.assertEqual(packet['input_sha256'], w.hashes(self.root, ['input.txt']))
        self.assertEqual(packet['prompt_sha256'], w.digest(packet['prompt'].encode()))
        self.assertIn('"language":"ar"', packet['prompt'])
        self.assertEqual(packet['response_schema'], mh.SCHEMA)
        self.assertFalse(packet['execution_verified'])
        self.assertEqual(state_path.read_bytes(), original)
        self.assertFalse((self.root/'output.txt').exists())
        # A source changing while the packet is assembled is refused, not exported.
        build = mh.build_prompt
        def mutate(*args, **kwargs):
            prompt = build(*args, **kwargs)
            (self.root/'input.txt').write_text('changed')
            return prompt
        with patch.object(mh, 'build_prompt', side_effect=mutate), self.assertRaisesRegex(ValueError, 'inputs or binding changed'):
            w.agent_packet(self.root, plan, fingerprint)
        calls = 0
        def mutate_after_last_read(*args, **kwargs):
            nonlocal calls
            prompt = build(*args, **kwargs); calls += 1
            if calls == 2:
                (self.root/'input.txt').write_text('late editor change')
            return prompt
        with patch.object(mh, 'build_prompt', side_effect=mutate_after_last_read), self.assertRaisesRegex(ValueError, 'inputs or binding changed'):
            w.agent_packet(self.root, plan, fingerprint)
        self.assertEqual(calls, 2)
        w.cancel(self.root, plan, fingerprint)
        with self.assertRaisesRegex(ValueError, 'awaiting task'):
            w.agent_packet(self.root, plan, fingerprint)


    def test_agent_packet_enforced_context_refuses_stale_sources(self):
        import crewloom
        import project_binding as pb
        subprocess.run(['git', 'init', '-q'], cwd=self.root, env=repo_map.git_environment(), check=True)
        pb.bootstrap(self.root, project_id='packet-enforced', mode='enforced')
        _, errors = crewloom.install_skills(self.root, 'agents', ['fullstack-mvp-engineer'], False)
        self.assertFalse(errors)
        self.plan['steps'][0]['kind'] = 'task'; self.plan['steps'][0].pop('argv')
        plan, fingerprint = self.write_plan()
        self.assertEqual(w.run(self.root, plan, fingerprint, 'image')['status'], 'awaiting_task')
        packet = w.agent_packet(self.root, plan, fingerprint)
        self.assertIn('"project_context":', packet['prompt'])
        self.assertIn('packet-enforced', packet['prompt'])
        (self.root/'input.txt').write_text('obsolete source')
        with self.assertRaisesRegex(ValueError, 'stale'):
            w.agent_packet(self.root, plan, fingerprint)

    def test_task_actions_need_explicit_project(self):
        import contextlib,io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:w.main(['run'])
        self.assertEqual(error.exception.code,2)

    def test_paused_task_reserves_the_project_between_calls(self):
        self.plan['steps'][0]['kind']='task';self.plan['steps'][0].pop('argv')
        plan,fingerprint=self.write_plan()
        self.assertEqual(w.run(self.root,plan,fingerprint,'image')['status'],'awaiting_task')
        other=json.loads(json.dumps(plan));other['id']='other-task';other['steps'][0]['outputs']=['other.txt']
        with self.assertRaisesRegex(ValueError,'unfinished workflow'):
            w.run(self.root,other,w.digest(json.dumps(other,sort_keys=True).encode()),'image')
        self.assertEqual(w.active_workflow(self.root)['workflow'],plan['id'])
        self.assertFalse((self.root/'other.txt').exists())

    def test_cancel_preserves_files_and_history_and_blocks_resume(self):
        self.plan['steps'][0]['kind']='task';self.plan['steps'][0].pop('argv')
        plan,fingerprint=self.write_plan();w.run(self.root,plan,fingerprint,'image')
        (self.root/'output.txt').write_text('partial artifact')
        ledger={'attempts':[{'signature':'prior-failure','status':'failed'}]};w.save_ledger(self.root,ledger)
        self.assertEqual(w.cancel(self.root,plan,fingerprint)['status'],'cancelled')
        self.assertEqual((self.root/'output.txt').read_text(),'partial artifact')
        self.assertEqual(json.loads((self.root/'.crewloom/attempts.json').read_text()),ledger)
        self.assertIsNone(w.active_workflow(self.root))
        with self.assertRaisesRegex(ValueError,'Cancelled'):w.run(self.root,plan,fingerprint,'image')
        self.assertEqual(w.cancel(self.root,plan,fingerprint)['idempotent'],True)
        other=json.loads(json.dumps(plan));other['id']='new-task'
        self.assertEqual(w.run(self.root,other,w.digest(json.dumps(other,sort_keys=True).encode()),'image')['status'],'awaiting_task')

    def test_cancel_cannot_bypass_running_project_lock(self):
        plan,fingerprint=self.write_plan()
        with w.lock(w.safe_path(self.root,'.crewloom',internal=True)):
            with self.assertRaisesRegex(ValueError,'locked'):w.cancel(self.root,plan,fingerprint)

    def test_actual_concurrent_runs_same_project_rejected(self):
        plan,fingerprint=self.write_plan();entered=threading.Event();release=threading.Event()
        def execute(root,argv,image,timeout,**kwargs):
            entered.set();self.assertTrue(release.wait(5));return self.execute(root,argv,image,timeout,**kwargs)
        with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=execute),ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(w.run,self.root,plan,fingerprint,'image')
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(ValueError,'locked'):w.run(self.root,plan,fingerprint,'image')
            finally:release.set()
            self.assertEqual(first.result(timeout=5)['status'],'complete')
        self.assertIsNone(w.active_workflow(self.root))

    def test_actual_parallel_projects_with_identical_names_are_independent(self):
        plan,fingerprint=self.write_plan();barrier=threading.Barrier(2)
        with tempfile.TemporaryDirectory() as t:
            other=Path(t).resolve();(other/'input.txt').write_text('second project')
            def execute(root,argv,image,timeout,**kwargs):
                barrier.wait(timeout=5);(root/'output.txt').write_text((root/'input.txt').read_text())
                return {'exit_code':0,'output':''}
            with patch.object(w,'inspect_image',return_value='sha256:test'),patch.object(w,'docker_execute',side_effect=execute),ThreadPoolExecutor(max_workers=2) as pool:
                runs=[pool.submit(w.run,root,plan,fingerprint,'image') for root in (self.root,other)]
                results=[future.result(timeout=8) for future in runs]
            self.assertEqual([r['status'] for r in results],['complete','complete'])
            self.assertEqual((self.root/'output.txt').read_text(),'input')
            self.assertEqual((other/'output.txt').read_text(),'second project')
            self.assertNotEqual(results[0]['project_root'],results[1]['project_root'])

    def test_copied_or_symlinked_project_reservation_rejected(self):
        folder=self.root/'.crewloom';folder.mkdir()
        path=folder/'active_workflow.json'
        path.write_text(json.dumps({'project_root':'/other/project','workflow':'test-feature','plan_sha256':'a'*64}))
        with self.assertRaisesRegex(ValueError,'cross-project'):self.run_plan()
        path.unlink()
        with tempfile.TemporaryDirectory() as t:
            path.symlink_to(Path(t)/'active.json')
            with self.assertRaisesRegex(ValueError,'symlinks|escapes'):self.run_plan()

    def test_native_context_reservation_blocks_a_different_workflow(self):
        folder=self.root/'.crewloom';folder.mkdir()
        (folder/'active_task.json').write_text(json.dumps(
            {'schema_version':1,'project_root':str(self.root),'project_id':'sample-project',
             'checkout_id':'a'*32,'task_id':'native-task','owner':'project-context'}))
        with self.assertRaisesRegex(ValueError,'reserved by native context task'):self.run_plan()


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','Enable real Docker integration checks explicitly')
class DockerWorkflowTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, repo_map.git_environment(), clear=True)
        environment.start(); self.addCleanup(environment.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.image=w.inspect_image(w.DEFAULT_IMAGE)

    def test_actual_failed_verification_then_repair_and_reuse(self):
        import model_host
        plan, fingerprint = repair_fixture(self.root)
        with patch.object(model_host, 'generate', side_effect=[({'output.txt': 'broken'}, {}), ({'output.txt': 'correct'}, {})]) as provider:
            self.assertEqual(w.run(self.root, plan, fingerprint, self.image)['status'], 'failed')
            original = (self.root/'.crewloom/workflows/original/state.json').read_bytes()
            prepared = w.prepare_repair(self.root, 'workflow.json', 'repair-one', 'generate', 'verify')
            repaired, checksum = w.read_plan(self.root, prepared['plan'])
            self.assertEqual(w.run(self.root, repaired, checksum, self.image)['status'], 'complete')
            self.assertEqual(w.run(self.root, repaired, checksum, self.image)['status'], 'complete')
            self.assertEqual(provider.call_count, 2)
            self.assertEqual((self.root/'.crewloom/workflows/original/state.json').read_bytes(), original)
            self.assertTrue(json.loads((self.root/'receipt.json').read_text())['passed'])

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
