"""Independent readonly registry/evidence readiness boundaries, fixture-only."""
import copy,hashlib,json,os,subprocess,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
SOURCE=Path(__file__).resolve().parent;sys.path.insert(0,str(SOURCE))
import crewloom,project_binding as pb,repo_map
class ReadinessAcceptance(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory(prefix='crewloom-readiness-independent-');self.addCleanup(t.cleanup);self.agency=Path(t.name).resolve();self.root=self.agency/'projects/fixture';self.root.mkdir(parents=True)
  _,errors=crewloom.install_skills(self.root,'agents',['context-guardian'],False);self.assertFalse(errors)
  pb.bootstrap(self.root,project_id='readiness-fixture')
  self.evidence=self.root/'evidence.md';self.evidence.write_text('Actual fixture evidence from repository review.\n')
  (self.root/'CONTEXT_SNAPSHOT.md').write_text('Public fixture current-state context.\n')
  now=datetime.now(timezone.utc).isoformat(timespec='seconds')
  self.entry={'id':'readiness-fixture','active_dir':'projects/fixture','context_snapshot':'projects/fixture/CONTEXT_SNAPSHOT.md','delivery_owner':'context-guardian','control_status':'ready_for_review','last_verified_at':now,'next_action':{'owner':'context-guardian','output':'A verified fixture change','acceptance':'Run the fixture checks'},'state_evidence':{'path':'projects/fixture/evidence.md','sha256':hashlib.sha256(self.evidence.read_bytes()).hexdigest(),'source_type':'repository_review','observed_at':now}}
  self.registry=self.agency/'registry.json';self.write_registry()
 def write_registry(self,entries=None):self.registry.write_text(json.dumps({'schema_version':1,'projects':entries if entries is not None else [self.entry]}))
 def snapshot(self):
  return {str(p.relative_to(self.agency)):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mode,p.stat().st_mtime_ns) for p in self.agency.rglob('*') if p.is_file() and not p.is_symlink()}
 def report(self,expected_ready=False,project_id='readiness-fixture',root=None):
  before=self.snapshot();r=subprocess.run([sys.executable,str(SOURCE/'agency_readiness.py'),'--project-root',str(root or self.root),'--project-id',project_id,'--agency-root',str(self.agency),'--registry',str(self.registry)],cwd=self.root,env=repo_map.git_environment(),capture_output=True,text=True,timeout=20)
  self.assertEqual(self.snapshot(),before,'Default readonly preflight mutated state')
  self.assertEqual(r.returncode,0 if expected_ready else 2,r.stdout+r.stderr)
  value=json.loads(r.stdout);self.assertIs(value['ready'],expected_ready)
  return value
 def test_current_registered_evidence_is_ready_with_no_writes(self):self.report(True)
 def test_reconciliation_status_is_not_automatically_ready(self):
  self.entry['control_status']='needs_reconciliation';self.entry['last_verified_at']=None;self.entry.pop('state_evidence');self.write_registry();self.report()
 def test_stale_evidence_is_not_current(self):
  self.entry['last_verified_at']='2000-01-01T00:00:00Z';self.entry['state_evidence']['observed_at']='2000-01-01T00:00:00Z';self.write_registry();self.report()
 def test_changed_evidence_hash_is_not_accepted(self):self.evidence.write_text('Changed after observation.\n');self.report()
 def test_empty_evidence_is_not_accepted(self):self.evidence.write_text('');self.entry['state_evidence']['sha256']=hashlib.sha256(b'').hexdigest();self.write_registry();self.report()
 def test_naive_timestamp_is_not_treated_as_current_timezone_aware_evidence(self):
  self.entry['last_verified_at']=datetime.now().isoformat();self.entry['state_evidence']['observed_at']=datetime.now().isoformat();self.write_registry();self.report()
 def test_foreign_project_id_is_refused_without_writes(self):self.report(project_id='another-project')
 def test_registry_cannot_bind_another_root_to_the_selected_id(self):
  other=self.agency/'other';other.mkdir();self.report(root=other)
 def test_duplicate_registry_ids_are_refused(self):self.write_registry([self.entry,copy.deepcopy(self.entry)]);self.report()
 def test_linked_registry_is_refused_without_touching_target(self):
  original=self.agency/'original.json';self.registry.rename(original);self.registry.symlink_to(original);self.report()
 def test_linked_evidence_is_refused_even_when_digest_matches(self):
  link=self.root/'evidence.link';link.symlink_to(self.evidence);self.entry['state_evidence']['path']='projects/fixture/evidence.link';self.write_registry();self.report()
if __name__=='__main__':unittest.main()
