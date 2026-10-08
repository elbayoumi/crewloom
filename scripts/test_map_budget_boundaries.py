"""R38/R39: serialized map bytes stay inside the budget, and every reached module is represented or named."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import repo_map


class MapBudgetBoundaries(unittest.TestCase):
    def project(self, files):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        env = repo_map.git_environment()
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True, env=env)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding='utf-8')
        subprocess.run(['git', 'add', '--', '.'], cwd=root, check=True, env=env)
        value, _ = repo_map.build(root)
        return root, value

    # R38
    def test_missing_seed_notice_cannot_push_the_map_over_its_budget(self):
        root, value = self.project({'src/a.py': 'def a():\n    return 1\n'})
        names = ['missing/module_%03d.py' % index for index in range(16)]
        for budget in (1024, 2048, 8192):
            with self.subTest(budget=budget):
                text, receipt = repo_map.render(value, 'a', budget, ['src/a.py'] + names)
                self.assertLessEqual(len(text.encode()), budget)
                self.assertEqual(receipt['map_bytes'], len(text.encode()))
                self.assertEqual(receipt['missing_seed_files'], names, 'the complete receipt is retained')
                self.assertIn('src/a.py', text, 'the present seed is still represented')
                if budget < 4096:
                    self.assertIn('missing_seed_files', text, 'the visible summary says names were left out')

    def test_a_short_missing_list_is_listed_completely(self):
        _, value = self.project({'src/a.py': 'def a():\n    return 1\n'})
        text, receipt = repo_map.render(value, 'a', 1024, ['src/a.py', 'gone.py'])
        self.assertIn('Seed files absent from this index: gone.py', text)
        self.assertNotIn('more;', text)

    def test_every_budget_and_seed_count_stays_inside_the_final_bytes(self):
        _, value = self.project({'src/%02d.py' % index: 'def f%d():\n    return %d\n' % (index, index)
                                 for index in range(12)})
        for count in (0, 1, 7, 40, 63):
            for budget in (1024, 1500, 4096):
                seeds = ['src/00.py'] + ['absent/%d.py' % index for index in range(count)]
                with self.subTest(count=count, budget=budget):
                    text, _ = repo_map.render(value, 'f', budget, seeds)
                    self.assertLessEqual(len(text.encode()), budget)

    # R39
    def closure(self, files, budget):
        root, value = self.project(files)
        return repo_map.closure_context(root, value, ['src/main.py'], budget)

    def represented(self, result, path):
        return (any(item['path'] == path for item in result['closure'])
                or any(item['path'] == path for item in result['signatures']) or path in result['omitted'])

    def test_a_reached_constants_module_that_cannot_fit_is_named_as_omitted(self):
        result = self.closure({'src/main.py': 'from src.data import VALUE\n\n\ndef run():\n    return VALUE\n',
                               'src/data.py': 'VALUE = "' + 'x' * 3000 + '"\n'}, 1024)
        self.assertEqual([item['path'] for item in result['closure']], [])
        self.assertIn('src/data.py', result['omitted'])
        self.assertLessEqual(result['bytes'], 1024)

    def test_every_reached_module_shape_is_present_partial_or_omitted(self):
        files = {
            'src/main.py': 'from src.consts import A\nfrom src.init import B\nfrom src.empty import C\n'
                           'from src.broken import D\nfrom src.defs import work\n',
            'src/consts.py': 'A = 1\n',
            'src/init.py': 'import os\nB = os.getcwd()\n' + 'PAD = "' + 'p' * 1500 + '"\n',
            'src/empty.py': '',
            'src/broken.py': 'def (:\n    pass\n' + '# ' + 'z' * 1500 + '\n',
            'src/defs.py': 'def work():\n    """Do the work."""\n    return 1\n',
        }
        for budget in (1024, 1536, 4096, 65536):
            result = self.closure(files, budget)
            for path in ('src/consts.py', 'src/init.py', 'src/empty.py', 'src/broken.py', 'src/defs.py'):
                with self.subTest(budget=budget, path=path):
                    self.assertTrue(self.represented(result, path), result['omitted'])
            self.assertLessEqual(result['bytes'], budget)
            self.assertEqual(len(result['omitted']), len(set(result['omitted'])))

    def test_a_roomy_budget_keeps_the_full_body_and_omits_nothing(self):
        result = self.closure({'src/main.py': 'from src.data import VALUE\n',
                               'src/data.py': 'VALUE = 1\n'}, 4096)
        self.assertEqual([item['path'] for item in result['closure']], ['src/data.py'])
        self.assertEqual(result['omitted'], [])


if __name__ == '__main__':
    unittest.main()
