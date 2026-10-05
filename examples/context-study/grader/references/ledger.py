"""Invoice totals grouped by currency and category."""
import unicodedata

from src.money import format_amount, parse_amount, total_of


def _category(value):
    if not isinstance(value, str):
        raise ValueError('category must be a string')
    text = unicodedata.normalize('NFKC', value).strip().casefold()
    if not text:
        raise ValueError('category must stay nonempty')
    return text


def _currency(value):
    if not isinstance(value, str):
        raise ValueError('currency must be a string')
    text = value.strip().upper()
    if len(text) != 3 or not all('A' <= letter <= 'Z' for letter in text):
        raise ValueError('currency must be three ASCII letters')
    return text


def summarize(records):
    """Group exact invoice totals by currency and category."""
    if not isinstance(records, list):
        raise TypeError('records must be a list')
    groups = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('each record must be an object')
        amount = parse_amount(record.get('amount'), 'amount')
        key = (_currency(record.get('currency')), _category(record.get('category')))
        groups.setdefault(key, []).append(amount)
    return [{'currency': currency, 'category': category, 'total': format_amount(total_of(amounts))}
            for (currency, category), amounts in sorted(groups.items())]
