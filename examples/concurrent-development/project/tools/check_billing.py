#!/usr/bin/env python3
"""Acceptance for the generated invoice module.

Runs inside the task's own container with a declared-input snapshot, so the module under
test is exactly the bytes the generation step produced. Every case is a numeric or
structural fact about the module's behaviour; nothing here reads a marker string out of the
source and calls it a pass.

    python3 tools/check_billing.py
"""
import hashlib
import importlib
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, 'src')

MODULE = 'src/billing.py'
HELPER = 'src/money.py'
OUT = 'artifacts/billing_acceptance.json'

billing = importlib.import_module('billing')


def sha256(relative):
    return hashlib.sha256(Path(relative).read_bytes()).hexdigest()


def invoice(**changes):
    """A minimal valid invoice, deep-copied so one case cannot alter another's input."""
    base = {'invoice_id': 'INV-CASE', 'language': 'en', 'lines': [
        {'description_en': 'Line one', 'description_ar': 'سطر أول', 'currency': 'EUR',
         'category': 'services', 'quantity': 2, 'unit_price': '10.00', 'tax_rate': '10'}]}
    base.update(deepcopy(changes))
    return base


def rounded_tax_case():
    """Two lines whose tax is exactly 0.005: per-line half-even gives 0.00, the group gives 0.01."""
    document = invoice(lines=[
        {'description_en': 'Half A', 'description_ar': 'نصف أ', 'currency': 'EUR',
         'category': 'services', 'quantity': 1, 'unit_price': '1.00', 'tax_rate': '0.5'},
        {'description_en': 'Half B', 'description_ar': 'نصف ب', 'currency': 'EUR',
         'category': 'services', 'quantity': 1, 'unit_price': '1.00', 'tax_rate': '0.5'}])
    group = billing.compute_invoice(document)['by_currency']['EUR']
    return {'tax': group['tax'], 'per_line_tax': group['per_line_tax']}


def refund_case():
    """A refund is a negative line: it reduces the net, the tax and the gross of its group."""
    document = invoice(lines=[
        {'description_en': 'Subscription', 'description_ar': 'اشتراك', 'currency': 'EUR',
         'category': 'subscription', 'quantity': 1, 'unit_price': '100.00', 'tax_rate': '15'},
        {'description_en': 'Refund', 'description_ar': 'استرداد', 'currency': 'EUR',
         'category': 'refund', 'quantity': 1, 'unit_price': '40.00', 'tax_rate': '15'}])
    summary = billing.compute_invoice(document)
    return {'net': summary['by_currency']['EUR']['net'], 'tax': summary['by_currency']['EUR']['tax'],
            'gross': summary['by_currency']['EUR']['gross'],
            'refund_row_net': summary['lines'][1]['net']}


def sample_case():
    """The frozen sample document: real totals for the three declared lines."""
    document = json.loads(Path('data/ledger_en.json').read_text(encoding='utf-8'))['invoice']
    summary = billing.compute_invoice(document)
    return {'currencies': summary['currencies'], 'single_currency': summary['single_currency'],
            'net': summary['by_currency']['USD']['net'], 'tax': summary['by_currency']['USD']['tax'],
            'gross': summary['by_currency']['USD']['gross'],
            'per_line_tax': summary['by_currency']['USD']['per_line_tax'],
            'rows': [[row['net'], row['tax'], row['gross']] for row in summary['lines']]}


def mixed_currency_case():
    """Two currencies in one invoice: each is totalled separately and there is no single total."""
    document = invoice(lines=[
        {'description_en': 'Euro', 'description_ar': 'أورو', 'currency': 'EUR',
         'category': 'services', 'quantity': 1, 'unit_price': '20.00', 'tax_rate': '0'},
        {'description_en': 'Riyal', 'description_ar': 'ريال', 'currency': 'SAR',
         'category': 'services', 'quantity': 1, 'unit_price': '100.00', 'tax_rate': '0'}])
    summary = billing.compute_invoice(document)
    return {'currencies': summary['currencies'], 'single_currency': summary['single_currency'],
            'eur_net': summary['by_currency']['EUR']['net'],
            'sar_net': summary['by_currency']['SAR']['net']}


def arabic_case():
    """One document, one report language: the Arabic label is chosen from the invoice language."""
    document = invoice(language='ar')
    summary = billing.compute_invoice(document)
    return {'language': summary['language'], 'label': summary['lines'][0]['label'],
            'titles': summary['titles']['net'], 'english_row_present':
                summary['lines'][0]['description_en'] == 'Line one'}


