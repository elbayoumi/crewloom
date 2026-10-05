"""The combined ledgerline report.

One report, two sections, one language. This module owns the shape of the output document and
the meaning of a section title; every number it prints is produced by the two modules this
batch generates alongside it, so a wrong number here is a wrong number in the whole report
rather than a formatting difference.
"""
from billing import compute_invoice
from planning import schedule

PAYLOAD_KEYS = ('capacity', 'invoice', 'language', 'tasks')

SECTION_TITLES = {
    'en': {'invoice': 'Invoice summary', 'plan': 'Execution plan', 'summary': 'Summary',
           'currencies': 'Currencies', 'waves': 'Waves', 'latest_tasks': 'Latest tasks'},
    'ar': {'invoice': 'ملخص الفاتورة', 'plan': 'خطة التنفيذ', 'summary': 'الملخص',
           'currencies': 'العملات', 'waves': 'الدفعات', 'latest_tasks': 'المهام الأخيرة'},
}


def _payload_keys(payload):
    if not isinstance(payload, dict):
        raise ValueError('report input must be a JSON object')
    unknown = set(payload) - set(PAYLOAD_KEYS)
    if unknown:
        raise ValueError('unknown report input fields: ' + ', '.join(sorted(unknown)))


def _invoice_for(payload, language):
    invoice = payload.get('invoice')
    if not isinstance(invoice, dict):
        raise ValueError('report input needs an invoice object')
    if language is None:
        return invoice
    return dict(invoice, language=language)


def build_report(payload):
    """Build the combined report; the only inputs are an invoice, tasks and a capacity."""
    _payload_keys(payload)
    invoice = _invoice_for(payload, payload.get('language'))
    summary = compute_invoice(invoice)
    plan = schedule(payload.get('tasks', []), payload.get('capacity'))
    language = summary['language']
    titles = dict(SECTION_TITLES[language])
    gross = {currency: values['gross'] for currency, values in summary['by_currency'].items()}
    return {'report': 'ledgerline', 'version': 1, 'language': language, 'titles': titles,
            'invoice': summary, 'plan': plan,
            'summary': {'invoice_id': summary['invoice_id'], 'currencies': summary['currencies'],
                        'gross_by_currency': gross, 'invoice_lines': len(summary['lines']),
                        'task_count': plan['task_count'], 'waves': len(plan['waves']),
                        'priority_total': plan['priority_total'],
                        'latest_tasks': plan['latest_tasks']}}