"""Adversarial artifact scope tests, including actual filesystem permissions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import execution_policy as policy
import workflow as w


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'input.txt').write_text('original')
        self.step={'argv':['python3','-c','pass'],'inputs':['input.txt'],'outputs':['output.txt']}

    def test_only_declared_inputs_visible_and_output_published(self):
        (self.root/'secret.txt').write_text('private')
        def execute(stage,*args,**kwargs):
            self.assertFalse((stage/'secret.txt').exists());self.assertEqual(kwargs['writable'],['output.txt'])
            (stage/'output.txt').write_text('verified');return {'exit_code':0}
        with patch.object(w,'docker_execute',side_effect=execute):policy.execute(self.root,self.step,'image',10)
        self.assertEqual((self.root/'output.txt').read_text(),'verified')
        self.assertEqual((self.root/'input.txt').read_text(),'original')

    def test_failed_command_cannot_change_project(self):
        def execute(stage,*args,**kwargs):
            (stage/'input.txt').write_text('tampered');(stage/'output.txt').write_text('unsafe');return {'exit_code':1}
        with patch.object(w,'docker_execute',side_effect=execute):policy.execute(self.root,self.step,'image',10)
        self.assertFalse((self.root/'output.txt').exists());self.assertEqual((self.root/'input.txt').read_text(),'original')

    def test_symlink_and_hardlink_destinations_rejected(self):
        for kind in ('symlink','hardlink'):
            path=self.root/'output.txt'
            if kind=='symlink':path.symlink_to(self.root/'input.txt')
            else:os.link(self.root/'input.txt',path)
            with self.subTest(kind=kind),self.assertRaises(ValueError):policy.destinations(self.root,['output.txt'])
            path.unlink()

    def test_input_changed_during_execution_rejects_all_outputs(self):
        def execute(stage,*args,**kwargs):
            (self.root/'input.txt').write_text('changed');(stage/'output.txt').write_text('artifact');return {'exit_code':0}
        with patch.object(w,'docker_execute',side_effect=execute),self.assertRaisesRegex(ValueError,'Inputs changed'):
            policy.execute(self.root,self.step,'image',10)
        self.assertFalse((self.root/'output.txt').exists())

    def test_output_budget_and_empty_outputs_rejected(self):
        for data in (b'',b'x'*(policy.MAX_OUTPUT_BYTES+1)):
            with self.assertRaises(ValueError):policy.publish(self.root,{'output.txt':data},w.hashes(self.root,['input.txt']))
        self.assertFalse((self.root/'output.txt').exists())


class GroupedPublicationTests(unittest.TestCase):
    """Own checks for the recoverable group contract the six supervisor cases depend on."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();(self.root/'input.txt').write_text('original')
        self.expected=w.hashes(self.root,['input.txt'])
        self.originals={}

    def pending(self):
        folder=self.root/'.crewloom'/'transactions'/'pending'
        return sorted(item.name for item in folder.iterdir()) if folder.is_dir() else []

    def journal(self, entries, state='prepared', ident='0000000000001-test'):
        """Hand-build one prepared transaction, the way a killed writer would leave it."""
        folder=policy._internal(self.root,'pending',ident)
        (folder/policy.BACKUP).mkdir(parents=True);(folder/policy.PAYLOAD).mkdir()
        for entry in entries:
            if isinstance(entry,dict) and entry.get('existed') and entry.get('index') in self.originals:
                (folder/policy.BACKUP/(str(entry['index'])+'.bin')).write_bytes(self.originals[entry['index']])
        value={'schema_version':policy.JOURNAL_VERSION,'transaction':ident,'project_root':str(self.root),
               'created_at':'2026-01-01T00:00:00Z','state':state,'inputs':dict(self.expected),
               'created_parents':[],'entries':entries}
        policy._write_record(folder/'journal.json',value)
        return folder

    def entry(self, index, relative, existed, original, new, mode=0o644, state='replaced'):
        self.originals[index]=original
        return {'index':index,'path':relative,'state':state,'existed':existed,'mode':mode,
                'bytes':len(new),policy.ORIGINAL_BYTES:len(original) if existed else 0,
                'original_sha256':w.digest(original) if existed else None,
                'new_sha256':w.digest(new)}

    def test_a_successful_three_file_group_preserves_modes_and_leaves_one_receipt(self):
        (self.root/'first.txt').write_bytes(b'old first\n');(self.root/'first.txt').chmod(0o640)
        (self.root/'second.txt').write_bytes(b'old second\n')
        receipt=policy.publish(self.root,{'first.txt':b'new first\n','second.txt':b'new second\n',
                                         'third.txt':b'new third\n'},self.expected)
        self.assertEqual((self.root/'first.txt').read_bytes(),b'new first\n')
        self.assertEqual((self.root/'second.txt').read_bytes(),b'new second\n')
        self.assertEqual((self.root/'third.txt').read_bytes(),b'new third\n')
        if os.name=='posix':
            self.assertEqual((self.root/'first.txt').stat().st_mode&0o777,0o640)
            self.assertEqual((self.root/'third.txt').stat().st_mode&0o777,0o644)
        self.assertEqual(sorted(receipt['outputs']),['first.txt','second.txt','third.txt'])
        self.assertEqual(receipt['outputs']['first.txt'],w.digest(b'new first\n'))
        receipts=sorted((self.root/'.crewloom'/'transactions'/'receipts').iterdir())
        self.assertEqual(len(receipts),1,receipts)
        self.assertEqual(self.pending(),[])

    def test_the_root_lock_is_held_for_every_destination_of_the_group(self):
        (self.root/'lock').write_text('unrelated')
        lock=self.root/'.crewloom'/'lock'
        original=os.replace;seen=[]
        def replace(source,target,*args,**kwargs):
            result=original(source,target,*args,**kwargs)
            if Path(target).name.endswith('.txt'):
                seen.append((Path(target).name,lock.is_file()))
            return result
        with patch.object(os,'replace',side_effect=replace):
            policy.publish(self.root,{'one.txt':b'1\n','two.txt':b'2\n'},self.expected)
        self.assertEqual(sorted(seen),[('one.txt',True),('two.txt',True)])
        self.assertEqual((self.root/'lock').read_text(),'unrelated')

    def test_a_rolled_back_group_leaves_foreign_neighbours_and_its_journal_removed(self):
        (self.root/'neighbour.txt').write_text('someone else')
        (self.root/'sub').mkdir();(self.root/'sub'/'keep.bin').write_text('keep')
        def failing(source,target,*args,**kwargs):
            if Path(target).name=='two.txt':raise OSError('injected')
            return original(source,target,*args,**kwargs)
        original=os.replace
        with patch.object(os,'replace',side_effect=failing),self.assertRaises(OSError):
            policy.publish(self.root,{'one.txt':b'1\n','two.txt':b'2\n'},self.expected)
        self.assertFalse((self.root/'one.txt').exists())
        self.assertFalse((self.root/'two.txt').exists())
        self.assertEqual((self.root/'neighbour.txt').read_text(),'someone else')
        self.assertEqual((self.root/'sub'/'keep.bin').read_text(),'keep')
        self.assertEqual(self.pending(),[])
        self.assertEqual([item.name for item in (self.root/'sub').iterdir()],['keep.bin'])

    def test_group_budgets_refuse_the_whole_group_before_any_destination_write(self):
        many={('out%03d.txt'%index):b'x' for index in range(policy.MAX_ARTIFACTS+1)}
        with self.assertRaisesRegex(ValueError,'Too many'):policy.publish(self.root,many,self.expected)
        big={'big.txt':b'x'*(policy.MAX_OUTPUT_BYTES+1)}
        with self.assertRaisesRegex(ValueError,'budget'):policy.publish(self.root,big,self.expected)
        (self.root/'wide.txt').write_bytes(b'y'*4096)
        with patch.object(policy,'MAX_BACKUP_BYTES',1024):
            with self.assertRaisesRegex(ValueError,'backup budget'):
                policy.publish(self.root,{'wide.txt':b'z'},self.expected)
        self.assertEqual((self.root/'wide.txt').read_bytes(),b'y'*4096)
        self.assertEqual(sorted(item.name for item in self.root.iterdir()),
                         ['.crewloom','input.txt','wide.txt'])

    def test_control_paths_trusted_roots_and_duplicate_destinations_are_refused(self):
        (self.root/'vendor').mkdir();(self.root/'vendor'/'module.py').write_text('runtime')
        with tempfile.TemporaryDirectory() as directory:
            outside=Path(directory).resolve();(outside/'keep.txt').write_text('keep')
            with patch.object(policy,'trusted_roots',return_value={(self.root/'vendor').resolve()}):
                with self.assertRaisesRegex(ValueError,'read-only'):
                    policy.publish(self.root,{'vendor/module.py':b'hijacked'},self.expected)
            self.assertEqual((self.root/'vendor'/'module.py').read_text(),'runtime')
            for relative,label in (('.crewloom/receipts.json','runtime'),('.git/config','runtime'),
                                   ('crewloom.project.json','control'),
                                   ('../'+outside.name+'/keep.txt','escape')):
                with self.subTest(label=label),self.assertRaises(ValueError):
                    policy.publish(self.root,{relative:b'x'},self.expected)
            self.assertEqual((outside/'keep.txt').read_text(),'keep')
        with self.assertRaisesRegex(ValueError,'aliases are forbidden'):
            policy.publish(self.root,{'same.txt':b'x','./same.txt':b'y'},self.expected)
        self.assertFalse((self.root/'same.txt').exists())
        import crewloom_resources as resources
        runtime=resources.module_file('execution_policy.py')
        self.assertIn(Path(w.LIBRARY).resolve(),policy.trusted_roots())
        self.assertIn(runtime.resolve().parent,policy.trusted_roots())
        self.assertTrue(runtime.is_file())

    @unittest.skipUnless(os.name=='posix','POSIX ownership boundary')
    def test_an_unwritable_destination_parent_rolls_the_whole_group_back(self):
        locked=self.root/'locked';locked.mkdir()
        (self.root/'first.txt').write_bytes(b'original first\n')
        original=os.replace
        def failing(source,target,*args,**kwargs):
            if Path(target).parent==locked:raise PermissionError('injected unwritable parent')
            return original(source,target,*args,**kwargs)
        locked.chmod(0o500)
        self.addCleanup(locked.chmod,0o700)
        with patch.object(os,'replace',side_effect=failing),self.assertRaises(PermissionError):
            policy.publish(self.root,{'first.txt':b'new first\n','locked/second.txt':b'new second\n'},
                           self.expected)
        self.assertEqual((self.root/'first.txt').read_bytes(),b'original first\n')
        self.assertFalse((locked/'second.txt').exists())
        self.assertEqual(self.pending(),[])

    def test_recovery_validates_every_record_before_it_writes_anything(self):
        (self.root/'first.txt').write_bytes(b'original first\n')
        (self.root/'second.txt').write_bytes(b'original second\n')
        entries=[self.entry(0,'first.txt',True,b'original first\n',b'new first\n',0o640),
                 self.entry(1,'second.txt',True,b'original second\n',b'new second\n')]
        folder=self.journal(entries)
        (self.root/'first.txt').write_bytes(b'new first\n')
        (self.root/'second.txt').write_bytes(b'an independent user edit\n')
        with self.assertRaisesRegex(ValueError,'Ambiguous interrupted publication'):
            policy.recover(self.root)
        # The restorable destination was left applied, because nothing is rolled back until the
        # whole journal is proven restorable; the foreign edit is never overwritten.
        self.assertEqual((self.root/'first.txt').read_bytes(),b'new first\n')
        self.assertEqual((self.root/'second.txt').read_bytes(),b'an independent user edit\n')
        self.assertEqual(self.pending(),[folder.name])

    def test_recovery_refuses_unrecognised_staged_content_without_deleting_it(self):
        entries=[self.entry(0,'first.txt',False,None,b'new first\n',state='pending')]
        folder=self.journal(entries)
        stranger=folder/'somebody-elses.txt';stranger.write_text('not ours')
        with self.assertRaisesRegex(ValueError,'Unrecognised content'):
            policy.recover(self.root)
        self.assertEqual(stranger.read_text(),'not ours')
        self.assertEqual(self.pending(),[folder.name])

    @unittest.skipUnless(os.name=='posix','POSIX symlink boundary')
    def test_a_writer_killed_before_its_journal_leaves_a_reconcilable_root(self):
        (self.root/'first.txt').write_bytes(b'original first\n')
        # A real child process is terminated inside the first journal write of a real group, so
        # the residue it leaves behind is exactly what a crash leaves, not a hand-built one.
        code = '''import json, os, sys
sys.path.insert(0, sys.argv[2])
import execution_policy as broker, workflow
root = __import__("pathlib").Path(sys.argv[1]).resolve()

def write_record(path, value):
    # The staging file is written and fsync-shaped exactly as the real one is, then the
    # process dies before the rename, so journal.json never appears.
    temporary = broker._staging(path)
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os._exit(92)

broker._write_record = write_record
broker.publish(root, {"first.txt": b"new first\\n"}, workflow.hashes(root, ["input.txt"]))
'''
        import repo_map
        result = subprocess.run([sys.executable, '-c', code, str(self.root),
                                 str(Path(__file__).resolve().parent)],
                                cwd=self.root, env=repo_map.git_environment(),
                                capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 92, result.stderr.decode(errors='replace'))
        self.assertEqual((self.root/'first.txt').read_bytes(), b'original first\n')
        # The residue is a transaction that provably never wrote a destination.
        pending = policy._internal(self.root, 'pending')
        residue = sorted(item.name for item in pending.iterdir())
        self.assertEqual(len(residue), 1)
        self.assertEqual(sorted(item.name for item in (pending/residue[0]).iterdir()),
                         ['.journal.json' + policy.TEMPORARY, policy.BACKUP, policy.PAYLOAD])
        receipt = policy.publish(self.root, {'second.txt': b'next group\n'}, self.expected)
        self.assertEqual(sorted(receipt['outputs']), ['second.txt'])
        self.assertEqual((self.root/'second.txt').read_bytes(), b'next group\n')
        self.assertEqual((self.root/'first.txt').read_bytes(), b'original first\n')
        self.assertEqual(self.pending(), [])

    def test_a_transaction_releases_only_its_own_journal_staging_file(self):
        self.journal([self.entry(0,'first.txt',False,None,b'new first\n',state='pending')])
        staging=policy._internal(self.root,'pending','0000000000001-test')/('.journal.json'+policy.TEMPORARY)
        staging.write_text('{"half":')
        # A recognised staging file left beside a valid journal is released with it.
        self.assertEqual(policy.recover(self.root),
                         [{'transaction': '0000000000001-test', 'restored': []}])
        self.assertFalse(staging.parent.exists())
        self.assertEqual(sorted(item.name for item in self.root.iterdir()),['.crewloom','input.txt'])

    def test_an_anonymous_temporary_left_by_an_older_build_is_reported_not_deleted(self):
        stranger=self.journal([self.entry(0,'first.txt',False,None,b'x',state='pending')],
                              ident='0000000000002-test')
        (stranger/'tmp8zk3q').write_text('not recognisable as ours')
        with self.assertRaisesRegex(ValueError,'Unrecognised content'):
            policy.recover(self.root)
        self.assertTrue((stranger/'tmp8zk3q').is_file())
        self.assertEqual(self.pending(),['0000000000002-test'])

    def test_receipt_storage_is_bounded_including_unrenamed_staging_files(self):
        receipts=policy._internal(self.root,'receipts');receipts.mkdir(parents=True)
        for index in range(policy.MAX_RECEIPTS+5):
            (receipts/('%013d-x.json'%(index+1))).write_text('{}')
        leftover=receipts/('0000000000000-leftover.json'+policy.TEMPORARY)
        leftover.write_text('{"half":')
        policy._prune(receipts)
        remaining=sorted(item.name for item in receipts.iterdir())
        self.assertEqual(len(remaining),policy.MAX_RECEIPTS)
        self.assertNotIn(leftover.name,remaining)
        self.assertEqual(remaining[-1],'%013d-x.json'%(policy.MAX_RECEIPTS+5))

    def test_recovery_never_follows_a_symlinked_transaction_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign=Path(directory).resolve();(foreign/'keep.txt').write_text('keep')
            (foreign/policy.BACKUP).mkdir();(foreign/policy.PAYLOAD).mkdir()
            pending=policy._internal(self.root,'pending');pending.mkdir(parents=True)
            (pending/'0000000000001-test').symlink_to(foreign,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'may not be a symlink'):
                policy.recover(self.root)
            self.assertEqual((foreign/'keep.txt').read_text(),'keep')
            self.assertTrue((pending/'0000000000001-test').is_symlink())

    def test_a_committed_journal_is_released_without_touching_destinations(self):
        (self.root/'first.txt').write_bytes(b'published\n')
        entries=[self.entry(0,'first.txt',False,None,b'published\n')]
        folder=self.journal(entries,state=policy.COMMITTED)
        self.assertEqual(policy.recover(self.root),[])
        self.assertEqual((self.root/'first.txt').read_bytes(),b'published\n')
        self.assertEqual(self.pending(),[])
        self.assertFalse(folder.exists())

    def test_a_journal_from_another_project_is_refused(self):
        entries=[self.entry(0,'first.txt',False,None,b'x',state='pending')]
        folder=self.journal(entries)
        record=json.loads((folder/'journal.json').read_text());record['project_root']='/elsewhere'
        (folder/'journal.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'another project'):
            policy.recover(self.root)
        self.assertEqual(self.pending(),[folder.name])

    def test_malformed_journal_records_are_refused_before_any_restore(self):
        (self.root/'first.txt').write_bytes(b'new first\n')
        for entries in ([{'index':0,'path':'first.txt'}], [{'index':0,'path':'first.txt','state':'replacing',
                        'existed':True,'mode':None,'bytes':1,'original_sha256':None,'new_sha256':None}],
                        'not-a-list'):
            with self.subTest(entries=str(entries)[:40]):
                for item in self.pending():policy._discard(policy._internal(self.root,'pending',item))
                self.journal(entries)
                with self.assertRaisesRegex(ValueError,'Ambiguous|usable'):
                    policy.recover(self.root)
                self.assertEqual((self.root/'first.txt').read_bytes(),b'new first\n')

    def applied_group(self, count=2):
        """Leave a group that is mid-publication: every destination holds the new bytes."""
        entries=[]
        for index in range(count):
            relative='output%d.txt'%index
            original=('original %d\n'%index).encode()
            (self.root/relative).write_bytes(b'new %d\n'%index)
            entries.append(self.entry(index,relative,True,original,b'new %d\n'%index))
        return self.journal(entries)

    def test_a_corrupt_backup_refuses_the_whole_group_before_any_destination_is_restored(self):
        folder=self.applied_group()
        # The same length as the original it replaces, so only the recorded digest can catch it.
        (folder/policy.BACKUP/'1.bin').write_bytes(b'corrupted bytes'[:len(b'original 1\n')])
        with self.assertRaisesRegex(ValueError,'staged backup no longer matches'):
            policy.recover(self.root)
        # The first destination is still restorable and is deliberately left applied: nothing is
        # undone until every backup in the group is proved, so the group never ends half reverted.
        self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')
        self.assertEqual((self.root/'output1.txt').read_bytes(),b'new 1\n')
        self.assertTrue((folder/'journal.json').is_file())

    def test_a_truncated_backup_is_refused_by_the_recorded_original_size(self):
        folder=self.applied_group(1)
        item=folder/policy.BACKUP/'0.bin'
        item.write_bytes(b'original 0\n'[:5])
        with self.assertRaisesRegex(ValueError,'size no longer matches'):
            policy.recover(self.root)
        self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')
        self.assertTrue(item.is_file())

    def test_a_missing_hardlinked_or_symlinked_backup_is_refused(self):
        for damage,expected in ((lambda item:item.unlink(),'staged backup for this destination is missing'),
                                (lambda item:os.link(item,self.root/'foreign.bin'),'has hardlinks'),
                                (lambda item:item.unlink() or item.symlink_to(self.root/'output0.txt'),
                                 'staged backup for this destination is missing')):
            with self.subTest(damage=getattr(damage,'__name__','unknown')):
                for item in self.pending():policy._discard(policy._internal(self.root,'pending',item))
                if (self.root/'foreign.bin').exists():(self.root/'foreign.bin').unlink()
                folder=self.applied_group(1);damage(folder/policy.BACKUP/'0.bin')
                with self.assertRaisesRegex(ValueError,expected):
                    policy.recover(self.root)
                self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')
                self.assertEqual(self.pending(),[folder.name])

    def test_a_journal_whose_own_identity_disagrees_with_its_folder_is_refused(self):
        folder=self.applied_group(1)
        record=json.loads((folder/'journal.json').read_text())
        record['transaction']='0000000000009-somewhere-else'
        (folder/'journal.json').write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'identity does not match'):
            policy.recover(self.root)
        self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')

    def test_an_unknown_schema_or_state_is_refused_before_any_restore(self):
        for key,value in (('schema_version',99),('state','half-done')):
            with self.subTest(key=key):
                for item in self.pending():policy._discard(policy._internal(self.root,'pending',item))
                folder=self.applied_group(1)
                record=json.loads((folder/'journal.json').read_text());record[key]=value
                (folder/'journal.json').write_text(json.dumps(record))
                with self.assertRaisesRegex(ValueError,'schema version|journal state'):
                    policy.recover(self.root)
                self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')

    def test_two_records_sharing_one_backup_index_or_path_are_refused(self):
        (self.root/'first.txt').write_bytes(b'new first\n')
        (self.root/'second.txt').write_bytes(b'new second\n')
        for label,entries in (('index',[self.entry(0,'first.txt',True,b'original first\n',b'new first\n'),
                                        self.entry(0,'second.txt',True,b'original second\n',b'new second\n')]),
                              ('path',[self.entry(0,'first.txt',True,b'original first\n',b'new first\n'),
                                       self.entry(1,'first.txt',True,b'original first\n',b'new first\n')])):
            with self.subTest(label=label):
                for item in self.pending():policy._discard(policy._internal(self.root,'pending',item))
                folder=self.journal(entries)
                with self.assertRaisesRegex(ValueError,'share one staged backup index|same path'):
                    policy.recover(self.root)
                self.assertEqual((self.root/'first.txt').read_bytes(),b'new first\n')
                self.assertTrue((folder/'journal.json').is_file())

    def test_a_record_naming_a_runtime_control_or_trusted_path_is_refused(self):
        (self.root/'vendor').mkdir();(self.root/'vendor'/'module.py').write_bytes(b'runtime\n')
        for relative in ('.crewloom/receipts.json','crewloom.project.json','../escape.txt','vendor/module.py'):
            with self.subTest(relative=relative):
                for item in self.pending():policy._discard(policy._internal(self.root,'pending',item))
                folder=self.journal([self.entry(0,relative,True,b'runtime\n',b'new content\n')])
                with patch.object(policy,'trusted_roots',return_value={(self.root/'vendor').resolve()}):
                    with self.assertRaises(ValueError):
                        policy.recover(self.root)
                self.assertEqual((self.root/'vendor'/'module.py').read_bytes(),b'runtime\n')
                self.assertTrue((folder/'journal.json').is_file())

    def test_a_valid_two_file_group_is_still_restored_byte_for_byte(self):
        folder=self.applied_group()
        restored=policy.recover(self.root)
        self.assertEqual(sorted(restored[0]['restored']),['output0.txt','output1.txt'])
        self.assertEqual((self.root/'output0.txt').read_bytes(),b'original 0\n')
        self.assertEqual((self.root/'output1.txt').read_bytes(),b'original 1\n')
        self.assertFalse(folder.exists())

    def fresh_journal(self,count=1):
        """A hand-built mid-publication group in a root with no residue from an earlier case.

        A refused case deliberately leaves its folder behind, so each one starts from runtime
        state that was created fresh rather than cleaned up through the broker that refused it.
        """
        for stale in list(self.root.iterdir()):
            if stale.name=='input.txt':continue
            if stale.is_dir() and not stale.is_symlink():shutil.rmtree(stale)
            else:stale.unlink()
        return self.applied_group(count)

    def staged_listing(self,folder):
        """Every staged file one transaction holds, by stage and name."""
        return {stage:sorted(item.name for item in (folder/stage).iterdir())
                for stage in (policy.BACKUP,policy.PAYLOAD)}

    def test_an_unrecognised_nested_staged_file_is_reported_and_never_deleted(self):
        # Ownership is the per-index staging names the folder's own record names, so an operator's
        # own notes inside a stage are somebody else's file: nothing at all may be removed on this
        # transaction's behalf, not even the recognised entries beside them.
        for stage,name,body in (('payload','manual-investigation.txt','independent notes\n'),
                                 (policy.BACKUP,'original-notes.txt','independent notes\n'),
                                 ('payload',policy._staged_name(3),'named for no recorded destination\n')):
            with self.subTest(stage=stage,name=name):
                folder=self.fresh_journal()
                stranger=folder/stage/name;stranger.write_text(body)
                before=self.staged_listing(folder)
                with self.assertRaisesRegex(ValueError,'Unrecognised content in publication stage'):
                    policy.recover(self.root)
                self.assertEqual(stranger.read_text(),body)
                self.assertEqual(self.staged_listing(folder),before)
                self.assertTrue((folder/'journal.json').is_file())
                # The rollback itself stays complete: it was proved before it was written, so the
                # destinations hold their recorded originals and only the residue needs an operator.
                self.assertEqual((self.root/'output0.txt').read_bytes(),b'original 0\n')
                self.assertEqual(self.pending(),[folder.name])

    def test_a_nested_symlinked_or_nested_folder_entry_is_reported_not_deleted(self):
        for label,build in (('symlink',lambda folder:(folder/policy.PAYLOAD/'0.bin').symlink_to(
                                 self.root/'output0.txt')),
                            ('directory',lambda folder:(folder/policy.PAYLOAD/'0.bin').mkdir())):
            with self.subTest(label=label):
                folder=self.fresh_journal()
                build(folder);before=self.staged_listing(folder)
                with self.assertRaisesRegex(ValueError,'Unexpected entry in publication stage'):
                    policy.recover(self.root)
                self.assertTrue((folder/'journal.json').is_file())
                self.assertTrue((folder/policy.PAYLOAD).is_dir())
                self.assertEqual((self.root/'output0.txt').read_bytes(),b'original 0\n')
                self.assertEqual(self.staged_listing(folder),before)

    @unittest.skipUnless(os.name=='posix','POSIX ownership boundary')
    def test_a_destination_that_became_a_link_or_a_directory_is_refused_before_any_restore(self):
        # The journal records content and a digest, never ownership of a name, so the same broker
        # destination check a publication is held to is re-run before a rollback writes anything.
        # Both names must keep their bytes and the journal must stay, whichever one is refused.
        for label,damage in (('hardlink',lambda target,root:os.link(target,root/'foreign.txt')),
                             ('directory',lambda target,root:(target.unlink(),target.mkdir()))):
            with self.subTest(label=label):
                folder=self.fresh_journal(2)
                damage(self.root/'output0.txt',self.root)
                with self.assertRaisesRegex(ValueError,'Ambiguous interrupted publication'):
                    policy.recover(self.root)
                # The destination that was still unambiguous is deliberately left applied: a
                # refusal found during the preflight is not a half-done rollback.
                self.assertEqual((self.root/'output1.txt').read_bytes(),b'new 1\n')
                self.assertTrue((folder/'journal.json').is_file())
                self.assertEqual((folder/policy.BACKUP/'0.bin').read_bytes(),b'original 0\n')
                if label=='hardlink':
                    self.assertEqual((self.root/'foreign.txt').read_bytes(),b'new 0\n')
                    self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')

    def test_an_oversized_journal_is_refused_before_it_is_read_or_parsed(self):
        folder=self.applied_group(1)
        journal=folder/'journal.json'
        with patch.object(policy,'MAX_JOURNAL_BYTES',64),self.assertRaises(ValueError) as refusal:
            policy.recover(self.root)
        # The refusal names the bound it was held to, so it is actionable rather than a parse error.
        self.assertIn('record budget',str(refusal.exception))
        self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')
        self.assertTrue(journal.is_file())
        self.assertEqual(self.staged_listing(folder),
                         {policy.BACKUP:['0.bin'],policy.PAYLOAD:[]})

    def test_a_journal_this_protocol_writes_stays_inside_the_record_budget(self):
        # The cap only refuses a file this protocol could not have written: the widest group it can
        # publish still produces a journal far inside it.
        folder=self.applied_group(policy.MAX_ARTIFACTS)
        self.assertLess((folder/'journal.json').stat().st_size,policy.MAX_JOURNAL_BYTES)
        self.assertLessEqual(policy.MAX_JOURNAL_BYTES,2*1024*1024)

    def case_insensitive_host(self):
        """Whether this host actually resolves two spellings of one name to one file.

        Nothing is probed to decide a rule; this only reports what the running host does, so the
        physical-identity cases are proven where they can be and reported as not applicable
        elsewhere instead of being assumed.
        """
        return (self.root/'INPUT.TXT').exists()

    def test_reserved_names_are_refused_in_every_spelling_on_every_platform(self):
        # Portable by construction: these are refused because of the spelling, not because of the
        # filesystem, so the same rule holds on a case-sensitive Linux container.
        for relative in ('.CREWLOOM/protected.json','.Crewloom/attempts.json','.GIT/config',
                         'src/.CrewLoom/x.txt','crewloom.project.json','CREWLOOM.PROJECT.JSON',
                         'sub/Crewloom.Project.Json'):
            with self.subTest(relative=relative),self.assertRaises(ValueError):
                w.declared_path(self.root,relative)
        # Ordinary artifact paths are untouched by the folding.
        for relative in ('report.txt','docs/Annual Report.md','src/.github/config.yml'):
            with self.subTest(relative=relative):
                self.assertTrue(str(w.declared_path(self.root,relative)).startswith(str(self.root)))

    def test_one_output_group_may_not_own_one_destination_in_two_spellings(self):
        # The whole group is refused before the first write, including two names that exist
        # nowhere yet, which is exactly the case a filesystem probe would be needed to detect and
        # the case a lexical comparison cannot see.
        for first,second in (('New.txt','new.txt'),('./New.txt','New.txt'),
                             ('sub/../Other.txt','other.txt'),('résumé.txt','re\u0301sume\u0301.txt')):
            with self.subTest(first=first,second=second):
                with self.assertRaises(ValueError):
                    policy.publish(self.root,{first:b'first\n',second:b'second\n'},self.expected)
                for relative in (first,second):
                    self.assertFalse((self.root/relative).exists())
        self.assertEqual(self.pending(),[])

    def test_an_ordinary_group_with_distinct_names_publishes_unchanged(self):
        # The portable rule refuses a collision, not capitalisation: a normal group of files whose
        # names differ in more than case still publishes, is journalled and leaves one receipt.
        receipt=policy.publish(self.root,{'report.txt':b'report\n','notes/summary.md':b'summary\n',
                                         'report.json':b'{}\n'},self.expected)
        self.assertEqual(sorted(receipt['outputs']),['notes/summary.md','report.json','report.txt'])
        self.assertEqual((self.root/'report.txt').read_bytes(),b'report\n')
        self.assertEqual((self.root/'notes'/'summary.md').read_bytes(),b'summary\n')
        self.assertEqual(sorted(item.name for item in
                                (self.root/'.crewloom'/'transactions'/'receipts').iterdir()),
                         [receipt['transaction']+'.json'])

    def test_one_existing_destination_may_be_replaced_through_either_spelling(self):
        # A single destination is one file whatever it is called, so it is replaced with the same
        # backup, rollback and receipt machinery rather than refused for being spelled differently.
        (self.root/'Result.txt').write_bytes(b'original output\n')
        target='result.txt' if self.case_insensitive_host() else 'Result.txt'
        receipt=policy.publish(self.root,{target:b'replacement\n'},self.expected)
        self.assertEqual(sorted(receipt['outputs']),[target])
        self.assertEqual((self.root/target).read_bytes(),b'replacement\n')
        self.assertEqual((self.root/'Result.txt').read_bytes(),b'replacement\n')
        self.assertEqual(self.pending(),[])

    def test_a_recovery_journal_may_not_undo_one_destination_twice_through_two_spellings(self):
        # The journal is the only input recovery trusts, so a record that names one destination in
        # two spellings would have the second undo restore the first already restored, byte for byte.
        folder=self.fresh_journal(1)
        journal=policy._record_value(folder/'journal.json','Publication journal')
        alias=dict(journal['entries'][0]);alias['index']=1
        alias['path']='OUTPUT0.TXT'
        alias['new_sha256']=w.digest(b'first candidate\n')
        journal['entries'].append(alias)
        policy._write_record(folder/'journal.json',journal)
        with self.assertRaisesRegex(ValueError,'two destination records name one path'):
            policy.recover(self.root)
        self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')
        self.assertTrue((folder/'journal.json').is_file())
        self.assertEqual(self.pending(),[folder.name])

    def test_a_reserved_name_alias_is_refused_inside_a_journalled_group(self):
        folder=self.fresh_journal(1)
        journal=policy._record_value(folder/'journal.json','Publication journal')
        alias=dict(journal['entries'][0]);alias['index']=1
        alias['path']='.CREWLOOM/attempts.json'
        journal['entries'].append(alias)
        policy._write_record(folder/'journal.json',journal)
        with self.assertRaisesRegex(ValueError,'runtime or Git state'):
            policy.recover(self.root)
        self.assertEqual((self.root/'output0.txt').read_bytes(),b'new 0\n')
        self.assertTrue((folder/'journal.json').is_file())

    def test_a_trusted_root_is_reached_through_physical_identity_not_its_spelling(self):
        # Refused only where the host actually resolves the two spellings to one directory,
        # because that is the only place there is a physical identity to prove; the spelling rules
        # above are portable and hold everywhere.
        if not self.case_insensitive_host():
            self.skipTest('Host resolves two spellings of one name to two files')
        vendor=self.root/'vendor';vendor.mkdir()
        runtime=vendor/'runtime.py';runtime.write_bytes(b'trusted runtime\n')
        # The same directory under another spelling is the one protected root.
        self.assertTrue(w.inside(self.root/'VENDOR',(vendor,)))
        self.assertTrue(w.inside(self.root/'VENDOR'/'nested'/'missing.py',(vendor,)))
        self.assertFalse(w.inside(self.root/'vendorless'/'missing.py',(vendor,)))
        with patch.object(policy,'trusted_roots',return_value={vendor}):
            with self.assertRaisesRegex(ValueError,'read-only'):
                policy.publish(self.root,{'VENDOR/runtime.py':b'replaced\n'},self.expected)
            with self.assertRaisesRegex(ValueError,'read-only'):
                policy.publish(self.root,{'vendor/Nested/new.py':b'new\n'},self.expected)
        self.assertEqual(runtime.read_bytes(),b'trusted runtime\n')
        self.assertFalse((vendor/'Nested').exists())


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS')=='1','Enable live Docker acceptance explicitly')
class ContainerPolicyTests(unittest.TestCase):
    def test_runtime_git_policy_and_other_inputs_are_inaccessible_or_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'secret.txt').write_text('private')
            script="""from pathlib import Path
import json
checks={'private_absent':not Path('secret.txt').exists(),'git_absent':not Path('.git').exists()}
for name,path in [('input_readonly','probe.py'),('runtime_readonly','.crewloom/tamper'),('undeclared_denied','extra.txt')]:
 try:Path(path).write_text('bad');checks[name]=False
 except OSError:checks[name]=True
Path('result.json').write_text(json.dumps(checks))
"""
            (root/'probe.py').write_text(script)
            image=w.inspect_image(w.DEFAULT_IMAGE)
            result=policy.execute(root,{'argv':['python3','probe.py'],'inputs':['probe.py'],'outputs':['result.json']},image,20)
            self.assertEqual(result['exit_code'],0,result.get('output'))
            self.assertTrue(all(json.loads((root/'result.json').read_text()).values()))
            self.assertEqual((root/'probe.py').read_text(),script);self.assertEqual((root/'secret.txt').read_text(),'private')

    def test_real_container_publishes_a_three_file_group_as_one_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'seed.txt').write_text('seed')
            (root/'first.txt').write_text('original first');(root/'first.txt').chmod(0o640)
            script="""from pathlib import Path
Path('report.json').write_text('{\\"one\\": 1}')
Path('nested').mkdir(exist_ok=True)
Path('nested/second.txt').write_text('two')
Path('third.txt').write_text('three')
"""
            (root/'probe.py').write_text(script)
            image=w.inspect_image(w.DEFAULT_IMAGE)
            result=policy.execute(root,{'argv':['python3','probe.py'],'inputs':['probe.py'],
                                        'outputs':['report.json','nested/second.txt','third.txt']},image,30)
            self.assertEqual(result['exit_code'],0,result.get('output'))
            self.assertEqual((root/'report.json').read_text(),'{"one": 1}')
            self.assertEqual((root/'nested'/'second.txt').read_text(),'two')
            self.assertEqual((root/'third.txt').read_text(),'three')
            if os.name=='posix':
                self.assertEqual((root/'first.txt').stat().st_mode&0o777,0o640)
            receipts=sorted((root/'.crewloom'/'transactions'/'receipts').iterdir())
            self.assertEqual(len(receipts),1,receipts)
            receipt=json.loads(receipts[0].read_text())
            self.assertEqual(sorted(receipt['outputs']),
                             ['nested/second.txt','report.json','third.txt'])


if __name__=='__main__':unittest.main()
