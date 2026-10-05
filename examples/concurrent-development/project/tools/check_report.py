#!/usr/bin/env python3
"""Acceptance for the generated report module and the generated command.

This runs in the dependent task's worktree, after the two independent task commits were
merged in. It therefore checks three different things: that the ancestors' recorded
acceptance still describes the bytes now on disk, that the combined report carries real
numbers, and that the generated command itself produces and refuses correctly when it is
started as a process.

    python3 tools/check_report.py
"""
import hashlib
import json
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, 'src')

import report  # noqa: E402

OUT = 'artifacts/report_acceptance.json'
GENERATED = ('src/billing.py', 'src/planning.py', 'src/report.py', 'src/app.py')
ANCESTOR_ARTIFACTS = ('artifacts/billing_acceptance.json', 'artifacts/planning_acceptance.json')


def sha256(relative):
    return hashlib.sha256(Path(relative).read_bytes()).hexdigest()


def load(relative):
    return json.loads(Path(relative).read_text(encoding='utf-8'))


def english_sample():
    return load('data/ledger_en.json')


def arabic_sample():
    return load('data/ledger_ar.json')


def english_report():
    return report.build_report(english_sample())['summary']


def arabic_report():
    return report.build_report(arabic_sample())['summary']


def arabic_labels():
    document = report.build_report(arabic_sample())
    return {'title': document['titles']['invoice'], 'label': document['invoice']['lines'][0]['label'],
            'arabic_kept': 'ملخص الفاتورة' in json.dumps(document, ensure_ascii=False),
            'titles_keys': sorted(document['titles'])}


def final_rounding():
    """The group total is the quantized sum of unrounded taxes; the per-line figure differs."""
    group = report.build_report(arabic_sample())['invoice']['by_currency']['SAR']
    return {'tax': group['tax'], 'per_line_tax': group['per_line_tax'],
            'net': group['net'], 'gross': group['gross'],
            'round_once_wins': group['tax'] != group['per_line_tax']}


def language_override():
    """An explicit language restyles the whole report and mutates nothing it was given."""
    payload = deepcopy(arabic_sample())
    document = report.build_report(dict(payload, language='en'))
    original = report.build_report(payload)
    return {'override_title': document['titles']['invoice'],
            'override_invoice_language': document['language'],
            'override_label': document['invoice']['lines'][0]['label'],
            'default_title': original['titles']['invoice'],
            'input_untouched': payload['invoice']['language'] == 'ar'}


def ancestors_match_current_bytes():
    """Each ancestor acceptance was recorded against exactly the module bytes now on disk."""
    observed = {}
    for relative, module in zip(ANCESTOR_ARTIFACTS, ('src/billing.py', 'src/planning.py')):
        record = load(relative)
        observed[relative] = {'accepted': record['accepted'], 'matches': record['source_sha256']
                              == sha256(module)}
    return observed


def run_command(document, *extra):
    with tempfile.TemporaryDirectory(prefix='ledgerline-') as folder:
        source = Path(folder) / 'input.json'
        target = Path(folder) / 'report.json'
        source.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
        result = subprocess.run([sys.executable, 'src/app.py', '--data', str(source),
                                 '--out', str(target), *extra], capture_output=True, text=True,
                                timeout=60)
        payload = json.loads(result.stdout) if result.stdout.strip() else {}
        written = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else None
        return result, payload, written


def cli_success():
    result, payload, written = run_command(english_sample())
    return {'returncode': result.returncode, 'status': payload.get('status'),
            'matches_library': written == report.build_report(english_sample()),
            'report_name': (written or {}).get('report'), 'stdout_is_small':
                len(result.stdout) < 200}


def cli_arabic():
    result, payload, written = run_command(arabic_sample(), '--language', 'ar')
    return {'returncode': result.returncode, 'language': (written or {}).get('language'),
            'title': ((written or {}).get('titles') or {}).get('invoice'),
            'status': payload.get('status')}


def cli_refuses():
    """A bad document exits 2 with one JSON error and leaves no output behind."""
    document = deepcopy(english_sample())
    document['invoice']['lines'][0]['currency'] = 'CHF'
    result, payload, written = run_command(document)
    error = {}
    if result.stderr.strip():
        try:
            error = json.loads(result.stderr.strip().splitlines()[-1])
        except ValueError:
            error = {'raw': result.stderr.strip()[:200]}
    return {'returncode': result.returncode, 'status': error.get('status'),
            'names_currency': 'currency' in str(error.get('error', '')),
            'no_partial_output': written is None, 'stdout_empty': not result.stdout.strip()}


