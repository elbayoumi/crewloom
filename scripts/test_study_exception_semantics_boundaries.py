"""A returned error-shaped value is not the required built-in exception."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import evaluate_hosts as study
import test_study_grader_acceptance_boundaries as fixtures
import workflow


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','explicit Docker acceptance opt-in')
class StudyExceptionSemanticsBoundaries(unittest.TestCase):
    def task(self):
        task=dict(fixtures.contracts()[0])
        task['cases']=[next(case for case in task['cases'] if case['id']=='non-finite')]
        return task

    def test_returning_an_error_dictionary_does_not_count_as_raising(self):
        candidate=b'def summarize(records):\n    return {"error":"ValueError"}\n'
        report=study.grade_study(candidate,self.task(),workflow.inspect_image(workflow.DEFAULT_IMAGE))
        self.assertEqual(report['held_out_pass_count'],0,report['runs'])

    def test_same_named_custom_exception_is_not_the_required_builtin(self):
        candidate=b'class ValueError(Exception):\n    pass\ndef summarize(records):\n    raise ValueError("wrong exception class")\n'
        report=study.grade_study(candidate,self.task(),workflow.inspect_image(workflow.DEFAULT_IMAGE))
        self.assertEqual(report['held_out_pass_count'],0,report['runs'])


if __name__=='__main__':
    unittest.main()
