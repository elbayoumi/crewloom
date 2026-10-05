#!/usr/bin/env python3
"""Acceptance for the generated planning module.

Runs inside the task's own container against a declared-input snapshot of the generated
module. The checks are about order, depth, capacity and refusal: a module that returns the
right-looking list for one document and a different one for the same document twice fails
here.

    python3 tools/check_planning.py
"""
import hashlib
import importlib
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, 'src')

MODULE = 'src/planning.py'
HELPER = 'src/scheduling_support.py'
OUT = 'artifacts/planning_acceptance.json'

planning = importlib.import_module('planning')


def sha256(relative):
    return hashlib.sha256(Path(relative).read_bytes()).hexdigest()


def english_sample():
    return json.loads(Path('data/ledger_en.json').read_text(encoding='utf-8'))


def arabic_sample():
    return json.loads(Path('data/ledger_ar.json').read_text(encoding='utf-8'))


def order_of(tasks, capacity=None):
    plan = planning.schedule(deepcopy(tasks), capacity)
    return {'order': plan['order'], 'waves': plan['waves'], 'capacity': plan['capacity']}


def depth_case():
    """A high-priority task still waits for the dependency it declares."""
    tasks = [{'id': 'later', 'priority': 9},
             {'id': 'first', 'priority': -9, 'depends_on': ['later']}]
    return order_of(tasks, 4)


def tie_break_case():
    """Equal priority and equal depth break lexically, not by input order."""
    return order_of([{'id': 'beta', 'priority': 1}, {'id': 'alpha', 'priority': 1},
                     {'id': 'gamma'}], 4)


def capacity_case():
    """Five independent tasks at capacity two chunk into waves of 2, 2 and 1."""
    tasks = [{'id': 't' + str(index), 'priority': 0} for index in range(5)]
    plan = planning.schedule(tasks, 2)
    return {'waves': plan['waves'], 'sizes': [len(wave) for wave in plan['waves']],
            'capacity': plan['capacity']}


def english_case():
    plan = planning.schedule(english_sample()['tasks'], english_sample()['capacity'])
    return {'order': plan['order'], 'waves': plan['waves'], 'depths': plan['depths'],
            'latest_tasks': plan['latest_tasks'], 'priority_total': plan['priority_total'],
            'task_count': plan['task_count']}


def arabic_case():
    plan = planning.schedule(arabic_sample()['tasks'], arabic_sample()['capacity'])
    return {'order': plan['order'], 'waves': plan['waves'], 'latest_tasks': plan['latest_tasks'],
            'priority_total': plan['priority_total'], 'task_count': plan['task_count']}


def determinism_case():
    document = english_sample()
    first = planning.schedule(deepcopy(document['tasks']), document['capacity'])
    second = planning.schedule(deepcopy(list(reversed(document['tasks']))), document['capacity'])
    return {'stable_under_reversed_input': first['order'] == second['order'],
            'identical': first == second}


def empty_case():
    plan = planning.schedule([], None)
    return {'order': plan['order'], 'waves': plan['waves'], 'task_count': plan['task_count'],
            'latest_tasks': plan['latest_tasks'], 'capacity': plan['capacity']}


def cycle_case():
    """The cycle is named, not swallowed, and planning refuses it."""
    tasks = [{'id': 'a', 'depends_on': ['c']}, {'id': 'b', 'depends_on': ['a']},
             {'id': 'c', 'depends_on': ['b']}]
    cycle = planning.detect_cycle(tasks)
    try:
        planning.schedule(tasks, 2)
    except ValueError as exc:
        message = str(exc)
    else:
        message = ''
    return {'cycle': cycle, 'closed': bool(cycle) and cycle[0] == cycle[-1],
            'refused': 'cycle' in message, 'clean_graph': planning.detect_cycle(
                [{'id': 'a'}, {'id': 'b', 'depends_on': ['a']}])}


