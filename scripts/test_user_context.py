"""Source integrity, correction history and scoped prompt-delivery regressions."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import crewloom
import model_host
import project_binding as pb
import project_context as pc
import repo_map
import user_context as uc

ROLE = 'context-guardian'


class UserContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        _, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        self.request = 'Keep the foundation English.\nالرد بالعربي.\nReduce errors, not add dashboards.\n'
        (self.root / 'request.txt').write_text(self.request, encoding='utf-8')
        pb.enter(self.root, 'sample-project', 'understand-task', ROLE, seeds=['request.txt'])

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
        (self.root / 'linked-store').hardlink_to(path)
        with self.assertRaisesRegex(ValueError, 'without hardlinks'):
            uc.select(self.root, 'understand-task')


if __name__ == '__main__':
    unittest.main()
