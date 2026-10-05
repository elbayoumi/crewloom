"""Exercise the grader's actual container mount and failed-call mutation boundary."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import evaluate_hosts as study
import test_study_grader_acceptance_boundaries as fixtures
import workflow


class StudyGraderIntegrityBoundaries(unittest.TestCase):
    def test_candidate_project_is_mounted_read_only_by_executor(self):
        task=fixtures.contracts()[0]
        case=task['cases'][1]
        captured={}
        def execute(root,argv,image,timeout,writable=None):
            captured['writable']=writable
            return {'exit_code':1,'timed_out':False,'duration_ms':1,'network':'none',
                    'image_id':image,'output':'fixture rejection','output_truncated':False}
        with patch.object(workflow,'docker_execute',side_effect=execute):
            study._grade_case(fixtures.REFERENCES[task['id']],task,case,0,'fixture-image',60,
                study.study_fixture_root(),study.TASK_SOURCES[task['id']]['support'],Path(task['output']).name)
        self.assertIsNotNone(captured['writable'],'chmod does not make an owner-writable container mount read-only')

    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','explicit Docker acceptance opt-in')
    def test_candidate_cannot_chmod_and_replace_checker_before_correct_return(self):
        task=dict(fixtures.contracts()[0]);task['cases']=[task['cases'][1]]
        candidate=fixtures.REFERENCES[task['id']]+b'\nfrom pathlib import Path\n_original=summarize\ndef summarize(records):\n    checker=Path("probe/probe.py")\n    checker.chmod(0o644)\n    checker.write_text("# changed checker\\n")\n    return _original(records)\n'
        result=study.grade_study(candidate,task,workflow.inspect_image(workflow.DEFAULT_IMAGE))
        self.assertEqual(result['held_out_pass_count'],0,result['runs'])

    @unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','explicit Docker acceptance opt-in')
    def test_input_mutation_followed_by_expected_exception_is_rejected(self):
        task=dict(fixtures.contracts()[0])
        task['cases']=[next(c for c in task['cases'] if c['id']=='non-finite')]
        candidate=b'def summarize(records):\n    records.clear()\n    raise ValueError("invalid amount")\n'
        result=study.grade_study(candidate,task,workflow.inspect_image(workflow.DEFAULT_IMAGE))
        self.assertEqual(result['held_out_pass_count'],0,result['runs'])


if __name__=='__main__':
    unittest.main()
