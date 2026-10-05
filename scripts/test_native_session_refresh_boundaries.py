"""A later task in the same native session must not reuse completed stale context."""
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle as lifecycle
import test_host_lifecycle as fixtures

class NativeSessionRefreshBoundaries(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','explicit real Docker acceptance opt-in')
    def test_completed_session_task_does_not_freeze_later_turns(self):
        case=fixtures.Fixture();case.setUp();self.addCleanup(case.doCleanups)
        record=case.install_default()
        first=lifecycle.callback(case.root,fixtures.PROJECT,'codex','UserPromptSubmit',
            case.payload(),config_sha=record['payload_sha256'])
        complete=lifecycle.callback(case.root,fixtures.PROJECT,'codex','Stop',
            case.payload(),config_sha=record['payload_sha256'])
        self.assertTrue(complete['verified'],complete)
        source=case.root/fixtures.SOURCE_FILE
        source.write_text(source.read_text()+'\n# NEW_NATIVE_TURN_SOURCE\n')
        second=lifecycle.callback(case.root,fixtures.PROJECT,'codex','UserPromptSubmit',
            case.payload(turn_id='turn-2'),config_sha=record['payload_sha256'])
        self.assertEqual(second['task_state'],'active')
        self.assertNotEqual(second['task_id'],first['task_id'])
        self.assertIn('NEW_NATIVE_TURN_SOURCE',second['additionalContext'])
        self.assertNotEqual(second['context_semantic_sha256'],first['context_semantic_sha256'])

if __name__=='__main__':unittest.main()
