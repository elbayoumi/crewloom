"""Supervisor checks ownership and configuration preservation in native installation."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle as lifecycle
import test_native_lifecycle_acceptance_boundaries as fixtures


class NativeInstallerIntegrityBoundaries(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.NativeLifecycleBoundaries();self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root

    def test_unrelated_settings_and_foreign_hooks_remain_byte_equivalent_values(self):
        path=self.root/'.codex/hooks.json';path.parent.mkdir()
        foreign={'owner':'existing-tool','schema_version':7,'extension':{'enabled':True},
                 'hooks':{'SessionStart':[{'matcher':'startup','hooks':[{'type':'command','command':'echo existing-hook'}]}]}}
        path.write_text(json.dumps(foreign),encoding='utf-8')
        self.fixture.install();installed=json.loads(path.read_text())
        for key in ('owner','schema_version','extension'):
            self.assertEqual(installed[key],foreign[key],key)
        self.assertIn(foreign['hooks']['SessionStart'][0],installed['hooks']['SessionStart'])

    def test_missing_role_is_rejected_before_installation_writes(self):
        before=self.fixture.snapshot()
        with patch.object(lifecycle,'_version_of',return_value='codex-cli 0.155.1'):
            with self.assertRaises(ValueError):
                lifecycle.install(self.root,'native-boundary','codex','role-not-installed',
                    criteria_path='criteria.md',declared_outputs=['src/output.py'])
        self.assertEqual(self.fixture.snapshot(),before)

    def test_foreign_opencode_plugin_is_never_replaced(self):
        path=self.root/'.opencode/plugins/crewloom-lifecycle.js';path.parent.mkdir(parents=True)
        path.write_text('export const OtherPlugin = async () => ({});\n',encoding='utf-8')
        before=self.fixture.snapshot()
        with patch.object(lifecycle,'_version_of',return_value='1.18.32'):
            with self.assertRaises(ValueError):
                lifecycle.install(self.root,'native-boundary','opencode','context-guardian',
                    criteria_path='criteria.md',declared_outputs=['src/output.py'])
        self.assertEqual(self.fixture.snapshot(),before)


if __name__=='__main__':
    unittest.main()
