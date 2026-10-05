"""The native command must emit the supported host protocol, not internal callback metadata."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle as lifecycle
import test_native_lifecycle_acceptance_boundaries as fixtures

class NativeWireBoundaries(unittest.TestCase):
    def invoke(self,event,extra=None):
        case=fixtures.NativeLifecycleBoundaries();case.setUp();self.addCleanup(case.doCleanups)
        record=case.install()
        payload={'cwd':str(case.root),'session_id':'wire-session','turn_id':'wire-turn',
                 'hook_event_name':event}
        payload.update(extra or {})
        with patch.object(sys,'stdin',io.StringIO(json.dumps(payload))), \
             contextlib.redirect_stdout(io.StringIO()) as stream:
            result=lifecycle.main(['event','--project',str(case.root),'--project-id','native-boundary',
                '--host','codex','--event',event,'--config-sha',record['payload_sha256']])
        self.assertEqual(result,0)
        return json.loads(stream.getvalue()),record

    def test_prompt_injection_uses_hook_specific_output(self):
        document,record=self.invoke('UserPromptSubmit')
        self.assertEqual(set(document),{'hookSpecificOutput'})
        hook=document['hookSpecificOutput']
        self.assertEqual(hook['hookEventName'],'UserPromptSubmit')
        self.assertIn(record['marker'],hook['additionalContext'])
        self.assertIn('Output VALUE must equal one.',hook['additionalContext'])

    def test_prepare_does_not_emit_unsupported_internal_metadata(self):
        document,_=self.invoke('SessionStart')
        self.assertEqual(document,{})

    def test_guard_denial_emits_only_the_supported_decision(self):
        document,_=self.invoke('PreToolUse',{'tool_name':'apply_patch','tool_input':{
            'command':'*** Begin Patch\n*** Add File: .crewloom/authority.json\n+{}\n*** End Patch\n'}})
        self.assertEqual(set(document),{'hookSpecificOutput'})
        self.assertEqual(document['hookSpecificOutput']['hookEventName'],'PreToolUse')
        self.assertEqual(document['hookSpecificOutput']['permissionDecision'],'deny')

if __name__=='__main__':unittest.main()
