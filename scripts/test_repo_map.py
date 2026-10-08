"""Map freshness, generations, seed visibility, import accuracy and prompt integration."""
import ast
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import repo_map as m
import model_host as h


def git(root,*argv):
    # An isolated CI container has no user Git configuration; the fixture sets its own identity.
    # `m.git_environment()` drops inherited repository, index and configuration overrides, so a
    # fixture commit can never land in the repository that happens to be committing this suite.
    identity=['-c','user.name=Crewloom Fixture','-c','user.email=fixture@example.invalid']
    subprocess.run(['git',*(identity if argv and argv[0]=='commit' else []),*argv],cwd=root,check=True,
                   capture_output=True,env=m.git_environment())


class MapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        subprocess.run(['git','init','-q'],cwd=self.root,check=True,env=m.git_environment())
        (self.root/'auth.py').write_text('import os\ndef login(user):\n    return user\n')
        (self.root/'other.ts').write_text('export function checkout() { return 1; }\n')

    def test_arabic_query_expands_visible_technical_terms_and_ranks_matching_source(self):
        value, _ = m.build(self.root)
        text, receipt = m.render(value, 'مصادقة', 1024)
        self.assertLess(text.index('auth.py'), text.index('other.ts'))
        self.assertIn('auth', receipt['query_expansions'])
        self.assertIn('query:auth', receipt['selection_reasons']['auth.py'])
        self.assertEqual(m.query_terms('untranslated_identifier')[0], {'untranslated_identifier'})
        with self.assertRaises(ValueError): m.query_terms('x' * 8193)

    def test_transitive_dependencies_are_ranked_and_missing_closure_is_visible(self):
        value = {'files': {}, 'graph_complete': True}
        for name, dependencies in [('entry.py', ['one.py']), ('one.py', ['two.py']), ('two.py', []), ('other.py', [])]:
            value['files'][name] = {'parser': 'fixture', 'parser_version': 1, 'symbols': [], 'neighbours': dependencies}
        text, receipt = m.render(value, '', 1024, ['entry.py'])
        self.assertLess(text.index('two.py'), text.index('other.py'))
        self.assertEqual(receipt['dependency_omission_count'], 0)
        self.assertTrue(receipt['navigation_sufficient'])
        value['files']['one.py']['neighbours'].append('missing.py')
        _, receipt = m.render(value, '', 1024, ['entry.py'])
        self.assertFalse(receipt['navigation_sufficient'])
        self.assertIn('missing.py', receipt['dependency_omissions'])

    def test_public_cli_works_with_project_flags(self):
        executable=Path(m.__file__).parent/'crewloom.py'
        result=subprocess.run(['python3',str(executable),'map','--project',str(self.root),'--query','login'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        payload=json.loads(result.stdout)
        self.assertIn('login',payload['map'])
        self.assertEqual(payload['stats']['generation'],m.GENERATION_VERSION)

    def test_symbols_and_cache_reuse(self):
        value,first=m.build(self.root);_,second=m.build(self.root)
        self.assertEqual(first['parsed'],2);self.assertEqual(second['parsed'],0)
        self.assertEqual(second['reused'],2)
        self.assertEqual(value['files']['auth.py']['symbols'][0]['name'],'login')

    def test_equal_size_edit_is_detected_by_hash(self):
        m.build(self.root);(self.root/'auth.py').write_text('import os\ndef login(user):\n    return user\n')
        value,stats=m.build(self.root)
        self.assertEqual(stats['parsed'],0)
        (self.root/'auth.py').write_text('import os\ndef login(users):\n    return users\n')
        value,stats=m.build(self.root)
        self.assertEqual(stats['parsed'],1)
        self.assertEqual(value['files']['auth.py']['symbols'][0]['name'],'login')

    def test_changed_added_and_removed_files_refresh(self):
        m.build(self.root);(self.root/'auth.py').write_text('def logout():\n    pass\n')
        (self.root/'other.ts').unlink();(self.root/'new.py').write_text('class Added: pass\n')
        value,stats=m.build(self.root)
        self.assertEqual(set(value['files']),{'auth.py','new.py'});self.assertEqual(stats['parsed'],2)
        self.assertEqual(value['files']['auth.py']['symbols'][0]['name'],'logout')
        self.assertEqual(stats['deleted'],['other.ts'])

    def test_branch_switch_keeps_content_verified_reuse(self):
        git(self.root,'add','-A');git(self.root,'commit','-qm','first');git(self.root,'branch','feature')
        m.build(self.root);git(self.root,'checkout','-q','feature')
        _,stats=m.build(self.root)
        self.assertEqual(stats['branch'],'feature')
        self.assertEqual(stats['parsed'],0);self.assertEqual(stats['reused'],2)
        (self.root/'feature.py').write_text('def feature():\n    pass\n')
        value,stats=m.build(self.root)
        self.assertEqual(stats['parsed'],1)
        self.assertIn('feature.py',value['files'])
        self.assertGreaterEqual(stats['nominated']['untracked'],1)

    def test_rename_moves_navigation_without_inventing_evidence(self):
        git(self.root,'add','-A');git(self.root,'commit','-qm','first')
        git(self.root,'mv','auth.py','session.py')
        value,stats=m.build(self.root)
        self.assertIn('session.py',value['files']);self.assertNotIn('auth.py',value['files'])
        self.assertEqual(stats['renamed'],[{'from':'auth.py','to':'session.py'}])

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
        cache=self.root/'.crewloom/index/map.json';value=json.loads(cache.read_text());value['project_root']='/another-project';cache.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'another project'):m.build(self.root)

    def test_corrupt_cache_rebuilds_and_records_recovery(self):
        m.build(self.root);(self.root/'.crewloom/index/map.json').write_text('{"files":')
        _,stats=m.build(self.root)
        self.assertEqual(stats['prior_state'],'recovered-corrupt-cache')
        self.assertEqual(stats['parsed'],2)

    def test_parser_upgrade_forces_reparse(self):
        m.build(self.root)
        cache=self.root/'.crewloom/index/map.json';value=json.loads(cache.read_text())
        for entry in value['files'].values():entry['parser_version']=0
        cache.write_text(json.dumps(value))
        _,stats=m.build(self.root)
        self.assertEqual(stats['parsed'],2)

    def test_foreign_checkout_identity_blocks_cache_write(self):
        (self.root/'.crewloom').mkdir()
        (self.root/'.crewloom/binding.json').write_text(json.dumps(
            {'schema_version':1,'project_id':'sample-project','checkout_id':'a'*32,'project_root':str(self.root)}))
        m.build(self.root)
        cache=self.root/'.crewloom/index/map.json';value=json.loads(cache.read_text())
        self.assertEqual(value['checkout_id'],'a'*32)
        value['checkout_id']='b'*32;cache.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'another project or checkout'):m.build(self.root)

    def test_python_relative_and_absolute_import_neighbours(self):
        (self.root/'pkg').mkdir()
        (self.root/'pkg/__init__.py').write_text('')
        (self.root/'pkg/core.py').write_text('from .helper import build\nfrom ..auth import login\nimport os\n')
        (self.root/'pkg/helper.py').write_text('def build():\n    pass\n')
        value,_=m.build(self.root)
        self.assertEqual(value['files']['pkg/core.py']['neighbours'],['auth.py','pkg/helper.py'])
        self.assertEqual(value['files']['auth.py']['neighbours'],[])
        self.assertNotIn('os',value['files']['pkg/core.py']['neighbours'])

    def test_js_relative_import_resolves_and_packages_are_reported_unresolved(self):
        (self.root/'src').mkdir()
        (self.root/'src/app.ts').write_text("import { helper } from './util';\nimport React from 'react';\nexport function app() { return helper(); }\n")
        (self.root/'src/util.ts').write_text('export function helper() { return 1; }\n')
        value,_=m.build(self.root)
        self.assertEqual(value['files']['src/app.ts']['neighbours'],['src/util.ts'])
        # A package outside the project is classified external and still counted unresolved,
        # because this index cannot link it either way.
        self.assertEqual(value['files']['src/app.ts']['external'],['react'])
        self.assertIn('react','\n'.join(value['files']['src/app.ts']['unresolved']))
        self.assertFalse(value['graph_complete'])
        if m.JS_GRAMMAR:
            self.assertEqual(value['files']['src/app.ts']['parser'],'ts-ast')
            self.assertNotIn('js-ts-symbols-approximate-no-tree-sitter',value['unsupported'])
            self.assertTrue(value['syntax']['available'])
        else:
            self.assertEqual(value['files']['src/app.ts']['parser'],'approximate-js-ts')
            self.assertIn('js-ts-symbols-approximate-no-tree-sitter',value['unsupported'])
            self.assertFalse(value['syntax']['available'])

    def test_syntax_error_file_is_visible_as_incomplete(self):
        (self.root/'broken.py').write_text('def oops(\n')
        value,_=m.build(self.root)
        self.assertEqual(value['files']['broken.py']['parser'],'syntax-error')
        self.assertIn('broken.py',value['incomplete_files'])

    def test_seed_path_survives_an_oversized_symbol_block(self):
        for index in range(40):(self.root/f'filler{index}.py').write_text('def filler():\n    pass\n')
        (self.root/'wide.py').write_text(''.join('def symbol_%d():\n    pass\n'%index for index in range(200)))
        value,_=m.build(self.root)
        text,stats=m.render(value,'filler',1024,['wide.py'])
        self.assertIn('wide.py',text)
        self.assertEqual(stats['truncated_seed_files'],['wide.py'])
        self.assertLessEqual(len(text.encode()),1024)

    def test_missing_seed_is_reported_not_hidden(self):
        value,_=m.build(self.root)
        text,stats=m.render(value,'login',2048,['absent.py'])
        self.assertEqual(stats['missing_seed_files'],['absent.py'])
        self.assertIn('absent.py',text)

    def test_selection_is_bounded_and_relevant(self):
        for index in range(60):(self.root/f'noise{index}.py').write_text('def unrelated(): pass\n')
        value,_=m.build(self.root);text,stats=m.render(value,'login',1024)
        self.assertIn('login',text);self.assertLessEqual(len(text.encode()),1024)
        self.assertGreater(stats['omitted_files'],0)
        with self.assertRaises(ValueError):m.render(value,'',1)

    def test_map_never_claims_a_complete_graph(self):
        value,_=m.build(self.root)
        text,_=m.render(value,'login',4096)
        self.assertIn('partial',text)
        # A standard-library import is an external dependency, not an unresolved project edge.
        self.assertEqual(value['files']['auth.py']['unresolved'],[])
        self.assertTrue(value['graph_complete'])
        (self.root/'absent_dependency.py').write_text('import crewloom_absent_dependency\ndef helper(): pass\n')
        later,_=m.build(self.root)
        self.assertFalse(later['graph_complete'])
        self.assertEqual(later['files']['absent_dependency.py']['unresolved'],
                         ['import crewloom_absent_dependency'])

    def test_legacy_root_only_cache_is_migrated_once(self):
        legacy = self.root / '.crewloom' / 'repo-map.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_text(json.dumps({'version': 1, 'project_root': str(self.root), 'files': {}}))
        value, stats = m.build(self.root)
        self.assertTrue(stats['legacy_cache_migrated'])
        self.assertEqual(json.loads((self.root / '.crewloom/index/map.json').read_text())['generation'],
                         m.GENERATION_VERSION)
        self.assertFalse(legacy.exists())
        _, again = m.build(self.root)
        self.assertFalse(again['legacy_cache_migrated'])

    def test_budget_and_file_limits_fail_before_writes(self):
        with self.assertRaisesRegex(ValueError,'budget'):m.render(m.build(self.root)[0],'x',64)
        cache=self.root/'.crewloom/index/map.json'
        with patch.object(m,'MAX_FILE',4):
            with self.assertRaises(ValueError):m.build(self.root)
        self.assertEqual(json.loads(cache.read_text())['generation'],m.GENERATION_VERSION)

    def test_non_git_root_is_unsupported_and_never_initialized(self):
        with tempfile.TemporaryDirectory() as folder:
            plain=Path(folder).resolve();(plain/'a.py').write_text('def a(): pass\n')
            with self.assertRaisesRegex(ValueError,'Git project'):m.build(plain)
            self.assertFalse((plain/'.git').exists())

    def test_model_prompt_map_is_explicit_opt_in_and_keeps_inputs(self):
        folder=self.root/'.agents/skills/fullstack-mvp-engineer';folder.mkdir(parents=True)
        (folder/'SKILL.md').write_text('Project guidance')
        step={'role':'fullstack-mvp-engineer','summary':'login','inputs':['auth.py'],'outputs':['result.py']}
        with patch('workflow.project_role',return_value={'ready':True,'guide':str(folder/'SKILL.md')}):
            plain=json.loads(h.build_prompt(self.root,step,'en').split('\n',1)[1])
            mapped=json.loads(h.build_prompt(self.root,dict(step,repo_map=True),'en').split('\n',1)[1])
        self.assertNotIn('repo_map',plain);self.assertIn('repo_map',mapped)
        self.assertEqual(plain['inputs'],mapped['inputs'])


