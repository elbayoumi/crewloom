"""Map cache freshness, safe scope, bounded selection and prompt integration."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import repo_map as m
import model_host as h


class MapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        subprocess.run(['git','init','-q'],cwd=self.root,check=True)
        (self.root/'auth.py').write_text('import os\ndef login(user):\n    return user\n')
        (self.root/'other.ts').write_text('export function checkout() { return 1; }\n')

    def test_public_cli_works_with_project_flags(self):
        executable=Path(m.__file__).parent/'crewloom.py'
        result=subprocess.run(['python3',str(executable),'map','--project',str(self.root),'--query','login'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('login',json.loads(result.stdout)['map'])

    def test_symbols_and_cache_reuse(self):
        value,first=m.build(self.root);_,second=m.build(self.root)
        self.assertEqual(first['parsed'],2);self.assertEqual(second['parsed'],0)
        self.assertEqual(second['reused'],2)
        self.assertEqual(value['files']['auth.py']['symbols'][0]['name'],'login')

    def test_changed_added_and_removed_files_refresh(self):
        m.build(self.root);(self.root/'auth.py').write_text('def logout():\n    pass\n')
        (self.root/'other.ts').unlink();(self.root/'new.py').write_text('class Added: pass\n')
        value,stats=m.build(self.root)
        self.assertEqual(set(value['files']),{'auth.py','new.py'});self.assertEqual(stats['parsed'],2)
        self.assertEqual(value['files']['auth.py']['symbols'][0]['name'],'logout')

    def test_ignored_secrets_and_generated_files_absent(self):
        (self.root/'.gitignore').write_text('private.py\n')
        (self.root/'private.py').write_text('def secret(): pass\n')
        (self.root/'.env').write_text('key=private')
        (self.root/'node_modules').mkdir();(self.root/'node_modules/a.py').write_text('def noise(): pass')
        value,_=m.build(self.root);self.assertEqual(set(value['files']),{'auth.py','other.ts'})

    def test_symlink_and_foreign_cache_rejected(self):
        (self.root/'alias.py').symlink_to(self.root/'auth.py')
        with self.assertRaises(ValueError):m.build(self.root)
        (self.root/'alias.py').unlink();m.build(self.root)
        cache=self.root/'.crewloom/repo-map.json';value=json.loads(cache.read_text());value['project_root']='/another-project';cache.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'another project'):m.build(self.root)

    def test_selection_is_bounded_and_relevant(self):
        for i in range(60):(self.root/f'noise{i}.py').write_text('def unrelated(): pass\n')
        value,_=m.build(self.root);text,stats=m.render(value,'login',1024)
        self.assertIn('login',text);self.assertLessEqual(len(text.encode()),1024)
        self.assertGreater(stats['omitted_files'],0)
        with self.assertRaises(ValueError):m.render(value,'',1)

    def test_model_prompt_map_is_explicit_opt_in_and_keeps_inputs(self):
        folder=self.root/'.agents/skills/fullstack-mvp-engineer';folder.mkdir(parents=True)
        (folder/'SKILL.md').write_text('Project guidance')
        step={'role':'fullstack-mvp-engineer','summary':'login','inputs':['auth.py'],'outputs':['result.py']}
        with patch('workflow.project_role',return_value={'ready':True,'guide':str(folder/'SKILL.md')}):
            plain=json.loads(h.build_prompt(self.root,step,'en').split('\n',1)[1])
            mapped=json.loads(h.build_prompt(self.root,dict(step,repo_map=True),'en').split('\n',1)[1])
        self.assertNotIn('repo_map',plain);self.assertIn('repo_map',mapped)
        self.assertEqual(plain['inputs'],mapped['inputs'])


if __name__=='__main__':unittest.main()
