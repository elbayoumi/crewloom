"""Independent project files must be rejected by the actual mandatory repository gate."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import check_repository as check


class RepositoryScopeBoundaries(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='crewloom-scope-acceptance-')
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        (self.root / 'LICENSE').write_text('Fixture license\n')
        skill = self.root / '.agents/skills/fixture'
        skill.mkdir(parents=True)
        (skill / 'SKILL.md').write_text('Fixture role\n')
        contract = Path(__file__).resolve().parents[1] / 'REPOSITORY_SCOPE.json'
        (self.root / 'REPOSITORY_SCOPE.json').write_bytes(contract.read_bytes())

    def inspect(self):
        # Keep the existing, unrelated role validator outside these scope fixtures.
        with patch.object(check, 'load_validator', return_value=SimpleNamespace(check=lambda name: [])):
            return check.inspect(self.root)

    def test_declared_toolkit_roots_are_accepted(self):
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/good.py').write_text('value = 1\n')
        self.assertEqual(self.inspect(), [])

    def test_independent_android_project_is_rejected(self):
        app = self.root / 'sms-forwarder'
        app.mkdir()
        (app / 'settings.gradle.kts').write_text('rootProject.name = "SMS"\n')
        self.assertTrue(self.inspect(), 'Mandatory gate accepted the unrelated Android project')

    def test_ignoring_a_foreign_project_does_not_register_it(self):
        (self.root / '.gitignore').write_text('sms-forwarder/\n')
        (self.root / 'sms-forwarder').mkdir()
        (self.root / 'sms-forwarder/settings.gradle.kts').write_text('rootProject.name = "SMS"\n')
        self.assertTrue(self.inspect(), 'Ignored independent project was accepted')

    def test_a_second_root_project_manifest_is_rejected(self):
        (self.root / 'package.json').write_text('{"name":"unrelated-app"}\n')
        self.assertTrue(self.inspect(), 'Unregistered root project manifest was accepted')

    def test_missing_scope_contract_is_refused(self):
        (self.root / 'REPOSITORY_SCOPE.json').unlink()
        self.assertTrue(self.inspect(), 'No project scope was accepted')

    def test_another_project_identity_is_refused(self):
        path = self.root / 'REPOSITORY_SCOPE.json'
        contract = json.loads(path.read_text())
        contract['project_id'] = 'sms-forwarder'
        path.write_text(json.dumps(contract))
        self.assertTrue(self.inspect(), 'A foreign project contract was accepted')


if __name__ == '__main__':
    unittest.main()
