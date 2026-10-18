"""Driver-independent bad/clean scope and one-use AX action contracts."""
import asyncio
import json
import os
import sys
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import native_desktop as nd
import test_user_context


class FakeDriver:
    def __init__(self): self.calls = []; self.count = 0; self.foreign = False
    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if name == 'check_permissions': value = {'accessibility': True}
        elif name == 'list_apps': raise AssertionError('Global app discovery is outside the manifest')
        elif name == 'list_windows':
            if self.foreign:
                return SimpleNamespace(is_error=True, structured_content={'refusal': {'code': 'bounded_resource_outside_manifest'}})
            value = {'windows': [{'pid': 42, 'window_id': 7, 'title': 'Crewloom Native Acceptance'}]}
        elif name == 'get_window_state':
            value = {'pid':42, 'window_id':7, 'window_title':'Crewloom Native Acceptance', 'elements_complete':False,
                     'tree_markdown':'- [0] AXWindow "Crewloom Native Acceptance"\n  - AXStaticText = "count:' + str(self.count) + '"\n- [4] AXMenuBar\n  - Private menu history',
                     'elements': [{'element_index':0,'role':'AXWindow','label':'Crewloom Native Acceptance'},
                                  {'element_index':1,'parent_index':0,'role': 'AXButton', 'label': 'Increment', 'enabled':True,'actions': ['AXPress'], 'element_token': 'token-1'},
                                  {'element_index':2,'parent_index':0,'role': 'AXButton', 'label': 'Grant permission', 'enabled':True,'actions': ['AXPress'], 'element_token': 'protected'},
                                  {'element_index':3,'parent_index':0,'role': 'AXStaticText', 'label': 'count:' + str(self.count)},
                                  {'element_index':4,'role':'AXMenuBar','label':'Private menu history'},
                                  {'element_index':5,'parent_index':4,'role':'AXButton','label':'Increment','enabled':True,'actions':['AXPress'],'element_token':'menu-button'}]}
        elif name == 'click': self.count += 1; value = {'status': 'delivered'}
        else: raise AssertionError(name)
        return SimpleNamespace(is_error=False, structured_content=value)