class GitEnvironmentIsolation(unittest.TestCase):
    """Two real repositories, an exported foreign Git environment, and the roots they may bind.

    A commit hook exports GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE and the configuration block for
    the repository being committed. Project discovery must follow the selected root instead, and
    must never read or write the repository that exported those variables.
    """

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve()
        self.exporting=self.base/'exporting';self.selected=self.base/'selected'
        for root,name in ((self.exporting,'exporting.py'),(self.selected,'selected.py')):
            root.mkdir();git(root,'init','-q')
            (root/name).write_text('def '+name[:-3]+'():\n    return 1\n')
            git(root,'add','-A');git(root,'commit','-qm','first')
        git(self.exporting,'branch','exported')
        git(self.exporting,'checkout','-q','exported')
        git(self.selected,'branch','selected-branch')
        git(self.selected,'checkout','-q','selected-branch')
        self.exported_metadata=self.metadata(self.exporting)
        self.exported_refs=self.refs(self.exporting)
        self.exporting_head=m.git_optional(self.exporting,['rev-parse','HEAD'])
        self.selected_head=m.git_optional(self.selected,['rev-parse','HEAD'])

    def metadata(self,root):
        """The repository bytes a leaking child would rewrite: HEAD, index and configuration."""
        folder=Path(root)/'.git'
        return {name:(folder/name).read_bytes() for name in ('HEAD','index','config')}

    def refs(self,root):
        found=subprocess.run(['git','for-each-ref','--format=%(refname) %(objectname)'],cwd=root,
                             capture_output=True,text=True,check=True,env=m.git_environment())
        return found.stdout

    def foreign_environment(self):
        """Every documented repository, index and configuration override, exported by another repository."""
        folder=self.exporting/'.git'
        return {'GIT_DIR':str(folder),'GIT_WORK_TREE':str(self.exporting),
                'GIT_INDEX_FILE':str(folder/'index'),'GIT_COMMON_DIR':str(folder),
                'GIT_OBJECT_DIRECTORY':str(folder/'objects'),
                'GIT_ALTERNATE_OBJECT_DIRECTORIES':str(folder/'objects'),
                'GIT_CEILING_DIRECTORIES':str(self.base),'GIT_CONFIG':str(folder/'config'),
                'GIT_CONFIG_PARAMETERS':"'core.bare=true'",'GIT_CONFIG_COUNT':'1',
                'GIT_CONFIG_KEY_0':'core.worktree','GIT_CONFIG_VALUE_0':str(self.exporting),
                'GIT_NAMESPACE':'exported','GIT_SHALLOW_FILE':str(folder/'shallow'),
                'GIT_AUTHOR_NAME':'Exported Author','GIT_AUTHOR_EMAIL':'author@example.invalid',
                'GIT_COMMITTER_NAME':'Exported Committer','GIT_COMMITTER_EMAIL':'committer@example.invalid'}

    def test_cleared_environment_keeps_identities_and_drops_repository_overrides(self):
        with patch.dict(os.environ,self.foreign_environment()):
            cleared=m.git_environment()
        self.assertEqual(cleared['GIT_AUTHOR_EMAIL'],'author@example.invalid')
        self.assertEqual(cleared['GIT_COMMITTER_NAME'],'Exported Committer')
        for dropped in ('GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE','GIT_COMMON_DIR','GIT_OBJECT_DIRECTORY',
                        'GIT_ALTERNATE_OBJECT_DIRECTORIES','GIT_CEILING_DIRECTORIES','GIT_CONFIG',
                        'GIT_CONFIG_PARAMETERS','GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0','GIT_CONFIG_VALUE_0',
                        'GIT_NAMESPACE','GIT_SHALLOW_FILE'):
            self.assertNotIn(dropped,cleared)
        for kept in ('PATH','HOME','LANG','TZ'):
            if kept in os.environ:self.assertEqual(cleared[kept],os.environ[kept])
        self.assertEqual(m.git_environment({'PATH':'/bin','GIT_DIR':'/elsewhere'}),{'PATH':'/bin'})

    def test_selected_repository_is_mapped_under_an_exported_foreign_environment(self):
        with patch.dict(os.environ,self.foreign_environment()):
            value,stats=m.build(self.selected)
        self.assertEqual(set(value['files']),{'selected.py'})
        self.assertEqual(value['project_root'],str(self.selected))
        self.assertEqual(value['git'],{'branch':'selected-branch','head':self.selected_head})
        self.assertEqual(stats['branch'],'selected-branch')
        self.assertEqual(stats['head'],self.selected_head)
        self.assertNotEqual(self.selected_head,self.exporting_head)
        self.assertEqual(self.metadata(self.exporting),self.exported_metadata)
        self.assertEqual(self.refs(self.exporting),self.exported_refs)
        self.assertFalse((self.exporting/'.crewloom').exists())

    def test_exporting_repository_is_mapped_when_another_one_exported_the_environment(self):
        # The same refusal in the opposite direction: neither repository may borrow the other.
        protected=self.metadata(self.selected);refs=self.refs(self.selected)
        with patch.dict(os.environ,{'GIT_DIR':str(self.selected/'.git'),
                                    'GIT_WORK_TREE':str(self.selected),
                                    'GIT_INDEX_FILE':str(self.selected/'.git/index')}):
            value,stats=m.build(self.exporting)
        self.assertEqual(set(value['files']),{'exporting.py'})
        self.assertEqual(value['project_root'],str(self.exporting))
        self.assertEqual(stats['head'],self.exporting_head)
        self.assertEqual(stats['branch'],'exported')
        self.assertEqual(self.metadata(self.selected),protected)
        self.assertEqual(self.refs(self.selected),refs)

    def test_plain_directory_is_refused_and_never_initialized_under_a_foreign_environment(self):
        plain=self.base/'plain';plain.mkdir()
        (plain/'plain.py').write_text('x = 1\n')
        with patch.dict(os.environ,self.foreign_environment()):
            with self.assertRaisesRegex(ValueError,'Git project'):m.build(plain)
        self.assertFalse((plain/'.git').exists())
        self.assertFalse((plain/'.crewloom').exists())

    def test_nested_directory_cannot_claim_the_repository_work_tree(self):
        nested=self.selected/'pkg';nested.mkdir()
        (nested/'core.py').write_text('def core():\n    return 1\n')
        with patch.dict(os.environ,self.foreign_environment()):
            with self.assertRaisesRegex(ValueError,'Git project'):m.build(nested)
        self.assertFalse((nested/'.crewloom').exists())

    def test_bare_repository_has_no_project_work_tree(self):
        bare=self.base/'bare.git'
        subprocess.run(['git','init','-q','--bare','bare.git'],cwd=self.base,check=True,
                       capture_output=True,env=m.git_environment())
        # A bare repository is its own Git directory: it has no work tree for a project root.
        protected={name:(bare/name).read_bytes() for name in ('HEAD','config')}
        with patch.dict(os.environ,self.foreign_environment()):
            with self.assertRaisesRegex(ValueError,'Git project'):m.build(bare)
        self.assertEqual({name:(bare/name).read_bytes() for name in ('HEAD','config')},protected)
        self.assertFalse((bare/'.crewloom').exists())

    def test_linked_worktree_is_its_own_project_root(self):
        linked=self.base/'linked'
        git(self.exporting,'worktree','add','-q',str(linked),'-b','linked-branch')
        (linked/'linked.py').write_text('def linked():\n    return 1\n')
        protected=self.metadata(self.exporting);refs=self.refs(self.exporting)
        with patch.dict(os.environ,self.foreign_environment()):
            value,stats=m.build(linked)
            bound=m.require_git_root(linked)
        self.assertEqual(set(value['files']),{'exporting.py','linked.py'})
        self.assertEqual(value['project_root'],str(linked))
        self.assertEqual(stats['branch'],'linked-branch')
        # A linked worktree is its own project root with its own Git directory, not the
        # main checkout that owns the branch it started from.
        self.assertEqual(bound['work_tree'],str(linked))
        self.assertNotEqual(bound['git_dir'],m.require_git_root(self.exporting)['git_dir'])
        self.assertEqual(self.metadata(self.exporting),protected)
        self.assertEqual(self.refs(self.exporting),refs)

    def test_every_test_fixture_starts_git_with_an_explicit_environment(self):
        """No fixture may inherit the repository that happens to be running this suite.

        These regressions execute inside a commit hook, where Git exports GIT_DIR, GIT_WORK_TREE
        and GIT_INDEX_FILE for the repository being committed. A fixture that starts Git without
        its own environment commits, branches and checks out inside that repository instead of
        its temporary project, so every such call is checked at source level here.
        """
        starters=('run','Popen','check_call','check_output','call')
        offenders=[]
        for path in sorted(Path(m.__file__).parent.glob('test_*.py')):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if not isinstance(node,ast.Call):continue
                name=getattr(node.func,'attr',getattr(node.func,'id',''))
                if name not in starters:continue
                if not any(isinstance(item,ast.Constant) and item.value=='git' for item in ast.walk(node)):
                    continue
                if not any(keyword.arg=='env' for keyword in node.keywords):
                    offenders.append(path.name+':'+str(node.lineno))
        self.assertEqual(offenders,[],'every fixture Git child needs repo_map.git_environment()')


if __name__=='__main__':unittest.main()
