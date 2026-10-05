"""Declaring a host configuration file must not permit disabling its own guards."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle as lifecycle
import test_native_lifecycle_acceptance_boundaries as fixtures


class NativeHostConfigBoundaries(unittest.TestCase):
    def test_all_host_configuration_trees_remain_protected_when_declared(self):
        case=fixtures.NativeLifecycleBoundaries();case.setUp();self.addCleanup(case.doCleanups)
        for name in ('.codex/config.toml','.opencode/opencode.json','.opencode/plugins/foreign.js','.claude/settings.json'):
            with self.subTest(path=name):
                with self.assertRaises(ValueError):
                    lifecycle.guard_file_edits(case.root,case.guard_record([name]),
                        '*** Begin Patch\n*** Add File: '+name+'\n+disable_guard=true\n*** End Patch\n')


if __name__=='__main__':
    unittest.main()