class NativeScopeTests(unittest.TestCase):
    def setUp(self):
        fixture = test_user_context.UserContextTests()
        with patch('tempfile.tempdir', '/tmp'): fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.prepared = nd.prepare(str(self.root), 'sample-project', 'understand-task')
        self.driver = FakeDriver()
        self.controller = nd.Controller(str(self.root), 'sample-project', 'understand-task', self.prepared['policy'], self.driver, pid=42)

    def test_exact_observe_act_reobserve_and_stale_refusal(self):
        async def run():
            snapshot = await self.controller.snapshot()
            self.assertEqual([b['label'] for b in snapshot['buttons']], ['Increment'])
            handle = snapshot['buttons'][0]['handle']
            after = await self.controller.click(handle)
            self.assertEqual(after['elements'][-1]['label'], 'count:1')
            self.assertFalse(after['action']['postcondition_verified'])
            self.assertIn('count:1', after['window_text'])
            self.assertNotIn('Private menu history', json.dumps(after))
            self.assertNotIn('element_token', json.dumps(after))
            with self.assertRaisesRegex(ValueError, 'stale'): await self.controller.click(handle)
        asyncio.run(run())
        clicks = [args for name, args in self.driver.calls if name == 'click']
        self.assertEqual(clicks, [{'pid': 42, 'window_id': 7, 'element_token': 'token-1', 'delivery_mode': 'background'}])
        self.assertTrue(all(args.get('prompt') is False for name,args in self.driver.calls if name == 'check_permissions'))
        self.assertFalse(any(name == 'list_apps' for name, args in self.driver.calls))

    def test_construction_never_allocates_an_event_loop_lock(self):
        with patch.object(nd.asyncio, 'Lock', side_effect=AssertionError('No lock outside a running loop')):
            nd.Controller(str(self.root), 'sample-project', 'understand-task',
                          self.prepared['policy'], self.driver, pid=42)

    def test_concurrent_observations_serialize_and_foreign_loops_are_refused(self):
        original = self.driver.call_tool
        active = peak = 0
        async def delayed(name, args):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0)
                return await original(name, args)
            finally:
                active -= 1
        async def run():
            snapshots = await asyncio.gather(self.controller.snapshot(), self.controller.snapshot())
            self.assertEqual([value['observation'] for value in snapshots], [1, 2])
        with patch.object(self.driver, 'call_tool', delayed):
            asyncio.run(run())
        self.assertEqual(peak, 1)
        calls = len(self.driver.calls)
        with self.assertRaisesRegex(ValueError, 'event loop'):
            asyncio.run(self.controller.snapshot())
        self.assertEqual(len(self.driver.calls), calls)

    def test_foreign_target_and_changed_manifest_are_refused_before_click(self):
        async def run():
            snapshot = await self.controller.snapshot()
            self.driver.foreign = True
            with self.assertRaisesRegex(ValueError, 'refused list_windows'): await self.controller.click(snapshot['buttons'][0]['handle'])
        asyncio.run(run())
        self.assertFalse(any(name == 'click' for name, args in self.driver.calls))
        manifest = self.root / json.loads((self.root / self.prepared['policy']).read_text())['manifest']
        manifest.write_text('version: 3\nallow: all\n')
        with self.assertRaisesRegex(ValueError, 'changed'): self.controller.guard()

    def test_failed_refresh_invalidates_old_handles_and_missing_permission_never_prompts(self):
        async def run():
            snapshot = await self.controller.snapshot()
            self.driver.foreign = True
            with self.assertRaises(ValueError): await self.controller.snapshot()
            self.driver.foreign = False
            with self.assertRaisesRegex(ValueError, 'stale'): await self.controller.click(snapshot['buttons'][0]['handle'])
        asyncio.run(run())

    def test_scope_permissions_and_preparation_are_immutable(self):
        with self.assertRaisesRegex(ValueError, 'cannot be overwritten'):
            nd.prepare(str(self.root), 'sample-project', 'understand-task')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            nd.Controller(str(self.root), 'foreign-project', 'understand-task', self.prepared['policy'], self.driver)
        policy = self.root / self.prepared['policy']; policy.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'owner-only'):
            nd.Controller(str(self.root), 'sample-project', 'understand-task', self.prepared['policy'], self.driver)

    def test_missing_boolean_and_invalid_pid_are_refused(self):
        for pid in (None, True, 0, -1, '42', 2147483648):
            with self.subTest(pid=pid), self.assertRaisesRegex(ValueError, 'observed app PID'):
                nd.Controller(str(self.root), 'sample-project', 'understand-task', self.prepared['policy'], self.driver, pid=pid)

    def test_wrong_snapshot_identity_and_incomplete_window_refuse_old_handles(self):
        async def run():
            original = self.driver.call_tool
            for alteration in ('identity', 'truncated', 'duplicate'):
                before = await self.controller.snapshot()
                async def malformed(name, args):
                    result = await original(name, args)
                    if name == 'get_window_state':
                        value = result.structured_content
                        if alteration == 'identity': value['window_id'] = 999
                        elif alteration == 'truncated': value['tree_markdown'] = value['tree_markdown'].split('\n- [4]')[0]
                        else: value['elements'].append(dict(value['elements'][0]))
                    return result
                with patch.object(self.driver, 'call_tool', malformed):
                    with self.assertRaises(ValueError): await self.controller.snapshot()
                with self.assertRaisesRegex(ValueError, 'stale'):
                    await self.controller.click(before['buttons'][0]['handle'])
        asyncio.run(run())
        self.assertFalse(any(name == 'click' for name, args in self.driver.calls))

    def test_disabled_button_is_not_actionable(self):
        original = self.driver.call_tool
        async def disabled(name, args):
            result = await original(name, args)
            if name == 'get_window_state': result.structured_content['elements'][1]['enabled'] = False
            return result
        with patch.object(self.driver, 'call_tool', disabled):
            self.assertEqual(asyncio.run(self.controller.snapshot())['buttons'], [])

    def test_custom_scope_requires_complete_exact_target_before_writing(self):
        nd.pb.cancel(self.root,'sample-project','understand-task','Prepare another explicitly scoped test')
        directory = self.root / '.crewloom/private/native' / nd.w.digest(b'custom-task')[:8]
        invalid = [dict(bundle_id='com.apple.calculator'), dict(bundle_id='com.apple.calculator', window_title='Calculator'),
                   dict(bundle_id='com.apple.calculator\nallow: all',window_title='Calculator',buttons=['7']),
                   dict(bundle_id='com.apple.calculator',window_title='Calculator\nOther',buttons=['7']),
                   dict(bundle_id='com.apple.calculator',window_title='Calculator',buttons=['7','7']),
                   dict(bundle_id='com.apple.calculator',window_title='Calculator',buttons=['7'],read_only=True)]
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                nd.prepare(str(self.root),'sample-project','custom-task',**kwargs)
            self.assertFalse(directory.exists())
        result=nd.prepare(str(self.root),'sample-project','custom-task',bundle_id='com.apple.calculator',window_title='Calculator',buttons=['7','Equals'])
        manifest=Path(result['manifest']).read_text()
        self.assertIn('bundle_id: com.apple.calculator',manifest)
        self.assertNotIn('list_apps',manifest)

    def test_read_only_policy_has_no_click_authority(self):
        nd.pb.cancel(self.root,'sample-project','understand-task','Prepare another explicitly scoped test')
        result=nd.prepare(str(self.root),'sample-project','read-task',bundle_id='com.apple.calculator',window_title='Calculator',read_only=True)
        self.assertNotIn('"click"',Path(result['manifest']).read_text())
        controller=nd.Controller(str(self.root),'sample-project','read-task',result['policy'],self.driver,pid=42)
        with self.assertRaisesRegex(ValueError,'observation only'):asyncio.run(controller.click('arbitrary'))
        self.assertEqual(self.driver.calls,[])


