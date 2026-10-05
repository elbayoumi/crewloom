"""Invoice records as stored by the billing provider, plus statement rendering.

This module already refuses anything the money helpers refuse, so the grouping
in ``src/ledger.py`` only has to organise records it is handed instead of
re-deciding what a valid amount is.
"""
import json

from src.money import format_amount, parse_amount

RECORD_FIELDS = ('amount', 'category', 'currency')


def decode_line(line):
    """One stored invoice line as a record with a parsed exact amount."""
    record = json.loads(line)
    if not isinstance(record, dict) or set(record) != set(RECORD_FIELDS):
        raise ValueError('stored invoice line has unexpected fields')
    return {'amount': parse_amount(record['amount']), 'category': record['category'],
            'currency': record['currency']}


def decode_export(text):
    """Decode a newline-delimited export, preserving the stored order."""
    return [decode_line(line) for line in text.splitlines() if line.strip()]


def statement(summary):
    """Render finished summary entries as one accounting line each."""
    return '\n'.join([entry['total'] + ' ' + entry['currency'] + ' ' + entry['category']
                      for entry in summary])


def refund(record, amount):
    """A negative record for the same currency and category as an original."""
    if not isinstance(amount, str):
        raise TypeError('refund amount must be a string')
    return {'amount': '-' + amount.lstrip('-'), 'category': record['category'],
            'currency': record['currency']}


def total_of_records(records):
    """Sum already-parsed amounts; kept here so callers share one accumulation."""
    from src.money import total_of
    return total_of([record['amount'] for record in records])


def render_totals(groups):
    """Format one amount per group entry that still carries a Decimal total."""
    return [format_amount(group['total']) for group in groups]