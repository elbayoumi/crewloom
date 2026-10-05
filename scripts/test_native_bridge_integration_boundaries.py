"""The installed plugin must reach the real engine, not only a dummy JSON bridge."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle as lifecycle
import test_native_lifecycle_acceptance_boundaries as fixtures


@unittest.skipUnless(shutil.which('node'),'Node is required for the actual plugin-to-engine bridge')
class NativeBridgeIntegrationBoundaries(unittest.TestCase):
    def test_installed_opencode_plugin_injects_real_bound_context(self):
        case=fixtures.NativeLifecycleBoundaries();case.setUp();self.addCleanup(case.doCleanups)
        with patch.object(lifecycle,'_version_of',return_value='1.18.32'):
            lifecycle.install(case.root,'native-boundary','opencode','context-guardian',
                criteria_path='criteria.md',sources=['src/output.py'],declared_outputs=['src/output.py'])
        record=lifecycle.load_install(case.root,'opencode')
        path=case.root/record['control_relative']
        program="import { CrewloomLifecycle } from "+json.dumps(path.as_uri())+";\nconst hooks=await CrewloomLifecycle({directory:process.cwd(),worktree:process.cwd()});\nawait hooks['chat.message']({sessionID:'real-bridge-session',messageID:'real-bridge-turn'},{});\nconst output={system:[]};await hooks['experimental.chat.system.transform']({sessionID:'real-bridge-session'},output);console.log(JSON.stringify(output));"
        result=subprocess.run([shutil.which('node'),'--input-type=module','-e',program],
            cwd=str(case.root),capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        system=json.loads(result.stdout)['system']
        self.assertTrue(system,'The installed plugin supplied no context')
        self.assertIn('VALUE=1',system[-1])
        self.assertIn('native-boundary',system[-1])


if __name__=='__main__':
    unittest.main()
