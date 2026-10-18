"""Source integrity, correction history and scoped prompt-delivery regressions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import crewloom
import host_lifecycle as hl
import model_host
import project_binding as pb
import project_context as pc
import repo_map
import user_context as uc

ROLE = 'context-guardian'


class UserContextTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, repo_map.git_environment(), clear=True)
        environment.start(); self.addCleanup(environment.stop)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        _, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        self.request = 'Keep the foundation English.\nالرد بالعربي.\nReduce errors, not add dashboards.\n'
        (self.root / 'request.txt').write_text(self.request, encoding='utf-8')
        pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])

    def child_worktree(self):
        for key,value in [('user.name','Acceptance'),('user.email','acceptance@example.invalid')]:
            subprocess.run(['git','config',key,value],cwd=self.root,check=True,env=repo_map.git_environment())
        subprocess.run(['git','commit','--allow-empty','-qm','Freeze test base'],cwd=self.root,check=True,env=repo_map.git_environment())
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        child=Path(temporary.name).resolve()/'child'
        subprocess.run(['git','worktree','add','--detach','-q',str(child),'HEAD'],cwd=self.root,check=True,env=repo_map.git_environment())
        pb.bootstrap(child,project_id='sample-project')
        return child

    def test_selected_context_reaches_worktree_and_refuses_parent_correction_on_resume(self):
        self.record();self.contract()
        # A different task's record must never be delivered to this child.
        pb.cancel(self.root,'sample-project','understand-task','Record another task before resuming')
        uc.record(self.root,'owner','other-secret','Reduce errors, not add dashboards.','request.txt',
                  'Reduce errors, not add dashboards.',task_id='other-task')
        pb.enter(self.root,'sample-project','understand-task',ROLE,seeds=['request.txt'])
        child=self.child_worktree()
        fingerprint=uc.inherit_task(self.root,child,'understand-task')
        selected=uc.select(child,'understand-task')
        self.assertEqual([r['key'] for r in selected['memories']],['response-language'])
        self.assertEqual(selected['memories'][0]['value'],'الرد بالعربي.')
        self.assertTrue(selected['contract']['source']['path'].startswith('.crewloom/private/inputs/inherited/'))
        self.assertEqual(uc.inherit_task(self.root,child,'understand-task',verify_only=True),fingerprint)
        self.record('Keep the foundation English.')
        with self.assertRaisesRegex(ValueError,'context changed'):
            uc.inherit_task(self.root,child,'understand-task',verify_only=True)

    def test_inheritance_refuses_foreign_project_and_modified_child_source(self):
        self.record();self.contract();child=self.child_worktree()
        uc.inherit_task(self.root,child,'understand-task')
        source=uc.select(child,'understand-task')['contract']['source']['path']
        (child/source).write_text('Changed inherited source')
        with self.assertRaises(ValueError):uc.inherit_task(self.root,child,'understand-task',verify_only=True)
        config=child/'crewloom.project.json';value=json.loads(config.read_text());value['project_id']='foreign-project';config.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'disagree'):uc.inherit_task(self.root,child,'understand-task')

    def record(self, value='الرد بالعربي.', **kwargs):
        return uc.record(self.root, 'owner', 'response-language', value, 'request.txt',
                         kwargs.pop('quote', value), task_id='understand-task', **kwargs)

    def contract(self, questions=None, user='owner'):
        return uc.contract(self.root, 'understand-task', user, 'Reduce output errors',
                           ['Keep project scope'], ['Measured fewer mistakes'], questions or [],
                           'request.txt', 'Reduce errors, not add dashboards.')

    def test_statement_is_quote_and_interpretation_stays_assumption(self):
        with self.assertRaisesRegex(ValueError, 'interpretations are assumptions'):
            self.record('Always use Arabic', quote='الرد بالعربي.')
        self.record('Always use Arabic', quote='الرد بالعربي.', kind='assumption')
        self.contract()
        self.assertEqual(uc.select(self.root, 'understand-task')['memories'][0]['kind'], 'assumption')

    def test_arabic_statement_and_english_contract_reach_actual_model_payload(self):
        self.record(); self.contract()
        pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])
        frozen = pc.load(self.root, {'project_id': 'sample-project', 'task_id': 'understand-task'})
        payload = model_host.project_context_payload(self.root, 'understand-task', {'inputs': ['request.txt']}, frozen)
        self.assertEqual(payload['user_context']['memories'][0]['value'], 'الرد بالعربي.')
        self.assertIn('not user confirmation', payload['user_context']['contract']['interpretation'])

    def test_missing_and_changed_sources_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'absent'):
            self.record('invented quote')
        self.record(); self.contract()
        (self.root / 'request.txt').write_text(self.request + 'changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            uc.select(self.root, 'understand-task')

    def test_correction_preserves_history_and_selects_latest(self):
        first = self.record()
        second = self.record('Keep the foundation English.')
        self.contract()
        self.assertEqual(second['supersedes'], first['id'])
        self.assertEqual(len(uc.load(self.root)['records']), 2)
        self.assertEqual(uc.select(self.root, 'understand-task')['memories'][0]['id'], second['id'])
        self.contract()
        self.assertEqual(len(uc.load(self.root)['contracts']['understand-task']['history']), 1)

    def test_later_assumption_preserves_the_quoted_statement(self):
        first = self.record()
        hypothesis = self.record('English replies inferred from foundation language',
                                 quote='Keep the foundation English.', kind='assumption')
        self.contract()
        self.assertIsNone(hypothesis['supersedes'])
        records = uc.select(self.root, 'understand-task')['memories']
        self.assertEqual([record['id'] for record in records], [first['id'], hypothesis['id']])
        self.assertEqual([record['kind'] for record in records], ['statement', 'assumption'])
        pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])
        frozen = pc.load(self.root, {'task_id': 'understand-task'})
        payload = model_host.project_context_payload(self.root, 'understand-task', {'inputs': ['request.txt']}, frozen)
        self.assertEqual([item['kind'] for item in payload['user_context']['memories']], ['statement', 'assumption'])
        native = hl.injected_context(self.root, pb.load_binding(self.root),
                                     {'host': 'codex', 'host_version': 'fixture', 'project_id': 'sample-project',
                                      'role': ROLE, 'declared_outputs': [], 'marker': 'test-receipt',
                                      'additional_context_limit': 65536}, frozen)
        self.assertIn(first['value'], native['additionalContext'])
        self.assertIn(hypothesis['value'], native['additionalContext'])
        correction = self.record('Keep the foundation English.')
        self.assertEqual(correction['supersedes'], first['id'])
        records = uc.select(self.root, 'understand-task')['memories']
        self.assertEqual([record['id'] for record in records], [correction['id'], hypothesis['id']])

    def test_task_hypothesis_does_not_erase_project_wide_quoted_statement(self):
        pb.cancel(self.root, 'sample-project', 'understand-task', 'fixture')
        first = uc.record(self.root, 'owner', 'response-language', 'الرد بالعربي.',
                          'request.txt', 'الرد بالعربي.')
        hypothesis = self.record('Maybe English replies', quote='Keep the foundation English.', kind='assumption')
        self.contract()
        records = uc.select(self.root, 'understand-task')['memories']
        self.assertEqual([record['id'] for record in records], [first['id'], hypothesis['id']])

    def test_user_and_task_are_not_inferred(self):
        self.record(); self.contract(user='other-user')
        self.assertEqual(uc.select(self.root, 'understand-task')['memories'], [])
        self.assertIsNone(uc.select(self.root, 'other-task'))

    def test_unresolved_questions_block_entry(self):
        self.contract(['Which output is intended?'])
        with self.assertRaisesRegex(ValueError, 'unresolved questions'):
            pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])

    def test_memory_change_invalidates_frozen_generation(self):
        self.record(); self.contract()
        pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])
        frozen = pc.load(self.root, {'project_id': 'sample-project', 'task_id': 'understand-task'})
        self.record('Keep the foundation English.')
        self.assertIn('user-context: interpretation or memory changed', pc.changed_files(self.root, frozen))

    def test_new_contract_also_invalidates_old_context(self):
        frozen = pc.load(self.root, {'project_id': 'sample-project', 'task_id': 'understand-task'})
        self.contract()
        self.assertIn('user-context: interpretation or memory changed', pc.changed_files(self.root, frozen))

    def test_foreign_checkout_storage_rejected(self):
        self.record(); self.contract()
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder).resolve()
            subprocess.run(['git', 'init', '-q'], cwd=other, check=True, env=repo_map.git_environment())
            crewloom.install_skills(other, 'agents', [ROLE], False)
            (other / 'request.txt').write_text(self.request)
            pb.enter(other, 'other-project', 'understand-task', ROLE, seeds=['request.txt'])
            shutil.copyfile(self.root / uc.RELATIVE, other / uc.RELATIVE)
            with self.assertRaisesRegex(ValueError, 'another project or checkout'):
                uc.select(other, 'understand-task')

    def test_symlink_source_and_active_other_task_rejected(self):
        (self.root / 'alias.txt').symlink_to(self.root / 'request.txt')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            uc.record(self.root, 'owner', 'language', 'الرد بالعربي.', 'alias.txt', 'الرد بالعربي.', task_id='understand-task')
        with self.assertRaisesRegex(ValueError, 'active context task'):
            uc.record(self.root, 'owner', 'language', 'الرد بالعربي.', 'request.txt', 'الرد بالعربي.', task_id='other-task')

    def test_task_value_overrides_project_value_and_other_users_stay_out(self):
        pb.cancel(self.root, 'sample-project', 'understand-task', 'fixture')
        uc.record(self.root, 'owner', 'response-language', 'Keep the foundation English.',
                  'request.txt', 'Keep the foundation English.')
        uc.record(self.root, 'other-user', 'other-key', 'الرد بالعربي.', 'request.txt', 'الرد بالعربي.')
        self.record(); self.contract()
        memories = uc.select(self.root, 'understand-task')['memories']
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]['value'], 'الرد بالعربي.')

    def test_malformed_kind_and_hardlinked_storage_rejected(self):
        self.record(); self.contract()
        path = self.root / uc.RELATIVE
        store = json.loads(path.read_text())
        store['records'][0]['kind'] = 'verified'
        path.write_text(json.dumps(store))
        with self.assertRaisesRegex(ValueError, 'Malformed memory kind'):
            uc.select(self.root, 'understand-task')
        path.unlink()
        self.record(); self.contract()
        os.link(path, self.root / 'linked-store')
        with self.assertRaisesRegex(ValueError, 'without hardlinks'):
            uc.select(self.root, 'understand-task')

    def test_native_delivery_keeps_user_context_mandatory_for_all_hosts(self):
        self.record(); self.contract()
        pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])
        frozen = pc.load(self.root, {'task_id': 'understand-task'})
        for host in ('codex', 'claude', 'opencode'):
            record = {'host': host, 'host_version': 'fixture', 'project_id': 'sample-project',
                      'role': ROLE, 'declared_outputs': [], 'marker': 'test-receipt',
                      'additional_context_limit': 65536}
            payload = hl.injected_context(self.root, pb.load_binding(self.root), record, frozen)
            self.assertIn('الرد بالعربي.', payload['additionalContext'])
            self.assertIn('Reduce output errors', payload['additionalContext'])
            self.assertEqual(payload['bytes'], len(payload['additionalContext'].encode('utf-8')))
            record['additional_context_limit'] = payload['bytes'] - 1
            with self.assertRaisesRegex(hl.LifecycleError, 'exceed'):
                hl.injected_context(self.root, pb.load_binding(self.root), record, frozen)

    def test_current_reused_archived_and_invalidated_contexts_are_owner_only(self):
        previous_umask = os.umask(0o022)
        try:
            self.record(); self.contract()
            pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])
            path = pc.context_path(self.root, 'understand-task')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            os.chmod(path, 0o644)
            pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.record('Keep the foundation English.')
            pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])
            pc.invalidate(self.root, 'understand-task', 'fixture')
            for copy in (self.root / '.crewloom/context').rglob('*.json'):
                self.assertEqual(copy.stat().st_mode & 0o777, 0o600, str(copy))
        finally:
            os.umask(previous_umask)


if __name__ == '__main__':
    unittest.main()