CASES = (
    ('english_summary_totals', english_report,
     {'invoice_id': 'INV-2026-004', 'currencies': ['USD'], 'gross_by_currency': {'USD': '2976.34'},
      'invoice_lines': 3, 'task_count': 5, 'waves': 3, 'priority_total': 23,
      'latest_tasks': ['publish-arabic']}),
    ('arabic_summary_totals', arabic_report,
     {'invoice_id': 'INV-2026-005', 'currencies': ['SAR'], 'gross_by_currency': {'SAR': '347.01'},
      'invoice_lines': 3, 'task_count': 3, 'waves': 3, 'priority_total': 0,
      'latest_tasks': ['c']}),
    ('arabic_titles_and_labels', arabic_labels,
     {'title': 'ملخص الفاتورة', 'label': 'حالة التقريب أ', 'arabic_kept': True,
      'titles_keys': ['currencies', 'invoice', 'latest_tasks', 'plan', 'summary', 'waves']}),
    ('the_group_total_rounds_once', final_rounding,
     {'tax': '45.01', 'per_line_tax': '45.00', 'net': '302.00', 'gross': '347.01',
      'round_once_wins': True}),
    ('an_explicit_language_restyles_only', language_override,
     {'override_title': 'Invoice summary', 'override_invoice_language': 'en',
      'override_label': 'Rounding probe A', 'default_title': 'ملخص الفاتورة',
      'input_untouched': True}),
    ('ancestor_acceptance_still_describes_these_bytes', ancestors_match_current_bytes,
     {'artifacts/billing_acceptance.json': {'accepted': True, 'matches': True},
      'artifacts/planning_acceptance.json': {'accepted': True, 'matches': True}}),
    ('the_command_writes_the_library_report', cli_success,
     {'returncode': 0, 'status': 'written', 'matches_library': True, 'report_name': 'ledgerline',
      'stdout_is_small': True}),
    ('the_command_writes_an_arabic_report', cli_arabic,
     {'returncode': 0, 'language': 'ar', 'title': 'ملخص الفاتورة', 'status': 'written'}),
    ('the_command_refuses_a_bad_document', cli_refuses,
     {'returncode': 2, 'status': 'blocked', 'names_currency': True, 'no_partial_output': True,
      'stdout_empty': True}),
)


def refusals():
    """The library refuses the same invalid documents the command does."""
    checks = []
    unknown = deepcopy(english_sample())
    unknown['invoice_id'] = 'not-allowed'
    checks.append(('unknown_payload_field_is_refused', unknown, 'unknown report input fields'))
    checks.append(('missing_invoice_is_refused', {'tasks': []}, 'invoice'))
    checks.append(('a_payload_that_is_not_an_object_is_refused', ['x'], 'must be a JSON object'))
    cycle = deepcopy(english_sample())
    cycle['tasks'] = [{'id': 'a', 'depends_on': ['b']}, {'id': 'b', 'depends_on': ['a']}]
    checks.append(('a_dependency_cycle_is_refused', cycle, 'cycle'))
    bad_language = deepcopy(english_sample())
    bad_language['language'] = 'de'
    checks.append(('an_unknown_language_is_refused', bad_language, 'language'))
    results = {}
    for name, payload, expected in checks:
        try:
            report.build_report(payload)
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
        except Exception as exc:
            observed = {'error': type(exc).__name__ + ': ' + str(exc)}
        cases.append({'name': name, 'expected': expected, 'observed': observed,
                      'ok': observed == expected})
    refused = refusals()
    for name in sorted(refused):
        cases.append({'name': name, 'expected': True, 'observed': refused[name],
                      'ok': refused[name]})
    failed = [item['name'] for item in cases if not item['ok']]
    accepted = not failed
    record = {'generated': {relative: sha256(relative) for relative in GENERATED},
              'case_count': len(cases), 'failed': failed, 'accepted': accepted, 'cases': cases}
    target = Path(OUT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding='utf-8')
    if not accepted:
        print('report acceptance failed: ' + ', '.join(failed), file=sys.stderr)
        return 1
    print('report acceptance passed ' + str(len(cases)) + ' cases')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())