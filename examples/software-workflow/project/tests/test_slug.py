import unittest
from src.slug import slugify


class SlugAcceptance(unittest.TestCase):
    def test_english(self):
        self.assertEqual(slugify('  Hello, WORLD!  '), 'hello-world')

    def test_arabic(self):
        self.assertEqual(slugify('مرحبا بالعالم'), 'مرحبا-بالعالم')

    def test_compatibility_normalization(self):
        self.assertEqual(slugify('Ｆｏｏ １２３'), 'foo-123')

    def test_empty_and_punctuation(self):
        for value in ('', '---', '  '):
            self.assertEqual(slugify(value), '')

    def test_type_rejection(self):
        for value in (None, 123, []):
            with self.assertRaises(TypeError): slugify(value)
