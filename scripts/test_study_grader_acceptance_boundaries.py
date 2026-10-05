"""Supervisor-owned context-study quality checks; independent of producer tests."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_hosts as study
import workflow as workflow


REFERENCES = {
    'invoice-summary': b'''import unicodedata
from money import parse_amount, total_of, format_amount
def summarize(records):
    if not isinstance(records,list): raise TypeError()
    groups={}
    for r in records:
        if not isinstance(r,dict): raise ValueError()
        if not all(isinstance(r.get(k),str) for k in ('amount','category','currency')): raise ValueError()
        category=unicodedata.normalize('NFKC',r['category']).strip().casefold()
        currency=r['currency'].strip().upper()
        if not category or len(currency)!=3 or any(not 'A'<=c<='Z' for c in currency): raise ValueError()
        groups.setdefault((currency,category),[]).append(parse_amount(r['amount']))
    return [dict(currency=k[0],category=k[1],total=format_amount(total_of(groups[k]))) for k in sorted(groups)]
''',
    'dependency-order': b'''from scheduling import check_task
def plan(tasks):
    if not isinstance(tasks,list): raise TypeError()
    items={}
    for raw in tasks:
        task=check_task(raw)
        if task['id'] in items: raise ValueError()
        items[task['id']]=task
    for key,t in items.items():
        if key in t['depends_on'] or any(d not in items for d in t['depends_on']): raise ValueError()
    result=[]
    while len(result)<len(items):
        ready=[k for k,t in items.items() if k not in result and all(d in result for d in t['depends_on'])]
        if not ready: raise ValueError()
        result.append(min(ready,key=lambda k:(-items[k]['priority'],k)))
    return result
''',
    'project-path': b'''from pathlib import Path
from pathutil import split_relative,is_linked,is_hardlinked,regular_file_below,contained
def resolve_project_path(root,relative):
    parts=split_relative(relative)
    target=Path(root).joinpath(*parts)
    if is_linked(root,parts) or is_hardlinked(target) or regular_file_below(root,parts) or not contained(root,target): raise ValueError()
    return target.resolve()
''',
}


def contracts():
    return study.study_contracts()['tasks']


class StudyGraderBoundaries(unittest.TestCase):
    def test_pass_count_denominator_is_number_of_executed_cases(self):
        task=contracts()[0]
        with mock.patch.object(study,'_grade_case',return_value={'passed':1}):
            report=study.grade_study(REFERENCES[task['id']],task,'sha256:test',case_runs=2)
        self.assertEqual(report['checks_total'],22)
        self.assertEqual(report['checks_passed'],22)
        self.assertEqual(report['held_out_total'],22)

    def test_json_comparison_does_not_coerce_boolean_to_integer(self):
        self.assertFalse(study.study_score({'value':True},{'value':1}))
        self.assertTrue(study.study_score({'value':1},{'value':1}))

    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','explicit Docker acceptance opt-in')
    def test_correct_references_pass_all_33_frozen_cases(self):
        image=workflow.inspect_image(workflow.DEFAULT_IMAGE)
        for task in contracts():
            with self.subTest(task=task['id']):
                report=study.grade_study(REFERENCES[task['id']],task,image)
                self.assertEqual(report['held_out_pass_count'],11,report['runs'])

    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','explicit Docker acceptance opt-in')
    def test_correct_return_with_mutated_input_is_rejected(self):
        task=dict(contracts()[0])
        task['cases']=[next(c for c in task['cases'] if c['id']=='combined')]
        candidate=REFERENCES[task['id']]+b'\n_original=summarize\ndef summarize(records):\n    result=_original(records)\n    records.clear()\n    return result\n'
        report=study.grade_study(candidate,task,workflow.inspect_image(workflow.DEFAULT_IMAGE))
        self.assertEqual(report['held_out_pass_count'],0,report['runs'])

    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','explicit Docker acceptance opt-in')
    def test_correct_return_with_modified_checker_is_rejected(self):
        task=dict(contracts()[0])
        task['cases']=[next(c for c in task['cases'] if c['id']=='combined')]
        candidate=REFERENCES[task['id']]+b'\nfrom pathlib import Path\n_original=summarize\ndef summarize(records):\n    Path("probe/probe.py").write_text("# checker overwritten\\n")\n    return _original(records)\n'
        report=study.grade_study(candidate,task,workflow.inspect_image(workflow.DEFAULT_IMAGE))
        self.assertEqual(report['held_out_pass_count'],0,report['runs'])


if __name__=='__main__':
    unittest.main()
