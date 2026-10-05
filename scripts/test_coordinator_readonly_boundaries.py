"""Read-only coordinator validation may hash changed stats without refreshing the Git index."""
import os,time,unittest
import task_coordinator as coordinator
import test_coordinator_acceptance_boundaries as fixtures
class CoordinatorReadonlyBoundaries(unittest.TestCase):
 def test_content_clean_but_stat_changed_file_does_not_cause_index_writes(self):
  case=fixtures.CoordinatorPreflightBoundaries('test_a_valid_bound_dag_can_be_validated_without_writing_project_state');case.setUp();self.addCleanup(case.doCleanups)
  path=case.root/'input.txt';earlier=time.time()-100;os.utime(path,(earlier,earlier));before=case.snapshot()
  result=coordinator.validate(str(case.root),'coordinator.json','coordinator-fixture')
  self.assertEqual(result['status'],'validated');self.assertEqual(case.snapshot(),before,'Read-only coordinator preflight refreshed the Git index')
if __name__=='__main__':unittest.main()
