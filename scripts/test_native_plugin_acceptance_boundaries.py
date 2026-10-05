"""Supervisor checks the shipped OpenCode callback bridge without provider calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]
BRIDGE='''import json,os,sys
stage=sys.argv[sys.argv.index('--stage')+1]
payload=json.load(sys.stdin)
if stage=='prepare' and os.environ.get('CREWLOOM_FIXTURE_REFUSE_PREPARE')=='1':
    print(json.dumps({'error':'scope refused'}))
elif stage=='inject':
    print(json.dumps({'additionalContext':'callback-only-marker'}))
elif stage=='guard':
    print(json.dumps({'permissionDecision':'deny','permissionDecisionReason':'outside declared outputs'}))
else:
    print(json.dumps({'status':'prepared','forwarded_pythonpath':os.environ.get('PYTHONPATH')}))
'''


@unittest.skipUnless(shutil.which('node'),'Node is required to exercise the real plugin callbacks')
class NativePluginBoundaries(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.project=Path(temporary.name).resolve()
        bridge=self.project/'bridge.py';bridge.write_text(BRIDGE,encoding='utf-8')
        source=(ROOT/'adapters/opencode/crewloom-lifecycle.js').read_text(encoding='utf-8')
        substitutions={'__CREWLOOM_BRIDGE_ARGV__':json.dumps([sys.executable,str(bridge)]),
                       '__CREWLOOM_ROOT__':json.dumps(str(self.project)),
                       '__CREWLOOM_PROJECT_ID__':json.dumps('plugin-boundary'),
                       '__CREWLOOM_CONFIG_SHA__':json.dumps('a'*64)}
        for key,value in substitutions.items():source=source.replace(key,value)
        (self.project/'plugin.mjs').write_text(source,encoding='utf-8')

    def node(self,body,extra=None):
        program="import { CrewloomLifecycle } from './plugin.mjs';\nconst hooks=await CrewloomLifecycle({directory:process.cwd(),worktree:process.cwd()});\n"+body
        env=dict(os.environ);env.update(extra or {})
        result=subprocess.run([shutil.which('node'),'--input-type=module','-e',program],
                              cwd=str(self.project),env=env,capture_output=True,text=True,timeout=15)
        return result

    def assert_refused(self,body):
        result=self.node(body)
        self.assertNotEqual(result.returncode,0,'Unsupported scope silently bypassed the callback: '+result.stdout)

    def test_missing_turn_identity_cannot_silently_skip_prepare(self):
        self.assert_refused("await hooks['chat.message']({sessionID:'s'},{});")

    def test_missing_session_cannot_silently_skip_context_injection(self):
        self.assert_refused("await hooks['experimental.chat.system.transform']({}, {system:[]});")

    def test_unknown_session_cannot_silently_skip_context_injection(self):
        self.assert_refused("await hooks['experimental.chat.system.transform']({sessionID:'unprepared'}, {system:[]});")

    def test_prepare_refusal_stops_generation_before_injection(self):
        result=self.node("await hooks['chat.message']({sessionID:'s',messageID:'t'},{});",
                         {'CREWLOOM_FIXTURE_REFUSE_PREPARE':'1'})
        self.assertNotEqual(result.returncode,0,'The plugin ignored an explicit bridge refusal')

    def test_known_session_receives_context(self):
        result=self.node("await hooks['chat.message']({sessionID:'s',messageID:'t'},{}); const output={system:[]}; await hooks['experimental.chat.system.transform']({sessionID:'s'},output); console.log(JSON.stringify(output));")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['system'],['callback-only-marker'])

    def test_explicit_guard_deny_is_thrown_to_the_host(self):
        result=self.node("await hooks['chat.message']({sessionID:'s',messageID:'t'},{}); await hooks['tool.execute.before']({sessionID:'s',callID:'c',tool:'bash'},{args:{command:'arbitrary command'}});")
        self.assertNotEqual(result.returncode,0)
        self.assertIn('outside declared outputs',result.stderr)


if __name__=='__main__':
    unittest.main()
