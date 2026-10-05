"""Invoice arithmetic for the ledgerline report.

Every amount crosses this module as an exact :class:`decimal.Decimal`, parsed by the
shared ``money`` helper, so a float can never reach a running sum. The rounding rule is
deliberate and asymmetric:

* a currency group's tax is the **quantized sum of the unrounded per-line taxes**, so one
  rounding decision happens per group;
* ``per_line_tax`` reports what quantizing each line first would have produced, and the
  report keeps both numbers so the difference is visible instead of implied.

A refund is a negative amount, never a signed quantity: the ``refund`` category negates an
otherwise positive line, so ``quantity`` and ``unit_price`` stay positive and a negative
amount without that category is refused.
"""
from decimal import Decimal

from money import format_amount, parse_amount, quantize

CURRENCIES = ('EUR', 'SAR', 'USD')
CATEGORIES = ('hardware', 'refund', 'services', 'subscription')
LANGUAGES = ('ar', 'en')
MAX_QUANTITY = 10000
MAX_TAX_RATE = Decimal('100')
RATE_PLACES = 4

SECTION_TITLES = {
    'en': {'net': 'Net', 'tax': 'Tax', 'gross': 'Gross', 'per_line_tax': 'Tax rounded per line'},
    'ar': {'net': 'الصافي', 'tax': 'الضريبة', 'gross': 'الإجمالي',
           'per_line_tax': 'الضريبة مقرّبة لكل سطر'},
}
ROUNDING_POLICY = 'half-even, applied once to each currency group total'


def check_currency(value):
    """One supported ISO currency code, compared case-sensitively on purpose."""
    if not isinstance(value, str) or value not in CURRENCIES:
        raise ValueError('currency must be one of ' + ', '.join(CURRENCIES))
    return value


def check_category(value):
    """One supported invoice category."""
    if not isinstance(value, str) or value not in CATEGORIES:
        raise ValueError('category must be one of ' + ', '.join(CATEGORIES))
    return value


def check_language(value):
    """One supported report language."""
    if not isinstance(value, str) or value not in LANGUAGES:
        raise ValueError('language must be one of ' + ', '.join(LANGUAGES))
    return value


def _quantity(line, index):
    value = line.get('quantity')
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('line ' + str(index) + ' quantity must be an integer')
    if not 1 <= value <= MAX_QUANTITY:
        raise ValueError('line ' + str(index) + ' quantity must be from 1 to ' + str(MAX_QUANTITY))
    return value


def _unit_price(line, index, category):
    value = parse_amount(line.get('unit_price'), 'line ' + str(index) + ' unit_price')
    if value <= 0:
        raise ValueError('line ' + str(index) + ' unit_price must be positive; a negative amount '
                         'belongs in the refund category')
    return value


def _tax_rate(line, index):
    value = quantize(parse_amount(line.get('tax_rate', '0'), 'line ' + str(index) + ' tax_rate'),
                     RATE_PLACES)
    if value < 0 or value > MAX_TAX_RATE:
        raise ValueError('line ' + str(index) + ' tax_rate must be from 0 to 100')
    return value


def _text(line, field, index):
    value = line.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError('line ' + str(index) + ' needs a nonempty ' + field)
    return value


def line_amounts(line, index):
    """Exact unrounded ``net``/``tax``/``gross`` decimals for one validated line."""
    if not isinstance(line, dict):
        raise ValueError('line ' + str(index) + ' must be an object')
    category = check_category(line.get('category'))
    check_currency(line.get('currency'))
    quantity = _quantity(line, index)
    unit_price = _unit_price(line, index, category)
    rate = _tax_rate(line, index)
    sign = -1 if category == 'refund' else 1
    net = Decimal(sign) * unit_price * quantity
    tax = net * rate.scaleb(-2)
    return {'currency': line['currency'], 'category': category, 'quantity': quantity,
            'unit_price': unit_price, 'tax_rate': rate, 'net': net, 'tax': tax,
            'gross': net + tax}


def _invoice_id(invoice):
    value = invoice.get('invoice_id')
    if not isinstance(value, str) or not value.strip():
        raise ValueError('invoice needs a nonempty invoice_id')
    return value.strip()


def _language(invoice):
    value = invoice.get('language', 'en')
    return check_language(value)


def compute_invoice(invoice):
    """One invoice summary: localized line rows and one quantized total per currency.

    Amounts are returned as fixed-scale decimal strings, never as floats, so a consumer
    never has to guess the scale or re-round a value it only wanted to print.
    """
    if not isinstance(invoice, dict):
        raise ValueError('invoice must be an object')
    language = _language(invoice)
    lines = invoice.get('lines')
    if not isinstance(lines, list) or not lines:
        raise ValueError('invoice needs a nonempty lines list')
    rows = []
    groups = {}
    for index, line in enumerate(lines, start=1):
        amounts = line_amounts(line, index)
        currency = amounts['currency']
        group = groups.setdefault(currency, {'net': Decimal(0), 'tax': Decimal(0),
                                             'gross': Decimal(0), 'per_line_tax': Decimal(0)})
        for field in ('net', 'tax', 'gross'):
            group[field] += amounts[field]
        group['per_line_tax'] += quantize(amounts['tax'])
        rows.append({'index': index,
                     'description_en': _text(line, 'description_en', index),
                     'description_ar': _text(line, 'description_ar', index),
                     'label': _text(line, 'description_' + language, index),
                     'currency': currency, 'category': amounts['category'],
                     'quantity': amounts['quantity'],
                     'net': format_amount(amounts['net']),
                     'tax': format_amount(amounts['tax']),
                     'gross': format_amount(amounts['gross'])})
    by_currency = {}
    for currency in sorted(groups):
        group = groups[currency]
        by_currency[currency] = {'net': format_amount(group['net']),
                                 'tax': format_amount(group['tax']),
                                 'gross': format_amount(group['gross']),
                                 'per_line_tax': format_amount(group['per_line_tax'])}
    return {'invoice_id': _invoice_id(invoice), 'language': language,
            'titles': dict(SECTION_TITLES[language]),
            'rounding': ROUNDING_POLICY, 'lines': rows, 'by_currency': by_currency,
            'single_currency': len(by_currency) == 1,
            'currencies': sorted(groups)}