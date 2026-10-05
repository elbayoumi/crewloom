"""Installation is never proof that a host received injected context."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle
import test_native_lifecycle_acceptance_boundaries as fixtures

class NativeDeliveryBoundaries(unittest.TestCase):
    def test_opencode_plugin_installation_does_not_claim_observed_delivery(self):
        case=fixtures.NativeLifecycleBoundaries();case.setUp();self.addCleanup(case.doCleanups)
        with patch.object(host_lifecycle,'_version_of',return_value='1.18.32'):
            host_lifecycle.install(case.root,'native-boundary','opencode','context-guardian',
                criteria_path='criteria.md',sources=['src/output.py'],declared_outputs=['src/output.py'])
        status=host_lifecycle.status(case.root,'native-boundary','opencode')
        self.assertTrue(status['config_ready'])
        self.assertEqual(status['observed_callbacks'],0)
        self.assertFalse(status['delivered'])

if __name__=='__main__':unittest.main()