@unittest.skipUnless(os.environ.get('CREWLOOM_NATIVE_LIVE') == '1', 'opt in to human-approved native fixture acceptance')
class LiveNativeAcceptance(unittest.TestCase):
    def test_real_scoped_stdio_observe_press_reobserve(self):
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        root = Path(os.environ['CREWLOOM_NATIVE_PROJECT']).resolve(strict=True)
        task = os.environ['CREWLOOM_NATIVE_TASK_ID']
        policy = os.environ['CREWLOOM_NATIVE_POLICY']
        pid = int(os.environ['CREWLOOM_NATIVE_PID'])
        project_id = os.environ['CREWLOOM_NATIVE_PROJECT_ID']
        args = [str(Path(nd.__file__)), 'serve', '--project', str(root), '--project-id', project_id,
                '--task-id', task, '--policy', policy, '--pid', str(pid)]
        report = {'task_id':task, 'pid':pid, 'module':str(Path(nd.__file__)), 'calls':[], 'passed':False}
        relative = '.crewloom/private/native/' + nd.w.digest(task.encode())[:8] + '/acceptance-' + uuid.uuid4().hex + '.json'
        def save(): nd.privacy.private_write(root, relative, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        def count(value):
            matches = re.findall(r'AXStaticText = "count:(\d+)"', value['window_text'])
            self.assertEqual(len(matches), 1, 'Exactly one observed counter is required')
            return int(matches[0])
        async def run():
            async with Client(StdioServerParameters(command=sys.executable,args=args,cwd=str(root)),mode='legacy') as client:
                names = {tool.name for tool in (await client.list_tools()).tools}
                self.assertEqual(names, {'crewloom_native_snapshot','crewloom_native_click'})
                async def call(name, arguments, error=False):
                    result = await client.call_tool(name, arguments)
                    report['calls'].append({'tool':name, 'arguments':arguments, 'result':result.model_dump(mode='json',by_alias=True)})
                    save()
                    self.assertEqual(result.is_error, error, result)
                    return result.structured_content
                before = await call('crewloom_native_snapshot',{})
                self.assertEqual(count(before),0)
                self.assertEqual({button['label'] for button in before['buttons']},{'Increment','Reset'})
                self.assertNotIn('AXMenuBar',json.dumps(before))
                handle = next(button['handle'] for button in before['buttons'] if button['label']=='Increment')
                after = await call('crewloom_native_click',{'handle':handle})
                self.assertEqual(count(after),1)
                await call('crewloom_native_click',{'handle':handle},error=True)
                unchanged = await call('crewloom_native_snapshot',{})
                self.assertEqual(count(unchanged),1)
                reset = next(button['handle'] for button in unchanged['buttons'] if button['label']=='Reset')
                cleared = await call('crewloom_native_click',{'handle':reset})
                self.assertEqual(count(cleared),0)
                await call('crewloom_native_click',{'handle':'unobserved-button'},error=True)
            # A different process is denied by the same approved bounded daemon
            # before any window observation or input; no policy expansion.
            foreign = args[:-1] + [str(os.getpid())]
            async with Client(StdioServerParameters(command=sys.executable,args=foreign,cwd=str(root)),mode='legacy') as client:
                result = await client.call_tool('crewloom_native_snapshot',{})
                report['foreign_process_refusal'] = result.model_dump(mode='json',by_alias=True)
                self.assertTrue(result.is_error,result)
            report['passed']=True
        save()
        try: asyncio.run(run())
        finally: save()
        print('Native acceptance evidence: '+str(root/relative))


if __name__ == '__main__': unittest.main()
