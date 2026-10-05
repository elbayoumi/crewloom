"""A new native installation cannot inherit delivery proof from the old contract."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle as lifecycle
import project_binding
import test_native_lifecycle_acceptance_boundaries as fixtures

class NativeReinstallBoundaries(unittest.TestCase):
    def test_changed_installation_requires_new_observed_delivery(self):
        case=fixtures.NativeLifecycleBoundaries();case.setUp();self.addCleanup(case.doCleanups)
        with patch.object(lifecycle,'_version_of',return_value='1.18.32'):
            before=lifecycle.install(case.root,'native-boundary','opencode','context-guardian',
                criteria_path='criteria.md',sources=['src/output.py'],declared_outputs=['src/output.py'])
            result=lifecycle.callback(case.root,'native-boundary','opencode','inject',
                {'cwd':str(case.root),'session_id':'old-session','turn_id':'old-turn'},config_sha=before['payload_sha256'])
            self.assertTrue(result['injected'])
            project_binding.cancel(case.root,'native-boundary',result['task_id'],'Completed fixture turn')
            (case.root/'src/another.py').write_text('VALUE=2\n')
            after=lifecycle.install(case.root,'native-boundary','opencode','context-guardian',
                criteria_path='criteria.md',sources=['src/output.py'],
                declared_outputs=['src/output.py','src/another.py'])
        self.assertNotEqual(before['declared_outputs'],after['declared_outputs'])
        report=lifecycle.status(case.root,'native-boundary','opencode')
        self.assertTrue(report['config_ready'])
        self.assertFalse(report['delivered'])
        self.assertEqual(report['observed_callbacks'],0)
        self.assertFalse(report['verified_executor'])

if __name__=='__main__':unittest.main()
