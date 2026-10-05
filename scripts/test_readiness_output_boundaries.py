"""Independent optional report-output ownership and persisted evidence checks."""
import json,subprocess,sys,unittest
from pathlib import Path
import agency_readiness as tool
import repo_map
import test_readiness_acceptance_boundaries as fixtures
class ReadinessOutputBoundaries(unittest.TestCase):
 def fixture(self):
  case=fixtures.ReadinessAcceptance('test_current_registered_evidence_is_ready_with_no_writes');case.setUp();self.addCleanup(case.doCleanups)
  return case
 def test_optional_reports_cannot_overwrite_any_runtime_authority_or_controller_state(self):
  for relative in ('.crewloom/binding.json','.crewloom/reviewers.json','.crewloom/active_task.json','.crewloom/coordinators/batch/state.json'):
   with self.subTest(relative=relative):
    case=self.fixture();path=case.root/relative;path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():path.write_text('foreign authority record\n')
    payload=tool.report('readiness-fixture',case.root,case.agency,case.registry);before=case.snapshot()
    with self.assertRaises(ValueError):tool.store_report(payload,case.root,relative)
    self.assertEqual(case.snapshot(),before)
 def test_dotdot_cannot_turn_an_owned_report_path_into_a_binding_write(self):
  case=self.fixture();(case.root/'.crewloom/readiness').mkdir();payload=tool.report('readiness-fixture',case.root,case.agency,case.registry);before=case.snapshot()
  with self.assertRaises(ValueError):tool.store_report(payload,case.root,'.crewloom/readiness/../binding.json')
  self.assertEqual(case.snapshot(),before)
 def test_owned_report_is_private_and_preserves_all_other_project_state(self):
  case=self.fixture();(case.root/'.crewloom/readiness').mkdir();payload=tool.report('readiness-fixture',case.root,case.agency,case.registry);before=case.snapshot()
  path=tool.store_report(payload,case.root,'.crewloom/readiness/ready.json')
  self.assertEqual(path,case.root/'.crewloom/readiness/ready.json');self.assertEqual(path.stat().st_mode&0o777,0o600)
  after=case.snapshot();self.assertEqual({p:v for p,v in after.items() if p!='projects/fixture/.crewloom/readiness/ready.json'},before)
  self.assertTrue(json.loads(path.read_text())['ready'])
 def test_written_report_and_stdout_agree_on_the_report_write_outcome(self):
  case=self.fixture();(case.root/'.crewloom/readiness').mkdir();target='.crewloom/readiness/ready.json'
  result=subprocess.run([sys.executable,str(Path(tool.__file__)), '--project-root',str(case.root),'--project-id','readiness-fixture','--agency-root',str(case.agency),'--registry',str(case.registry),'--report-out',target],cwd=case.root,env=repo_map.git_environment(),capture_output=True,text=True,timeout=20)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  printed=json.loads(result.stdout);stored=json.loads((case.root/target).read_text())
  self.assertEqual(stored['write'],printed['write'],'Persisted evidence falsely reports a different write outcome')
if __name__=='__main__':unittest.main()
