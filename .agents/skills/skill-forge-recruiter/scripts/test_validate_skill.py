"""Validate bilingual procedures without relaxing structural requirements."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_skill


class SkillLanguageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / '.agents' / 'skills' / 'sample-skill'
        (self.base / 'brain').mkdir(parents=True)
        for filename in validate_skill.BRAIN_FILES:
            (self.base / 'brain' / filename).write_text('# Memory\n', encoding='utf-8')
        context = patch.object(validate_skill, 'REPO', self.root)
        context.start()
        self.addCleanup(context.stop)

    def write_skill(self, sections):
        text = ('---\nname: sample-skill\ndescription: A bounded example skill\n---\n'
                + sections + '\n' + 'Read the architecture and record the task outcome. ' * 8)
        (self.base / 'SKILL.md').write_text(text, encoding='utf-8')

    def test_english_procedure_is_accepted(self):
        self.write_skill('# Brain\n# When to use')
        self.assertEqual(validate_skill.check('sample-skill'), [])

    def test_arabic_procedure_is_accepted(self):
        self.write_skill('# بروتوكول البرين\n# متى تستخدم')
        self.assertEqual(validate_skill.check('sample-skill'), [])

    def test_mixed_language_procedure_is_accepted(self):
        self.write_skill('# البرين\n# Triggers')
        self.assertEqual(validate_skill.check('sample-skill'), [])

    def test_missing_memory_section_is_rejected(self):
        self.write_skill('# When to use')
        self.assertTrue(any('Brain / working memory' in e for e in validate_skill.check('sample-skill')))

    def test_missing_activation_section_is_rejected(self):
        self.write_skill('# Brain')
        self.assertTrue(any('When to use / triggers' in e for e in validate_skill.check('sample-skill')))

    def test_missing_brain_file_is_rejected(self):
        self.write_skill('# Brain\n# When to use')
        (self.base / 'brain' / 'CHALLENGES.md').unlink()
        self.assertIn('missing brain/CHALLENGES.md', validate_skill.check('sample-skill'))

    def test_machine_local_path_is_rejected(self):
        self.write_skill('# Brain\n# When to use\n/Users/example/private')
        self.assertIn('machine-local path in SKILL.md', validate_skill.check('sample-skill'))


if __name__ == '__main__':
    unittest.main()
