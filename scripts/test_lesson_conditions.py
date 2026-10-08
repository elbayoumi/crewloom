"""R36/R37: lesson conditions are typed, evaluated or reported, and can never crash selection."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import crewloom
import project_binding as pb
import project_lessons as pl
import repo_map

ROLE = 'context-guardian'


class LessonConditionBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True, env=repo_map.git_environment())
        _, errors = crewloom.install_skills(self.root, 'agents', [ROLE], False)
        self.assertEqual(errors, [])
        (self.root / 'input.txt').write_text('input', encoding='utf-8')
        pb.enter(self.root, 'sample-project', 'lesson-task', ROLE, seeds=['input.txt'])
        self.binding = pb.load_binding(self.root)

    def verified(self, conditions, issue='Use the supported call form'):
        value = pl.record(self.root, self.binding, issue, 'Apply the documented form', conditions)['lesson']
        value['state'] = 'verified'
        value['verification'] = {'kind': 'objective', 'executed': True, 'evidence': []}
        pl.save(self.root, value)
        return value['id']

    def select(self, seeds=(), tokens=()):
        return pl.select(self.root, list(seeds), set(tokens), 10)

    def selected_ids(self, **kwargs):
        return [item['id'] for item in self.select(**kwargs)['lessons']]

    def lock(self, **versions):
        document = {'lockfileVersion': 3, 'packages': {'': {}, **{'node_modules/' + k: {'version': v}
                                                                for k, v in versions.items()}}}
        (self.root / 'package-lock.json').write_text(json.dumps(document), encoding='utf-8')

    # R36
    def test_dependency_only_condition_is_not_matched_by_an_empty_query(self):
        lesson = self.verified({'dependencies': ['requests']})
        result = self.select()
        self.assertEqual(result['lessons'], [])
        self.assertIn('not declared', result['ineligible'][0]['reason'])
        self.assertEqual(result['ineligible'][0]['id'], lesson)

    def test_declared_dependency_and_exact_locked_version_constraints_are_evaluated(self):
        self.lock(react='18.2.0')
        satisfied = self.verified({'dependencies': ['react>=18,<19']}, 'one')
        old = self.verified({'dependencies': ['react<18']}, 'two')
        exact = self.verified({'dependencies': ['react==18.2.0']}, 'three')
        result = self.select()
        self.assertEqual(sorted(item['id'] for item in result['lessons']), sorted([satisfied, exact]))
        self.assertIn(old, [item['id'] for item in result['ineligible']])

    def test_a_range_without_an_exact_resolution_is_ineligible_not_assumed(self):
        (self.root / 'package.json').write_text(json.dumps({'dependencies': {'react': '^18.0.0'}}), encoding='utf-8')
        constrained = self.verified({'dependencies': ['react>=18']}, 'constrained')
        named = self.verified({'dependencies': ['react']}, 'named')
        result = self.select()
        self.assertEqual([item['id'] for item in result['lessons']], [named])
        self.assertIn('no exact resolved version', next(i for i in result['ineligible'] if i['id'] == constrained)['reason'])

    def test_python_pins_and_normalised_names_resolve_from_requirements_and_pyproject(self):
        (self.root / 'requirements.txt').write_text('# comment\nFlask_Login==0.6.3\nrequests>=2\n', encoding='utf-8')
        (self.root / 'pyproject.toml').write_text('[project]\nname = "x"\ndependencies = ["SQLAlchemy==2.0.30"]\n',
                                                  encoding='utf-8')
        ids = [self.verified({'dependencies': [spec]}, spec)
               for spec in ('flask-login==0.6.3', 'sqlalchemy>=2,<3', 'flask.login<0.6')]
        self.assertEqual(sorted(self.selected_ids()), sorted(ids[:2]))

    def test_a_changed_lockfile_makes_a_version_bound_lesson_stale(self):
        self.lock(react='18.2.0')
        lesson = self.verified({'dependencies': ['react==18.2.0']})
        self.assertEqual(self.selected_ids(), [lesson])
        self.lock(react='19.0.0')
        result = self.select()
        self.assertEqual(result['lessons'], [])
        self.assertIn('manifest changed', result['ineligible'][0]['reason'])
        self.assertEqual(pl.revalidate(self.root), [lesson])
        self.assertEqual(pl.read(self.root, lesson)['state'], 'invalidated')

    def test_unsupported_dependency_conditions_are_refused_at_ingestion(self):
        for bad in ('', 'req uests>>2', 'react~=18', 'react>=1.x', '>=1'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pl.validate_conditions({'dependencies': [bad]} if bad else {'dependencies': [bad]})

    # R37
    def test_malformed_regular_expression_text_is_a_literal_and_never_raises(self):
        lesson = self.verified({'paths': ['[', '(unclosed', 'src/*.py']})
        self.assertEqual(self.selected_ids(seeds=['notes/[draft].md']), [lesson])
        self.assertEqual(self.selected_ids(seeds=['src/a.py']), [lesson])
        self.assertEqual(self.selected_ids(seeds=['README.md']), [])

    def test_a_dot_is_not_a_wildcard_any_more(self):
        self.verified({'paths': ['a.py']})
        self.assertEqual(self.selected_ids(seeds=['aXpy']), [])
        self.assertEqual(len(self.selected_ids(seeds=['pkg/a.py'])), 1)

    def test_overlong_or_control_character_patterns_are_refused(self):
        for bad in ('x' * 201, 'line\nbreak'):
            with self.subTest(bad=bad[:10]), self.assertRaises(ValueError):
                pl.validate_conditions({'paths': [bad]})

    def test_existing_invalid_or_unreadable_records_are_reported_and_preserved(self):
        good = self.verified({'paths': ['input.txt']}, 'good')
        broken = self.verified({'paths': ['input.txt']}, 'broken')
        path = self.root / '.crewloom/lessons' / (broken + '.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        record['conditions'] = {'paths': 5}
        path.write_text(json.dumps(record), encoding='utf-8')
        garbage = self.root / '.crewloom/lessons' / ('a' * 32 + '.json')
        garbage.write_text('{not json', encoding='utf-8')
        result = self.select(seeds=['input.txt'])
        self.assertEqual([item['id'] for item in result['lessons']], [good])
        reasons = {item['id']: item['reason'] for item in result['ineligible']}
        self.assertIn('malformed', reasons[broken])
        self.assertIn('unreadable', reasons['a' * 32])
        self.assertTrue(path.is_file() and garbage.is_file(), 'history is not deleted')

    def test_imported_packets_with_invalid_conditions_are_refused(self):
        packet = self.root / 'packet.json'
        packet.write_text(json.dumps({'schema_version': 1, 'project_id': 'sample-project', 'lessons': [
            {'sanitized': True, 'issue': 'x', 'remedy': 'y', 'conditions': {'dependencies': ['bad bad>>']}}]}),
            encoding='utf-8')
        with self.assertRaises(ValueError):
            pl.import_reviewed(self.root, str(packet), self.binding)


if __name__ == '__main__':
    unittest.main()
