#!/usr/bin/env python3
"""The combined acceptance for the whole integrated candidate.

This runs once, in the integration worktree, after every verified task commit was merged.
It is only meaningful because the integration workflow declares every task output as one of
its inputs: the three generated modules and the three per-task acceptance artifacts are all
on disk here, so this script can check that the integrated tree still behaves, that the
generated command produces the report from the integrated code, and that a bad document is
refused instead of half written.

    python3 tools/check_combined.py
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

GENERATED = ('src/billing.py', 'src/planning.py', 'src/report.py', 'src/app.py')
TASK_ARTIFACTS = {
    'artifacts/billing_acceptance.json': 'src/billing.py',
    'artifacts/planning_acceptance.json': 'src/planning.py',
    'artifacts/report_acceptance.json': 'src/report.py',
}
OUT = 'artifacts/combined_acceptance.json'


def sha256(relative):
    return hashlib.sha256(Path(relative).read_bytes()).hexdigest()


def load(relative):
    return json.loads(Path(relative).read_text(encoding='utf-8'))


def command(document, *extra):
    """Start the generated command as a process and report what it did."""
    with tempfile.TemporaryDirectory(prefix='ledgerline-combined-') as folder:
        source = Path(folder) / 'input.json'
        target = Path(folder) / 'report.json'
        source.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        result = subprocess.run([sys.executable, 'src/app.py', '--data', str(source),
                                 '--out', str(target), *extra], capture_output=True, text=True,
                                timeout=60)
        written = None
        if target.is_file():
            written = json.loads(target.read_text(encoding='utf-8'))
        error = None
        if result.stderr.strip():
            try:
                error = json.loads(result.stderr.strip().splitlines()[-1]).get('error')
            except ValueError:
                error = result.stderr.strip()[:200]
        first = target.read_bytes() if target.is_file() else None
        return {'returncode': result.returncode, 'report': written, 'error': error, 'raw': first}


def task_evidence():
    """Each task's own acceptance is accepted and describes the integrated bytes."""
    observed = {}
    for artifact, module in TASK_ARTIFACTS.items():
        record = load(artifact)
        recorded = record.get('source_sha256') or (record.get('generated') or {}).get(module)
        observed[artifact] = {'accepted': record['accepted'],
                              'matches_integrated_bytes': recorded == sha256(module)}
    return observed


def task_coverage():
    """The per-task acceptances are real batteries, not a single smoke check."""
    return {artifact: load(artifact)['case_count'] >= 10 and load(artifact)['accepted']
            for artifact in TASK_ARTIFACTS}


def generated_modules():
    return {relative: (Path(relative).is_file() and Path(relative).stat().st_size > 0)
            for relative in GENERATED}


def english_run():
    document = command(load('data/ledger_en.json'))['report']
    return {'returncode': 0, 'report': document['report'], 'language': document['language'],
            'summary': document['summary'], 'waves': document['plan']['waves'],
            'invoice_currency_totals': document['invoice']['by_currency']}


def arabic_run():
    document = command(load('data/ledger_ar.json'), '--language', 'ar')['report']
    group = document['invoice']['by_currency']['SAR']
    return {'language': document['language'], 'title': document['titles']['invoice'],
            'label': document['invoice']['lines'][0]['label'], 'summary': document['summary'],
            'rounding_after_integration': {'tax': group['tax'],
                                           'per_line_tax': group['per_line_tax']},
            'waves': document['plan']['waves']}


def mixed_currency_run():
    """Two currencies and a refund through the real command, from the integrated tree."""
    document = {'invoice': {'invoice_id': 'INV-MIXED', 'language': 'en', 'lines': [
        {'description_en': 'Euro work', 'description_ar': 'عمل باليورو', 'currency': 'EUR',
         'category': 'services', 'quantity': 1, 'unit_price': '20.00', 'tax_rate': '0'},
        {'description_en': 'Riyal refund', 'description_ar': 'استرداد بالريال', 'currency': 'SAR',
         'category': 'refund', 'quantity': 1, 'unit_price': '100.00', 'tax_rate': '10'}]},
        'capacity': 2, 'tasks': [{'id': 'only', 'priority': 0}]}
    outcome = command(document)
    return {'returncode': outcome['returncode'],
            'currencies': outcome['report']['invoice']['currencies'],
            'single_currency': outcome['report']['invoice']['single_currency'],
            'by_currency': outcome['report']['invoice']['by_currency'],
            'waves': outcome['report']['plan']['waves']}


def repeated_run_is_byte_stable():
    """The same document twice produces the same bytes, so a report can be diffed."""
    document = load('data/ledger_en.json')
    return {'identical': command(document)['raw'] == command(document)['raw'],
            'ends_with_newline': (command(document)['raw'] or b'').endswith(b'\n')}


def refusals():
    """Every invalid document exits 2, names its cause and writes no output."""
    cycle = deepcopy(load('data/ledger_en.json'))
    cycle['tasks'] = [{'id': 'a', 'depends_on': ['b']}, {'id': 'b', 'depends_on': ['a']}]
    unknown = deepcopy(load('data/ledger_en.json'))
    unknown['extra'] = True
    amount = deepcopy(load('data/ledger_en.json'))
    amount['invoice']['lines'][0]['unit_price'] = 10.5
    quantity = deepcopy(load('data/ledger_en.json'))
    quantity['invoice']['lines'][0]['quantity'] = True
    category = deepcopy(load('data/ledger_en.json'))
    category['invoice']['lines'][0]['category'] = 'discount'
    cases = (('a_cycle_is_refused', cycle, 'cycle'),
             ('an_unknown_payload_field_is_refused', unknown, 'unknown report input fields'),
             ('a_float_amount_is_refused', amount, 'unit_price'),
             ('a_boolean_quantity_is_refused', quantity, 'quantity'),
             ('an_unknown_category_is_refused', category, 'category'))
    observed = {}
    for name, document, expected in cases:
        outcome = command(document)
        observed[name] = {'returncode': outcome['returncode'], 'no_report': outcome['report'] is None,
                          'names_cause': expected in str(outcome['error'])}
    return observed


