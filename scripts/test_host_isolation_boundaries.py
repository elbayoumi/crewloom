"""Independent child-process profile and exact prompt transport, no provider calls."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import model_host as h
import test_transport_acceptance_boundaries as fixtures
class HostIsolationBoundaries(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
 def test_opencode_command_uses_the_actual_tool_free_run_flags(self):
  argv=h.command('opencode','fixture-opencode',self.root,'opencode/space-bunny-free',prompt='unique prompt')
  self.assertEqual(argv[:2],['fixture-opencode','run']);self.assertIn('--pure',argv);self.assertIn('--agent',argv);self.assertIn('--format',argv);self.assertEqual(argv.count('unique prompt'),1)
  profile=__import__('json').loads((self.root/'opencode.json').read_text());self.assertEqual(profile['permission']['*'],'deny');self.assertFalse(profile['tools']['skill'])
 def test_child_configuration_override_does_not_repurpose_authentication_home(self):
  profile=self.root/'opencode.json';profile.write_text('{}');env=h.opencode_environment(self.root,profile)
  self.assertNotIn('HOME',env);self.assertNotIn('CODEX_HOME',env);self.assertTrue(Path(env['XDG_CONFIG_HOME']).is_relative_to(self.root));self.assertEqual(env['OPENCODE_CONFIG'],str(profile))
 def test_generate_delivers_the_opencode_prompt_exactly_once_and_reports_real_unknown_model(self):
  calls=[];prompt='one uniquely identifiable complete task prompt'
  class Process:
   def __init__(self,argv,**kwargs):
    self.returncode=0;self.pid=123456;calls.append({'argv':argv,'env':kwargs['env'],'input':[]})
    kwargs['stdout'].write(fixtures.stream(fixtures.text(),fixtures.finish())+'\n');kwargs['stdout'].flush()
   def communicate(self,value=None,timeout=None):calls[-1]['input'].append(value);return ('','')
  info={'host':'opencode','executable':'fixture-opencode','version':'1.18.32','generation_supported':True,'authentication_verified':False}
  with patch.object(h,'probe',return_value=info),patch.object(h.subprocess,'Popen',Process):
   artifacts,evidence=h.generate('opencode',prompt,['src/result.py'],model='opencode/space-bunny-free')
  self.assertEqual(artifacts,{'src/result.py':'VALUE = 1\n'});self.assertEqual(calls[0]['argv'].count(prompt),1);self.assertEqual(calls[0]['input'],[None]);self.assertEqual(calls[0]['env'].get('HOME'),os.environ.get('HOME'));self.assertEqual(calls[0]['env'].get('CODEX_HOME'),os.environ.get('CODEX_HOME'));self.assertIsNone(evidence['model_reported']);self.assertEqual(evidence['prompt_bytes'],len(prompt.encode()))
 def test_codex_generation_builder_keeps_hooks_and_execution_tools_disabled(self):
  argv=h.command('codex','fixture-codex',self.root,'gpt-6-sol',prompt='complete prompt')
  for flag in ('features.hooks=false','features.plugins=false','features.shell_tool=false','features.code_mode_host=false','features.apps=false'):self.assertIn(flag,argv)
  self.assertIn('--ignore-user-config',argv);self.assertIn('--ephemeral',argv);self.assertEqual(argv[-1],'-')
if __name__=='__main__':unittest.main()