def empty_case():
    """An empty invoice is refused rather than reported as zero."""
    try:
        billing.compute_invoice(invoice(lines=[]))
    except ValueError as exc:
        return {'refused': 'lines' in str(exc)}
    return {'refused': False}


CASES = (
    ('group_tax_rounds_once', rounded_tax_case, {'tax': '0.01', 'per_line_tax': '0.00'}),
    ('refund_reduces_its_currency_group', refund_case,
     {'net': '60.00', 'tax': '9.00', 'gross': '69.00', 'refund_row_net': '-40.00'}),
    ('frozen_sample_totals', sample_case,
     {'currencies': ['USD'], 'single_currency': True, 'net': '2588.01', 'tax': '388.33',
      'gross': '2976.34', 'per_line_tax': '388.33',
      'rows': [['588.00', '88.20', '676.20'], ['2500.01', '375.13', '2875.14'],
               ['-500.00', '-75.00', '-575.00']]}),
    ('mixed_currency_has_no_single_total', mixed_currency_case,
     {'currencies': ['EUR', 'SAR'], 'single_currency': False, 'eur_net': '20.00',
      'sar_net': '100.00'}),
    ('arabic_language_selects_arabic_labels', arabic_case,
     {'language': 'ar', 'label': 'سطر أول', 'titles': 'الصافي', 'english_row_present': True}),
    ('an_empty_invoice_is_refused', empty_case, {'refused': True}),
)


def refusals():
    """Every input the contract names as invalid must raise ValueError, with the field named."""
    def mutate(**changes):
        document = invoice()
        document['lines'][0].update(changes)
        return document

    checks = (
        ('unknown_currency_is_refused', invoice(lines=[dict(invoice()['lines'][0],
                                                           currency='CHF')]), 'currency'),
        ('lowercase_currency_is_refused', invoice(lines=[dict(invoice()['lines'][0],
                                                             currency='usd')]), 'currency'),
        ('unknown_category_is_refused', invoice(lines=[dict(invoice()['lines'][0],
                                                           category='discount')]), 'category'),
        ('float_amount_is_refused', mutate(unit_price=10.5), 'unit_price'),
        ('non_finite_amount_is_refused', mutate(unit_price='NaN'), 'unit_price'),
        ('infinite_amount_is_refused', mutate(unit_price='Infinity'), 'unit_price'),
        ('negative_price_needs_the_refund_category', mutate(unit_price='-5.00'), 'unit_price'),
        ('boolean_quantity_is_refused', mutate(quantity=True), 'quantity'),
        ('zero_quantity_is_refused', mutate(quantity=0), 'quantity'),
        ('oversized_quantity_is_refused', mutate(quantity=10001), 'quantity'),
        ('tax_rate_above_one_hundred_is_refused', mutate(tax_rate='100.5'), 'tax_rate'),
        ('missing_description_is_refused', invoice(lines=[dict(invoice()['lines'][0],
                                                              description_ar='')]),
         'description_ar'),
        ('unknown_language_is_refused', invoice(language='fr'), 'language'),
        ('missing_invoice_id_is_refused', invoice(invoice_id=''), 'invoice_id'),
        ('a_line_that_is_not_an_object_is_refused', invoice(lines=['x']), 'must be an object'),
    )
    results = {}
    for name, document, expected in checks:
        try:
            billing.compute_invoice(document)
        except ValueError as exc:
            results[name] = expected in str(exc)
        else:
            results[name] = False
    return results


def main():
    cases = []
    for name, run, expected in CASES:
        try:
            observed = run()
        except Exception as exc:  # a case that raises where a value was expected is a failure
            observed = {'error': type(exc).__name__ + ': ' + str(exc)}
        cases.append({'name': name, 'expected': expected, 'observed': observed,
                      'ok': observed == expected})
    refused = refusals()
    for name in sorted(refused):
        cases.append({'name': name, 'expected': True, 'observed': refused[name],
                      'ok': refused[name]})
    failed = [item['name'] for item in cases if not item['ok']]
    report = {'module': MODULE, 'source_sha256': sha256(MODULE), 'helper_sha256': sha256(HELPER),
              'case_count': len(cases), 'failed': failed, 'accepted': not failed,
              'cases': cases}
    target = Path(OUT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding='utf-8')
    if failed:
        print('billing acceptance failed: ' + ', '.join(failed), file=sys.stderr)
        return 1
    print('billing acceptance passed ' + str(len(cases)) + ' cases')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())