def command_help():
    result = subprocess.run([sys.executable, 'src/app.py', '--help'], capture_output=True,
                            text=True, timeout=60)
    return {'returncode': result.returncode, 'mentions_language': '--language' in result.stdout,
            'mentions_data': '--data' in result.stdout}


CASES = (
    ('every_task_acceptance_survived_integration', task_evidence,
     {'artifacts/billing_acceptance.json': {'accepted': True, 'matches_integrated_bytes': True},
      'artifacts/planning_acceptance.json': {'accepted': True, 'matches_integrated_bytes': True},
      'artifacts/report_acceptance.json': {'accepted': True, 'matches_integrated_bytes': True}}),
    ('every_task_acceptance_ran_a_real_battery', task_coverage,
     {'artifacts/billing_acceptance.json': True, 'artifacts/planning_acceptance.json': True,
      'artifacts/report_acceptance.json': True}),
    ('every_generated_module_is_present', generated_modules,
     {'src/billing.py': True, 'src/planning.py': True, 'src/report.py': True, 'src/app.py': True}),
    ('english_report_from_the_integrated_command', english_run,
     {'returncode': 0, 'report': 'ledgerline', 'language': 'en',
      'summary': {'invoice_id': 'INV-2026-004', 'currencies': ['USD'],
                  'gross_by_currency': {'USD': '2976.34'}, 'invoice_lines': 3, 'task_count': 5,
                  'waves': 3, 'priority_total': 23, 'latest_tasks': ['publish-arabic']},
      'waves': [['collect-invoices', 'archive-ledger'], ['validate-tax', 'draft-report'],
                ['publish-arabic']],
      'invoice_currency_totals': {'USD': {'net': '2588.01', 'tax': '388.33', 'gross': '2976.34',
                                          'per_line_tax': '388.33'}}}),
    ('arabic_report_from_the_integrated_command', arabic_run,
     {'language': 'ar', 'title': 'ملخص الفاتورة', 'label': 'حالة التقريب أ',
      'summary': {'invoice_id': 'INV-2026-005', 'currencies': ['SAR'],
                  'gross_by_currency': {'SAR': '347.01'}, 'invoice_lines': 3, 'task_count': 3,
                  'waves': 3, 'priority_total': 0, 'latest_tasks': ['c']},
      'rounding_after_integration': {'tax': '45.01', 'per_line_tax': '45.00'},
      'waves': [['a'], ['b'], ['c']]}),
    ('mixed_currency_and_refund_from_the_integrated_command', mixed_currency_run,
     {'returncode': 0, 'currencies': ['EUR', 'SAR'], 'single_currency': False,
      'by_currency': {'EUR': {'net': '20.00', 'tax': '0.00', 'gross': '20.00',
                              'per_line_tax': '0.00'},
                      'SAR': {'net': '-100.00', 'tax': '-10.00', 'gross': '-110.00',
                              'per_line_tax': '-10.00'}},
      'waves': [['only']]}),
    ('two_runs_are_byte_identical', repeated_run_is_byte_stable,
     {'identical': True, 'ends_with_newline': True}),
    ('the_command_documents_its_own_interface', command_help,
     {'returncode': 0, 'mentions_language': True, 'mentions_data': True}),
)

REFUSAL_CASES = (
    ('a_cycle_is_refused', {'returncode': 2, 'no_report': True, 'names_cause': True}),
    ('an_unknown_payload_field_is_refused', {'returncode': 2, 'no_report': True,
                                             'names_cause': True}),
    ('a_float_amount_is_refused', {'returncode': 2, 'no_report': True, 'names_cause': True}),
    ('a_boolean_quantity_is_refused', {'returncode': 2, 'no_report': True, 'names_cause': True}),
    ('an_unknown_category_is_refused', {'returncode': 2, 'no_report': True, 'names_cause': True}),
)


def main():
    cases = []
    for name, run, expected in CASES:
        try:
            observed = run()
        except Exception as exc:
            observed = {'error': type(exc).__name__ + ': ' + str(exc)}
        cases.append({'name': name, 'expected': expected, 'observed': observed,
                      'ok': observed == expected})
    refused = refusals()
    for name, expected in REFUSAL_CASES:
        observed = refused.get(name, {'error': 'case did not run'})
        cases.append({'name': name, 'expected': expected, 'observed': observed,
                      'ok': observed == expected})
    failed = [item['name'] for item in cases if not item['ok']]
    record = {'integration': 'ledgerline', 'generated': {relative: sha256(relative)
                                                         for relative in GENERATED},
              'case_count': len(cases), 'failed': failed, 'accepted': not failed, 'cases': cases}
    target = Path(OUT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding='utf-8')
    if failed:
        print('combined acceptance failed: ' + ', '.join(failed), file=sys.stderr)
        return 1
    print('combined acceptance passed ' + str(len(cases)) + ' cases')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())