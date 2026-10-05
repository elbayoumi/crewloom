"""Frozen fixture tests for the reused exact-decimal money helper.

These ship with the project and are never generated: they pin the arithmetic the generated
invoice module is required to build on, so a generated module cannot quietly redefine
"half-even" or accept a float.
"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import money  # noqa: E402


class MoneyParsingTests(unittest.TestCase):
    def test_decimal_strings_parse_exactly(self):
        self.assertEqual(money.parse_amount('1250.005'), Decimal('1250.005'))
        self.assertEqual(money.parse_amount(' -12.50 '), Decimal('-12.50'))
        self.assertEqual(money.parse_amount('1.5e3'), Decimal('1500'))

    def test_floats_and_booleans_are_refused(self):
        for value in (10.5, True, None, 3, ['1.00']):
            with self.assertRaises(ValueError):
                money.parse_amount(value)

    def test_non_finite_and_malformed_text_is_refused(self):
        for value in ('NaN', 'Infinity', '-Infinity', '', '1,000.00', '1.2.3', 'ten'):
            with self.assertRaises(ValueError):
                money.parse_amount(value)

    def test_the_field_name_is_part_of_the_refusal(self):
        with self.assertRaisesRegex(ValueError, 'line 2 unit_price'):
            money.parse_amount('x', 'line 2 unit_price')


class MoneyRoundingTests(unittest.TestCase):
    def test_half_even_rounds_a_half_to_the_even_digit(self):
        self.assertEqual(money.quantize(Decimal('0.005')), Decimal('0.00'))
        self.assertEqual(money.quantize(Decimal('0.015')), Decimal('0.02'))
        self.assertEqual(money.quantize(Decimal('-0.005')), Decimal('0.00'))

    def test_a_group_sum_is_rounded_once_not_every_record(self):
        two_halves = [money.total_of([Decimal('0.005'), Decimal('0.005')])]
        self.assertEqual(money.quantize(*two_halves), Decimal('0.01'))
        per_line = sum(money.quantize(value) for value in (Decimal('0.005'), Decimal('0.005')))
        self.assertEqual(per_line, Decimal('0.00'))

    def test_formatting_keeps_the_scale_and_the_sign(self):
        self.assertEqual(money.format_amount(Decimal('0')), '0.00')
        self.assertEqual(money.format_amount(Decimal('2976.33650050')), '2976.34')
        self.assertEqual(money.format_amount(Decimal('-575')), '-575.00')
        self.assertEqual(money.format_amount(Decimal('1'), 4), '1.0000')


if __name__ == '__main__':
    unittest.main()