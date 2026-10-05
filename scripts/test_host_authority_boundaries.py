"""Frozen acceptance: declaring native host policy must not authorize changing it."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import workflow
import host_lifecycle
import test_native_lifecycle_acceptance_boundaries as fixtures

class HostAuthorityBoundaries(unittest.TestCase):
    def test_project_root_host_configuration_remains_protected(self):
        case=fixtures.NativeLifecycleBoundaries();case.setUp();self.addCleanup(case.doCleanups)
        for name in ('opencode.json','opencode.jsonc','OPENCODE.JSONC'):
            with self.subTest(path=name):
                with self.assertRaises(ValueError):
                    host_lifecycle.guard_file_edits(case.root,case.guard_record([name]),
                        '*** Begin Patch\n*** Add File: '+name+'\n+{}\n*** End Patch\n')

    def test_managed_artifacts_cannot_modify_native_host_authority(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            for name in ('opencode.json','opencode.jsonc','.codex/config.toml',
                         '.claude/settings.json','.opencode/plugins/guard.js',
                         '.CODEX/config.toml','OPENCODE.JSON'):
                with self.subTest(path=name):
                    with self.assertRaises(ValueError):workflow.declared_path(root,name)

    def test_ordinary_project_configuration_is_still_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            self.assertEqual(workflow.declared_path(root,'src/settings.json'),root/'src/settings.json')

if __name__=='__main__':unittest.main()