CASES = (
    ('dependency_depth_beats_priority', depth_case,
     {'order': ['later', 'first'], 'waves': [['later', 'first']], 'capacity': 4}),
    ('equal_priority_breaks_lexically', tie_break_case,
     {'order': ['alpha', 'beta', 'gamma'],
      'waves': [['alpha', 'beta', 'gamma']], 'capacity': 4}),
    ('capacity_chunks_without_mixing', capacity_case,
     {'waves': [['t0', 't1'], ['t2', 't3'], ['t4']], 'sizes': [2, 2, 1], 'capacity': 2}),
    ('frozen_english_sample_plan', english_case,
     {'order': ['collect-invoices', 'archive-ledger', 'validate-tax', 'draft-report',
                'publish-arabic'],
      'waves': [['collect-invoices', 'archive-ledger'], ['validate-tax', 'draft-report'],
                ['publish-arabic']],
      'depths': {'archive-ledger': 1, 'collect-invoices': 1, 'draft-report': 3,
                 'publish-arabic': 4, 'validate-tax': 2},
      'latest_tasks': ['publish-arabic'], 'priority_total': 23, 'task_count': 5}),
    ('frozen_arabic_sample_plan', arabic_case,
     {'order': ['a', 'b', 'c'], 'waves': [['a'], ['b'], ['c']], 'latest_tasks': ['c'],
      'priority_total': 0, 'task_count': 3}),
    ('the_plan_is_deterministic', determinism_case,
     {'stable_under_reversed_input': True, 'identical': True}),
    ('an_empty_plan_is_valid', empty_case,
     {'order': [], 'waves': [], 'task_count': 0, 'latest_tasks': [], 'capacity': 2}),
    ('a_cycle_is_named_and_refused', cycle_case,
     {'cycle': ['a', 'c', 'b', 'a'], 'closed': True, 'refused': True, 'clean_graph': []}),
)


def refusals():
    """Every invalid document the contract names must raise ValueError naming the cause."""
    checks = (
        ('unknown_dependency_is_refused', [{'id': 'a', 'depends_on': ['ghost']}], 'unknown task'),
        ('self_dependency_is_refused', [{'id': 'a', 'depends_on': ['a']}], 'itself'),
        ('duplicate_task_is_refused', [{'id': 'a'}, {'id': 'a'}], 'twice'),
        ('repeated_dependency_is_refused', [{'id': 'a', 'depends_on': ['b', 'b']},
                                            {'id': 'b'}], 'repeats'),
        ('boolean_priority_is_refused', [{'id': 'a', 'priority': True}], 'priority'),
        ('out_of_range_priority_is_refused', [{'id': 'a', 'priority': 10}], 'priority'),
        ('invalid_task_id_is_refused', [{'id': '../foreign'}], 'id'),
        ('a_task_that_is_not_an_object_is_refused', ['nope'], 'must be an object'),
        ('a_task_list_that_is_not_a_list_is_refused', {'id': 'a'}, 'must be a list'),
    )
    results = {}
    for name, tasks, expected in checks:
        try:
            planning.schedule(tasks, 2)
        except ValueError as exc:
            results[name] = expected in str(exc)
        else:
            results[name] = False
    for name, capacity in (('zero_capacity_is_refused', 0), ('oversized_capacity_is_refused', 9),
                           ('boolean_capacity_is_refused', True)):
        try:
            planning.schedule([{'id': 'a'}], capacity)
        except ValueError as exc:
            results[name] = 'capacity' in str(exc)
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
    report = {'module': MODULE, 'source_sha256': sha256(MODULE),
              'helper_sha256': sha256(HELPER), 'case_count': len(cases), 'failed': failed,
              'accepted': not failed, 'cases': cases}
    target = Path(OUT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding='utf-8')
    if failed:
        print('planning acceptance failed: ' + ', '.join(failed), file=sys.stderr)
        return 1
    print('planning acceptance passed ' + str(len(cases)) + ' cases')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())