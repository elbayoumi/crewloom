"""Public context-study acceptance must work without excluded private runtime files."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import evaluate_hosts as study
import test_context_study as producer

class StudyPublicExportBoundaries(unittest.TestCase):
    def test_public_resource_acceptance_needs_no_private_supervisor_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve()
            fixture=root/study.FIXTURE_RELATIVE
            shutil.copytree(study.study_fixture_root(),fixture)
            resource=root/study.GRADER_CONTRACTS_RELATIVE
            resource.parent.mkdir(parents=True)
            shutil.copyfile(Path(study.w.LIBRARY)/study.GRADER_CONTRACTS_RELATIVE,resource)
            self.assertFalse((root/'.crewloom').exists())
            with patch.object(study.w,'LIBRARY',root):
                case=producer.FrozenProtocolTests('test_the_held_out_resource_is_packaged_and_never_private_state')
                result=unittest.TestResult();case.run(result)
            self.assertEqual(result.errors,[],result.errors)
            self.assertEqual(result.failures,[],result.failures)
            self.assertEqual(result.testsRun,1)

if __name__=='__main__':unittest.main()
