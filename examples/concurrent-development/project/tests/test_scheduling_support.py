"""Frozen fixture tests for the reused task-field validation helper.

These pin the identifier, priority and dependency rules the generated planning module must
build on: a boolean is never a priority, an identifier is never a path, and a repeated
dependency is refused before any ordering happens.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import scheduling_support as support  # noqa: E402


class IdentifierTests(unittest.TestCase):
    def test_lowercase_identifiers_pass(self):
        for value in ('a', 'collect-invoices', 't0', 'x' * 32):
            self.assertEqual(support.check_id(value), value)

    def test_paths_uppercase_and_overlong_identifiers_are_refused(self):
        for value in ('../foreign', 'A', '1task', 'x' * 33, '', None, 5):
            with self.assertRaises(ValueError):
                support.check_id(value)

    def test_the_field_name_is_part_of_the_refusal(self):
        with self.assertRaisesRegex(ValueError, 'task 3 id'):
            support.check_id('Bad', 'task 3 id')


class PriorityTests(unittest.TestCase):
    def test_an_omitted_priority_is_zero_and_the_bounds_are_inclusive(self):
        self.assertEqual(support.check_priority(None), 0)
        self.assertEqual(support.check_priority(-9), -9)
        self.assertEqual(support.check_priority(9), 9)

    def test_a_boolean_is_never_a_priority(self):
        for value in (True, False):
            with self.assertRaises(ValueError):
                support.check_priority(value)

    def test_wrong_types_and_out_of_range_values_are_refused(self):
        for value in ('5', 5.0, [1], 10, -10):
            with self.assertRaises(ValueError):
                support.check_priority(value)


class DependencyTests(unittest.TestCase):
    def test_an_omitted_value_is_an_empty_tuple(self):
        self.assertEqual(support.check_dependencies(None), ())

    def test_order_is_preserved_and_a_repeat_is_refused(self):
        self.assertEqual(support.check_dependencies(['b', 'a']), ('b', 'a'))
        with self.assertRaisesRegex(ValueError, 'repeats a'):
            support.check_dependencies(['a', 'a'])

    def test_a_non_list_is_refused(self):
        for value in ('a', {'a': True}, 1):
            with self.assertRaises(ValueError):
                support.check_dependencies(value)


if __name__ == '__main__':
    unittest.main()