"""Catalog identities, overlap, redirects, concurrent mutation and read-only status."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import project_binding as pb

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve(); self.catalog = self.base / 'catalog.json'
        self.a = self.base / 'a'; self.b = self.base / 'b'
        for root, ident in ((self.a, 'project-a'), (self.b, 'project-b')):
            root.mkdir(); pb.bootstrap(root, ident)

    def add(self, root=None, ident='project-a'):
        return pb.catalog_update(self.catalog, 'add', root or self.a, ident)

    def test_distinct_roots_and_idempotent_add(self):
        self.add(); self.add(); self.add(self.b, 'project-b')
        self.assertEqual(len(pb.read_catalog(self.catalog)['projects']), 2)

    def test_same_id_other_checkout_and_same_root_other_id_refused(self):
        self.add()
        with self.assertRaises(ValueError): self.add(self.b)
        with self.assertRaises(ValueError): self.add(self.a, 'project-b')

    def test_nested_binding_rejected_before_writes(self):
        nested = self.a / 'child'; nested.mkdir()
        with self.assertRaisesRegex(ValueError, 'nested'): pb.bootstrap(nested, 'child-project')
        self.assertFalse((nested / '.crewloom').exists())
        self.assertFalse((nested / '.gitignore').exists())

    def test_parent_registration_refused(self):
        self.add()
        with self.assertRaisesRegex(ValueError, 'overlaps'): pb.catalog_guard(self.base, 'parent', self.catalog)

    def test_redirected_catalog_and_hardlink_refused(self):
        self.add(); link = self.base / 'link.json'; link.symlink_to(self.catalog)
        with self.assertRaisesRegex(ValueError, 'symlink'): pb.read_catalog(link)
        hard = self.base / 'hard.json'; os.link(self.catalog, hard)
        with self.assertRaisesRegex(ValueError, 'hardlinks'): pb.read_catalog(hard)

    def test_stale_identity_reported_without_rebinding(self):
        self.add(); binding = self.a / pb.BINDING_RELATIVE
        data = json.loads(binding.read_text()); data['checkout_id'] = 'f' * 32; binding.write_text(json.dumps(data))
        report = pb.catalog_overview(self.catalog)['projects'][0]
        self.assertFalse(report['available']); self.assertIn('identity changed', report['error'])

    def test_unknown_schema_and_overlapping_records_refused(self):
        self.add(); data = pb.read_catalog(self.catalog)
        item = dict(data['projects'][0], project_id='other-project', project_root=str(self.a / 'nested'))
        data['projects'].append(item); self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'overlapping'): pb.read_catalog(self.catalog)

    def test_catalog_must_live_outside_projects(self):
        with self.assertRaisesRegex(ValueError, 'outside'): pb.catalog_update(self.a / 'catalog.json', 'add', self.a, 'project-a')

    def test_overview_read_only_and_project_task_separation(self):
        self.add(); self.add(self.b, 'project-b')
        before = {str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()}
        overview = pb.catalog_overview(self.catalog)
        self.assertTrue(all(p['available'] for p in overview['projects']))
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.base.rglob('*') if p.is_file()})

    def test_concurrent_mutation_never_loses_an_entry(self):
        barrier = threading.Barrier(2); failures = []
        def worker(root, ident):
            barrier.wait()
            try: self.add(root, ident)
            except ValueError: failures.append((root, ident))
        threads = [threading.Thread(target=worker, args=(r,i)) for r,i in ((self.a,'project-a'),(self.b,'project-b'))]
        for t in threads: t.start()
        for t in threads: t.join()
        for r,i in failures: self.add(r,i)
        self.assertEqual(len(pb.read_catalog(self.catalog)['projects']),2)

    def test_env_catalog_rejects_overlap_before_bootstrap(self):
        self.add(); outer = self.base.parent
        with patch.dict(os.environ, {'CREWLOOM_CATALOG':str(self.catalog)}):
            with self.assertRaisesRegex(ValueError, 'overlaps'): pb.catalog_guard(outer, 'other')

    def test_folded_paths_are_conservative(self):
        self.assertTrue(pb.roots_overlap('/projects/Demo', '/projects/demo/child'))
        self.assertFalse(pb.roots_overlap('/projects/demo', '/projects/demo-two'))

    def test_redirected_project_is_unavailable_and_can_be_removed(self):
        self.add(); moved = self.base / 'moved'; self.a.rename(moved); self.a.symlink_to(moved)
        self.assertFalse(pb.catalog_overview(self.catalog)['projects'][0]['available'])
        pb.catalog_update(self.catalog, 'remove', project_id='project-a')
        self.assertEqual(pb.read_catalog(self.catalog)['projects'], [])


class CatalogCommandTests(unittest.TestCase):
    setUp = CatalogTests.setUp
    add = CatalogTests.add
    def test_cancel_only_selected_project_preserves_other_task(self):
        import contextlib, io
        for root, ident in ((self.a, 'project-a'), (self.b, 'project-b')):
            binding = pb.load_binding(root)
            pb.save_task_state(root, {'schema_version':1, 'task_id':'same-task', 'status':'active', 'project_root':str(root), 'project_id':ident, 'checkout_id':binding['checkout_id']})
            pb.reserve(root, binding, 'same-task', 'context-guardian')
            self.add(root, ident)
        before = (self.b / '.crewloom/tasks/same-task/state.json').read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            code = pb.catalog_main(['cancel-task','--catalog',str(self.catalog),'--project-id','project-a','--task-id','same-task'])
        self.assertEqual(code,0)
        self.assertEqual(pb.task_state(self.a,'same-task')['status'],'cancelled')
        self.assertEqual((self.b / '.crewloom/tasks/same-task/state.json').read_bytes(),before)

    def test_copied_checkout_task_is_unavailable_and_cannot_be_cancelled(self):
        import contextlib, io
        self.add()
        pb.save_task_state(self.a, {'schema_version':1, 'task_id':'same-task', 'status':'active',
                                  'project_root':str(self.a), 'project_id':'project-a', 'checkout_id':'f'*32})
        self.assertFalse(pb.catalog_overview(self.catalog)['projects'][0]['available'])
        before=(self.a/'.crewloom/tasks/same-task/state.json').read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pb.catalog_main(['cancel-task','--catalog',str(self.catalog),'--project-id','project-a','--task-id','same-task']),2)
        self.assertEqual(before,(self.a/'.crewloom/tasks/same-task/state.json').read_bytes())

    def test_setup_preserves_installed_memory_and_is_idempotent(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pb.main(['setup','--project',str(self.a),'--project-id','project-a']),0)
        brain = self.a / '.agents/skills/context-guardian/brain/COMPLETED.md'; brain.write_text('Private memory\n')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pb.main(['setup','--project',str(self.a),'--project-id','project-a']),0)
        self.assertEqual(brain.read_text(),'Private memory\n')

    def test_cancel_refuses_workflow_owner(self):
        import contextlib, io
        self.add()
        pb.write_json(self.a,'.crewloom/active_workflow.json',{'project_root':str(self.a),'workflow':'one','plan_sha256':'a'*64})
        with contextlib.redirect_stdout(io.StringIO()):
            code=pb.catalog_main(['cancel-task','--catalog',str(self.catalog),'--project-id','project-a','--task-id','same-task'])
        self.assertEqual(code,2)
        self.assertTrue((self.a/'.crewloom/active_workflow.json').exists())

if __name__ == '__main__': unittest.main()
