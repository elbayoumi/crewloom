"""Model outputs must obey project scope even when the host returns unsafe JSON."""
import json
from pathlib import Path
import tempfile
import os
import sys
import unittest
from unittest.mock import patch
import model_host as h
import workflow as w


class ArtifactTests(unittest.TestCase):
    def test_exact_declared_set(self):
        self.assertEqual(h.validate_artifacts({'artifacts':[{'path':'src/a.py','content':'print(1)'}]},['src/a.py']),{'src/a.py':'print(1)'})

    def test_escaping_duplicate_missing_empty_or_extra_rejected(self):
        for value in ({'artifacts':[{'path':'../a','content':'x'}]},
                      {'artifacts':[{'path':'a','content':'x'},{'path':'a','content':'y'}]},
                      {'artifacts':[]},{'artifacts':[{'path':'a','content':''}]},
                      {'artifacts':[{'path':'a','content':'x','command':'rm'}]}):
            with self.subTest(value=value),self.assertRaises(ValueError):h.validate_artifacts(value,['a'])

    def test_artifact_size_limit(self):
        with self.assertRaisesRegex(ValueError,'size limit'):
            h.validate_artifacts({'artifacts':[{'path':'a','content':'x'*(h.MAX_ARTIFACT_BYTES+1)}]},['a'])

    def test_claude_tools_and_settings_disabled(self):
        with tempfile.TemporaryDirectory() as t:
            argv=h.command('claude','claude',Path(t))
        self.assertEqual(argv[argv.index('--tools')+1],'')
        self.assertEqual(argv[argv.index('--setting-sources')+1],'')
        self.assertIn('--strict-mcp-config',argv);self.assertNotIn('bypassPermissions',argv)

    def test_codex_read_only_and_user_config_disabled(self):
        with tempfile.TemporaryDirectory() as t:argv=h.command('codex','codex',Path(t))
        self.assertIn('--ignore-user-config',argv);self.assertIn('read-only',argv)
        self.assertIn('features.shell_tool=false',argv);self.assertIn('features.multi_agent=false',argv)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',argv)

    def test_host_tool_events_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'tool'):
                h.parse_response('codex',json.dumps({'type':'item.completed','item':{'type':'command_execution'}}),Path(t))

    def test_nonfatal_diagnostic_is_not_a_tool_event(self):
        with tempfile.TemporaryDirectory() as t:
            scratch=Path(t);(scratch/'response.json').write_text(json.dumps({'artifacts':[{'path':'a','content':'x'}]}))
            events=[{'type':'item.completed','item':{'type':'error','message':'Invalid optional skill ignored'}},
                    {'type':'turn.completed','usage':{'input_tokens':2}}]
            value,usage,cost=h.parse_response('codex','\n'.join(json.dumps(e) for e in events),scratch)
            self.assertEqual(usage['host_diagnostic_items'],1);self.assertEqual(value['artifacts'][0]['content'],'x')
            with self.assertRaisesRegex(ValueError,'complete'):
                h.parse_response('codex',json.dumps(events[0]),scratch)

    def test_claude_error_or_permission_denial_rejected(self):
        for value in ({'is_error':True},{'permission_denials':['Read']}):
            with self.assertRaises(ValueError):h.parse_response('claude',json.dumps(value),Path('/unused'))


class ProcessBoundaryTests(unittest.TestCase):
    def test_generation_does_not_forward_arbitrary_environment(self):
        script="import json,os,pathlib;pathlib.Path('response.json').write_text(json.dumps({'artifacts':[{'path':'a','content':os.environ.get('CREWLOOM_PRIVATE_TEST','absent')}]}));print(json.dumps({'type':'turn.completed','usage':{}}))"
        with patch.object(h,'probe',return_value={'executable':sys.executable,'version':'synthetic-fixture'}),patch.object(h,'command',return_value=[sys.executable,'-c',script]),patch.dict(os.environ,{'CREWLOOM_PRIVATE_TEST':'should-not-forward'}):
            artifacts,evidence=h.generate('codex','test input',['a'],5)
        self.assertEqual(artifacts['a'],'absent')

    def test_timeout_terminates_host_process(self):
        with patch.object(h,'probe',return_value={'executable':sys.executable,'version':'synthetic-fixture'}),patch.object(h,'command',return_value=[sys.executable,'-c','import time;time.sleep(5)']):
            with self.assertRaisesRegex(ValueError,'timed out'):h.generate('codex','input',['a'],0.3)


class ModelWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'task.md').write_text('Implement a bounded feature')
        folder=self.root/'.agents/skills/fullstack-mvp-engineer';(folder/'brain').mkdir(parents=True)
        (folder/'SKILL.md').write_text('Use only project inputs')
        for name in w.MEMORY:(folder/'brain'/(name+'.md')).write_text('# Project memory')
        self.plan={'schema_version':1,'id':'model-demo','steps':[{'id':'implement','role':'fullstack-mvp-engineer',
                   'kind':'model','host':'codex','summary':'Implement feature','inputs':['task.md'],'outputs':['src/a.py']}]}

    def run_plan(self):
        (self.root/'workflow.json').write_text(json.dumps(self.plan))
        plan,fingerprint=w.read_plan(self.root,'workflow.json')
        return w.run(self.root,plan,fingerprint,'image',allow_host_cli=True)

    def test_generation_and_resume_no_repeated_provider_call(self):
        with patch.object(h,'generate',return_value=({'src/a.py':'print(1)'},{'host':'codex'})) as generate:
            self.assertEqual(self.run_plan()['status'],'complete')
            self.assertEqual(self.run_plan()['status'],'complete');self.assertEqual(generate.call_count,1)
        self.assertEqual((self.root/'src/a.py').read_text(),'print(1)')

    def test_missing_role_blocks_before_host(self):
        (self.root/'.agents/skills/fullstack-mvp-engineer/SKILL.md').unlink()
        with patch.object(h,'generate') as generate:
            self.assertEqual(self.run_plan()['status'],'failed');generate.assert_not_called()

    def test_two_host_failures_not_reset_by_workflow_name(self):
        with patch.object(h,'generate',side_effect=ValueError('host unavailable')) as generate:
            self.run_plan();self.run_plan();self.plan['id']='other-demo'
            result=self.run_plan();self.assertIn('Two attempts',result['blocker']);self.assertEqual(generate.call_count,2)

    def test_symlink_output_rejected_before_any_write(self):
        (self.root/'private.txt').write_text('private');(self.root/'src').mkdir();(self.root/'src/a.py').symlink_to(self.root/'private.txt')
        with patch.object(h,'generate',return_value=({'src/a.py':'changed'},{'host':'codex'})):
            self.assertEqual(self.run_plan()['status'],'failed')
        self.assertEqual((self.root/'private.txt').read_text(),'private')

    def test_input_changes_during_generation_reject_output(self):
        def generate(*args):
            (self.root/'task.md').write_text('changed');return {'src/a.py':'print(1)'},{'host':'codex'}
        with patch.object(h,'generate',side_effect=generate):self.assertEqual(self.run_plan()['status'],'failed')
        self.assertFalse((self.root/'src/a.py').exists())

    def test_output_plan_alias_rejected(self):
        self.plan['steps'][0]['outputs']=['nested/../workflow.json']
        with self.assertRaisesRegex(ValueError,'overwrite the plan'):self.run_plan()

    def test_output_aliases_cannot_share_owner(self):
        self.plan['steps'][0]['outputs']=['src/a.py','src/../src/a.py']
        with self.assertRaisesRegex(ValueError,'one owner'):self.run_plan()

    def test_unknown_host_rejected(self):
        self.plan['steps'][0]['host']='unknown'
        with self.assertRaises(ValueError):self.run_plan()

    def test_prompt_reads_selected_project_only(self):
        with tempfile.TemporaryDirectory() as other:
            (Path(other)/'task.md').write_text('FOREIGN PRIVATE TEXT')
            prompt=h.build_prompt(self.root,self.plan['steps'][0],'ar')
        self.assertIn('Implement a bounded feature',prompt);self.assertIn('"language": "ar"',prompt)
        self.assertNotIn('FOREIGN PRIVATE TEXT',prompt)


if __name__=='__main__':unittest.main()
