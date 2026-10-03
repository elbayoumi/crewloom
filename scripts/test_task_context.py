"""Frozen context generations: scope, staleness, ranges, bodies, budgets and language parity."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import crewloom
import project_binding as pb
import project_context as pc
import repo_map
import workflow as w

ROLE = 'context-guardian'


class TaskContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        self.installed, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'auth.py').write_text('def login(user):\n    """Doc."""\n    return user\n', encoding='utf-8')
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / 'test_auth.py').write_text('from auth import login\n\ndef test_login():\n    assert login("a")\n',
                                                          encoding='utf-8')
        (self.root / 'ACCEPTANCE.md').write_text('- login returns the caller\n- Arabic label works\n',
                                                 encoding='utf-8')
        self.entered = pb.enter(self.root, 'sample-project', 'login-fix', ROLE,
                                seeds=['auth.py'], sources=['auth.py'], criteria_path='ACCEPTANCE.md')

    def context(self, task_id='login-fix'):
        binding = pb.load_binding(self.root)
        config, _ = pb.load_config(self.root)
        return pc.snapshot(self.root, binding, task_id, ROLE, config, ['- login returns the caller'],
                           ['auth.py'], 'en', ['auth.py'])

    def test_entry_freezes_a_scoped_generation_with_complete_rules_and_criteria(self):
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        binding = pb.load_binding(self.root)
        self.assertEqual(stored['scope']['project_id'], binding['project_id'])
        self.assertEqual(stored['scope']['checkout_id'], binding['checkout_id'])
        self.assertEqual(stored['scope']['project_root'], str(self.root))
        self.assertEqual(stored['scope']['task_id'], 'login-fix')
        guide = '.agents/skills/' + ROLE + '/SKILL.md'
        self.assertIn(guide, [item['path'] for item in stored['rules']])
        self.assertEqual(stored['criteria'], ['- login returns the caller', '- Arabic label works'])
        self.assertLessEqual(stored['bytes'], json.loads((self.root / pb.CONFIG_NAME).read_text())['budgets']['context_bytes'])
        self.assertTrue(stored['ranges'])
        self.assertIn('auth.py', [item['path'] for item in stored['bodies']])
        self.assertFalse(stored['provider']['usage_available'])

    def test_generation_is_reused_when_nothing_semantic_changes(self):
        first = self.entered['context']
        second = pb.enter(self.root, 'sample-project', 'login-fix', ROLE, seeds=['auth.py'],
                          sources=['auth.py'], criteria_path='ACCEPTANCE.md')['context']
        self.assertEqual(second['generation'], first['generation'])
        self.assertFalse(second['written'])
        self.assertEqual(second['semantic_sha256'], first['semantic_sha256'])
        (self.root / 'auth.py').write_text('def login(user):\n    """Doc."""\n    return user  # edit\n',
                                          encoding='utf-8')
        third = pb.enter(self.root, 'sample-project', 'login-fix', ROLE, seeds=['auth.py'],
                          sources=['auth.py'], criteria_path='ACCEPTANCE.md')['context']
        self.assertEqual(third['generation'], first['generation'] + 1)
        self.assertTrue(third['written'])

    def test_stale_range_reference_is_refused_after_a_source_change(self):
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        entry = next(item for item in stored['ranges'] if item['path'] == 'auth.py')
        text = pc.resolve_range(self.root, stored, entry['cache_key'], entry['path'], entry['start'], entry['end'])
        self.assertIn('login', text)
        (self.root / 'auth.py').write_text('def login(user):\n    return user\n# moved lines\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Stale line reference'):
            pc.resolve_range(self.root, stored, entry['cache_key'], entry['path'], entry['start'], entry['end'])
        with self.assertRaisesRegex(ValueError, 'stale'):
            pc.load(self.root, {'task_id': 'login-fix'})

    def test_unknown_or_mismatched_cache_keys_are_refused(self):
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        entry = stored['ranges'][0]
        with self.assertRaisesRegex(ValueError, 'Unknown range cache key'):
            pc.resolve_range(self.root, stored, 'a' * 64, entry['path'], entry['start'], entry['end'])
        with self.assertRaisesRegex(ValueError, 'does not match'):
            pc.resolve_range(self.root, stored, entry['cache_key'], entry['path'], 999, 1000)

    def test_context_scope_rejects_another_project_or_checkout(self):
        with self.assertRaisesRegex(ValueError, 'another project, checkout or task'):
            pc.load(self.root, {'task_id': 'login-fix', 'project_id': 'other-project'})
        with self.assertRaisesRegex(ValueError, 'another project, checkout or task'):
            pc.load(self.root, {'task_id': 'login-fix', 'checkout_id': 'b' * 32})
        with self.assertRaisesRegex(ValueError, 'No frozen context'):
            pc.load(self.root, {'task_id': 'unknown-task'})

    def test_identical_filenames_in_two_projects_never_share_a_context(self):
        with tempfile.TemporaryDirectory() as folder:
            twin = Path(folder).resolve() / 'twin'
            twin.mkdir()
            shutil_path = Path(self.root / '.agents')
            import shutil
            shutil.copytree(shutil_path, twin / '.agents')
            subprocess.run(['git', 'init', '-q'], cwd=twin, check=True, env=repo_map.git_environment())
            for name in ('auth.py', 'ACCEPTANCE.md'):
                (twin / name).write_text((self.root / name).read_text())
            shutil.copytree(self.root / 'tests', twin / 'tests')
            pb.enter(twin, 'twin-project', 'login-fix', ROLE, seeds=['auth.py'], sources=['auth.py'],
                     criteria_path='ACCEPTANCE.md')
            mine = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
            theirs = json.loads((twin / '.crewloom' / 'context' / 'login-fix.json').read_text())
            self.assertNotEqual(mine['sha256'], theirs['sha256'])
            self.assertNotEqual(mine['scope']['project_id'], theirs['scope']['project_id'])
            with self.assertRaises(ValueError):
                pc.load(twin, {'task_id': 'login-fix', 'project_id': 'sample-project'})

    def test_required_declared_bodies_fail_instead_of_disappearing(self):
        binding = pb.load_binding(self.root)
        config, _ = pb.load_config(self.root)
        (self.root / 'big.py').write_text('VALUE = "' + 'x' * 40000 + '"\n', encoding='utf-8')
        config['budgets']['context_bytes'] = 8192
        with self.assertRaisesRegex(ValueError, 'context_bytes|room for navigation'):
            pc.snapshot(self.root, binding, 'login-fix', ROLE, config, [], ['auth.py'], 'en', ['big.py'])
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        self.assertEqual([item['path'] for item in stored['bodies']], ['auth.py'])
        with self.assertRaisesRegex(ValueError, 'missing'):
            pc.snapshot(self.root, binding, 'login-fix', ROLE, config, [], ['auth.py'], 'en', ['absent.py'])

    def test_managed_calls_receive_only_declared_bodies(self):
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        (self.root / 'secret.py').write_text('SECRET = 1\n', encoding='utf-8')
        available = pc.bodies(self.root, stored)
        self.assertEqual(sorted(available), ['auth.py'])
        self.assertEqual(pc.bodies(self.root, stored, ['secret.py']), {})

    def test_omissions_are_recorded_for_optional_records_only(self):
        pb.cancel(self.root, 'sample-project', 'login-fix', 'fixture setup')
        for index in range(80):
            (self.root / ('noise%02d.py' % index)).write_text('def noise():\n    pass\n', encoding='utf-8')
        pb.enter(self.root, 'sample-project', 'second-task', ROLE, seeds=['auth.py'], sources=['auth.py'])
        stored = json.loads((self.root / '.crewloom' / 'context' / 'second-task.json').read_text())
        kinds = {item['kind'] for item in stored['omissions']}
        self.assertTrue(kinds <= {'map-files', 'map-seeds', 'map-seed-symbols', 'dependency-resolution',
                                  'indexed-names', 'lessons', 'navigation-trim'})
        self.assertNotIn('source-body', kinds)
        self.assertIn('auth.py', stored['navigation']['text'])

    def test_arabic_and_english_contexts_carry_the_same_evidence(self):
        english = self.context()
        binding = pb.load_binding(self.root)
        config, _ = pb.load_config(self.root)
        arabic = pc.snapshot(self.root, binding, 'login-fix-ar', ROLE, config, ['- login returns the caller'],
                             ['auth.py'], 'ar', ['auth.py'])
        self.assertEqual(set(english) - {'scope'}, set(arabic) - {'scope'})
        self.assertEqual(english['scope']['language'], 'en')
        self.assertEqual(arabic['scope']['language'], 'ar')
        self.assertEqual(english['navigation']['text'], arabic['navigation']['text'])
        self.assertEqual([item['cache_key'] for item in english['ranges']],
                         [item['cache_key'] for item in arabic['ranges']])
        self.assertEqual(english['criteria'], arabic['criteria'])
        self.assertEqual(english['omissions'], arabic['omissions'])

    def test_tampered_context_is_refused(self):
        path = self.root / '.crewloom' / 'context' / 'login-fix.json'
        stored = json.loads(path.read_text())
        stored['navigation']['text'] = 'rewritten'
        path.write_text(json.dumps(stored), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'fingerprint does not match'):
            pc.load(self.root, {'task_id': 'login-fix'})

    def test_invalidation_marks_the_generation_instead_of_deleting_it(self):
        marked = pc.invalidate(self.root, 'login-fix', 'source changed before publication')
        self.assertIn('source changed', marked['reason'])
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        self.assertEqual(stored['generation'], 1)
        self.assertEqual(stored['invalidated']['reason'], 'source changed before publication')

    def test_semantic_content_survives_telemetry_and_generation_churn(self):
        first = self.entered['context']
        (self.root / 'auth.py').write_text('def login(user):\n    """Doc."""\n    return user  # edit\n',
                                           encoding='utf-8')
        second = pb.enter(self.root, 'sample-project', 'login-fix', ROLE, seeds=['auth.py'],
                          sources=['auth.py'], criteria_path='ACCEPTANCE.md')['context']
        self.assertEqual(second['generation'], first['generation'] + 1)
        self.assertNotEqual(second['semantic_sha256'], first['semantic_sha256'])
        for _ in range(3):
            again = pb.enter(self.root, 'sample-project', 'login-fix', ROLE, seeds=['auth.py'],
                             sources=['auth.py'], criteria_path='ACCEPTANCE.md')['context']
            self.assertEqual(again['generation'], second['generation'])
            self.assertFalse(again['written'])
            self.assertEqual(again['semantic_sha256'], second['semantic_sha256'])
            self.assertEqual(again['bytes'], second['bytes'])
        # Telemetry values are derived at freeze time and never enter the semantic fingerprint.
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        stored['telemetry'] = {'parsed': 9999, 'reused': 8888, 'duration_ms': 123456,
                               'generated_at': '2099-01-01T00:00:00+00:00'}
        self.assertEqual(pc.semantic_digest(stored), second['semantic_sha256'])

    def test_immutable_history_keeps_the_original_generation_after_invalidation(self):
        original = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        pc.invalidate(self.root, 'login-fix', 'source changed before publication')
        archived = pc.history_path(self.root, 'login-fix', original['generation'])
        self.assertTrue(archived.is_file())
        kept = json.loads(archived.read_text())
        self.assertEqual(kept['semantic_sha256'], original['semantic_sha256'])
        self.assertFalse(kept.get('invalidated'))
        marked = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        self.assertTrue(marked['invalidated'])
        fresh = pc.snapshot(self.root, pb.load_binding(self.root), 'login-fix', ROLE,
                            pb.load_config(self.root)[0], ['- login returns the caller'],
                            ['auth.py'], 'en', ['auth.py'])
        frozen, written = pc.freeze(self.root, fresh)
        self.assertTrue(written)
        self.assertEqual(frozen['generation'], original['generation'] + 1)
        self.assertEqual(json.loads(archived.read_text())['semantic_sha256'], original['semantic_sha256'])

    def test_declared_body_and_ranges_are_hashed_against_the_real_file(self):
        stored = json.loads((self.root / '.crewloom' / 'context' / 'login-fix.json').read_text())
        body = stored['bodies'][0]
        self.assertEqual(body['sha256'], w.digest((self.root / body['path']).read_bytes()))
        self.assertEqual(body['text'], (self.root / body['path']).read_text())
        for item in stored['ranges']:
            self.assertEqual(len(item['cache_key']), 64)
            self.assertIn(item['path'], {'auth.py', 'tests/test_auth.py'})

    def test_rules_over_budget_are_refused_instead_of_truncated(self):
        binding = pb.load_binding(self.root)
        config, _ = pb.load_config(self.root)
        (self.root / 'AGENTS.md').write_text('RULE ' * 4000, encoding='utf-8')
        config['budgets']['context_bytes'] = 4096
        with self.assertRaisesRegex(ValueError, 'Governing rules and acceptance criteria exceed'):
            pc.snapshot(self.root, binding, 'login-fix', ROLE, config, [], ['auth.py'], 'en', [])


class DenseOptionalNavigationTests(unittest.TestCase):
    """A generous context ceiling is not a target for optional navigation hints.

    The reproduced failure was a large real project whose generation fitted only because it
    spent its remaining room on unrelated symbol ranges: the acceptance workflow that must
    read the whole snapshot back, plus the rules and declared sources, then no longer fitted
    the same frozen budget. Required evidence must survive; optional hints must not grow.
    """

    CONTEXT_BYTES = 131072

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        self.installed, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'AGENTS.md').write_text('# Project constitution\n' + 'Governing rule line.\n' * 700,
                                             encoding='utf-8')
        (self.root / 'ACCEPTANCE.md').write_text('- the acceptance command exits zero\n' * 40, encoding='utf-8')
        (self.root / 'loginpanel.tsx').write_text('export function renderLoginPanel() {\n  return "panel";\n}\n',
                                                  encoding='utf-8')
        for index in range(200):
            (self.root / ('panel_%03d.ts' % index)).write_text(
                "import { renderLoginPanel } from './loginpanel';\n\nexport function panelVariant%03d() {\n"
                '  return renderLoginPanel();\n}\n' % index, encoding='utf-8')
        for index in range(120):
            (self.root / ('loginpanel.%03d.test.tsx' % index)).write_text('\n'.join(
                'export function testLoginPanel%03dCase%02d() {\n  return true;\n}\n' % (index, case)
                for case in range(12)), encoding='utf-8')
        config = pb.default_config('dense-project')
        config['budgets'].update(context_bytes=self.CONTEXT_BYTES, map_bytes=8192, range_bytes=8192)
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        pb.enter(self.root, 'dense-project', 'dense-task', ROLE, seeds=['loginpanel.tsx'],
                 sources=['loginpanel.tsx'], criteria_path='ACCEPTANCE.md')

    def context(self):
        return json.loads((self.root / '.crewloom' / 'context' / 'dense-task.json').read_text())

    def test_dense_related_ranges_stay_inside_their_own_allowance(self):
        stored = self.context()
        config, _ = pb.load_config(self.root)
        spent = sum(pc.record_cost(item) for item in stored['ranges'])
        self.assertLessEqual(spent, config['budgets']['range_bytes'],
                             'Optional ranges must not fill the global ceiling')
        self.assertLessEqual(len(stored['ranges']), pc.MAX_RANGE_RECORDS)
        self.assertIn('loginpanel.tsx', [item['path'] for item in stored['ranges']],
                      'Seed ranges are required evidence and are never traded away')
        self.assertGreater(len(stored['tests']), pc.MAX_RANGE_RECORDS,
                           'The fixture must really saturate the optional range candidates')
        dropped = next(item for item in stored['omissions'] if item['kind'] == 'ranges')
        self.assertGreater(dropped['count'], len(stored['ranges']),
                           'Every omitted optional range must stay recorded')

    def test_acceptance_assembly_of_snapshot_rules_and_sources_fits_the_frozen_budget(self):
        stored = self.context()
        rules = sum(item['bytes'] for item in stored['rules'])
        declared = sum(item['bytes'] for item in stored['bodies'])
        self.assertLessEqual(stored['bytes'] + rules + declared, self.CONTEXT_BYTES,
                             'The whole snapshot plus its rules and sources must fit the frozen budget')
        self.assertLess(stored['bytes'], self.CONTEXT_BYTES // 2)

    def test_range_allowance_defaults_to_the_map_allocation_for_older_configurations(self):
        stored = self.context()
        config, _ = pb.load_config(self.root)
        del config['budgets']['range_bytes']
        (self.root / pb.CONFIG_NAME).write_text(json.dumps(config), encoding='utf-8')
        self.assertEqual(pc.range_budget(config), config['budgets']['map_bytes'])
        fresh = pc.snapshot(self.root, pb.load_binding(self.root), 'dense-task-legacy', ROLE, config,
                            stored['criteria'], ['loginpanel.tsx'], 'en', ['loginpanel.tsx'])
        spent = sum(pc.record_cost(item) for item in fresh['ranges'])
        self.assertLessEqual(spent, config['budgets']['map_bytes'])
        self.assertLessEqual(fresh['bytes'], self.CONTEXT_BYTES)


if __name__ == '__main__':
    unittest.main()
