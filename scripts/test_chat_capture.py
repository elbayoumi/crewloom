"""Opt-in prompt capture, immutable provenance and clarification boundaries."""
import json
import unittest
from unittest.mock import patch
import user_context as uc
import host_lifecycle as hl
import mcp_bridge
import test_user_context
from test_host_lifecycle import Fixture, PROJECT


class CaptureTests(unittest.TestCase):
    def setUp(self):
        fixture = test_user_context.UserContextTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.task = 'understand-task'
        uc.configure_capture(self.root, self.task, 'owner', 'Fix defects', ['Tests pass'])

    def capture(self, message, turn='t1'):
        return uc.capture_message(self.root, self.task, 'codex', 's', turn, message)

    def test_exact_arabic_source_private_permissions_and_duplicate(self):
        message = 'الرد بالعربي. Fix the real bug.'
        self.assertEqual(self.capture(message)['status'], 'captured')
        self.assertTrue(self.capture(message)['duplicate'])
        store = uc.load(self.root)
        self.assertEqual(len(store['captured_tasks'][self.task]['turns']), 1)
        source = self.root / store['records'][0]['source']['path']
        self.assertEqual(source.read_text(), message)
        self.assertEqual(source.stat().st_mode & 0o777, 0o600)
        self.assertEqual(uc.select(self.root, self.task)['memories'][-1]['value'], 'الرد بالعربي')
        with self.assertRaisesRegex(ValueError, 'different source'):
            self.capture('different text')

    def test_questions_require_later_exact_answer_and_cannot_be_erased(self):
        result = self.capture('Use [TBD] as the target.')
        question = result['questions'][0]
        with self.assertRaisesRegex(ValueError, 'unresolved questions'):
            uc.select(self.root, self.task)
        with self.assertRaisesRegex(ValueError, 'later captured'):
            uc.answer_question(self.root, self.task, question['id'], question['source']['path'], 'Use')
        with self.assertRaisesRegex(ValueError, 'cannot erase'):
            uc.contract(self.root, self.task, 'owner', 'Fix', [], ['Pass'], [], question['source']['path'], '[TBD]')
        self.capture('The target is the local fixture.', 't2')
        store = uc.load(self.root)
        source = next(t['source'] for t in store['captured_tasks'][self.task]['turns'].values() if t['turn_id'] == 't2')
        with self.assertRaisesRegex(ValueError, 'absent'):
            uc.answer_question(self.root, self.task, question['id'], source, 'invented answer')
        uc.answer_question(self.root, self.task, question['id'], source, 'The target is the local fixture.')
        self.assertEqual(uc.select(self.root, self.task)['contract']['questions'], [])
        with self.assertRaisesRegex(ValueError, 'already resolved'):
            uc.answer_question(self.root, self.task, question['id'], source, 'The target')

    def test_disabled_capture_and_scope_do_not_widen_authority(self):
        self.assertEqual(uc.capture_message(self.root, 'other-task', None, None, None, None)['status'], 'disabled')
        self.capture('hello')
        with self.assertRaisesRegex(ValueError, 'another user'):
            uc.configure_capture(self.root, self.task, 'other-user', 'Fix', ['Pass'])
        bridge = mcp_bridge.Bridge(str(self.root), 'sample-project', self.task)
        with self.assertRaisesRegex(ValueError, 'allow-context-update'):
            bridge.answer('q-any', 'outside', 'text')

    def test_missing_text_changed_policy_and_budgets_fail_before_write(self):
        with self.assertRaises(ValueError): self.capture(None)
        with self.assertRaises(ValueError): self.capture('x' * 8193)
        for i in range(8): self.capture('message ' + str(i), 'turn-' + str(i))
        before = (self.root / uc.RELATIVE).read_bytes()
        with self.assertRaisesRegex(ValueError, 'window is full'): self.capture('ninth', 'turn-9')
        self.assertEqual((self.root / uc.RELATIVE).read_bytes(), before)
        policy = self.root / uc.CAPTURE_POLICY.format(task_id=self.task)
        value = json.loads(policy.read_text()); value['scope']['project_id'] = 'foreign'
        policy.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'another project'): self.capture('hello')

    def test_malformed_metadata_is_rejected(self):
        self.capture('hello')
        path = self.root / uc.RELATIVE
        value = json.loads(path.read_text()); value['captured_tasks'][self.task]['turns'] = []
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'Malformed capture'): uc.load(self.root)

    def test_disabling_preserves_history_and_open_questions(self):
        self.capture('Use [TBD].')
        before = (self.root / uc.RELATIVE).read_bytes()
        self.assertEqual(uc.disable_capture(self.root, self.task)['status'], 'disabled')
        self.assertEqual(self.capture('new text', 't2')['status'], 'disabled')
        self.assertEqual((self.root / uc.RELATIVE).read_bytes(), before)
        self.assertEqual(uc.capture_status(self.root, self.task)['questions'][0]['status'], 'open')


class NativeCaptureTests(Fixture):
    def test_real_callback_questions_block_tools_and_raw_text_stays_private(self):
        record = self.install_default()
        prepared = hl.callback(self.root, PROJECT, 'codex', 'SessionStart', self.payload(turn_id=None), config_sha=record['payload_sha256'])
        task = prepared['task_id']
        uc.configure_capture(self.root, task, 'owner', 'Fix local fixture', ['Tests pass'])
        response = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(prompt='PRIVATE-CAPTURE-SENTINEL [TBD]'), config_sha=record['payload_sha256'])
        self.assertTrue(response['clarification_required'])
        self.assertFalse(response['injected'])
        guarded = hl.callback(self.root, PROJECT, 'codex', 'PreToolUse', self.payload(tool='bash', args={'command': 'python3 -m unittest'}), config_sha=record['payload_sha256'])
        self.assertFalse(guarded['allowed'])
        self.assertIn('unresolved questions', guarded['permissionDecisionReason'])
        self.assertNotIn('PRIVATE-CAPTURE-SENTINEL', hl._events_path(self.root, 'codex').read_text())
        answered = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(turn_id='turn-2', prompt='The target is the fixture.'), config_sha=record['payload_sha256'])
        self.assertTrue(answered['clarification_required'])
        store = uc.load(self.root)
        source = next(t['source'] for t in store['captured_tasks'][task]['turns'].values() if t['turn_id'] == 'turn-2')
        question = uc.capture_status(self.root, task)['questions'][0]
        uc.answer_question(self.root, task, question['id'], source, 'The target is the fixture.')
        injected = hl.callback(self.root, PROJECT, 'codex', 'UserPromptSubmit', self.payload(turn_id='turn-3', prompt='Continue with that target.'), config_sha=record['payload_sha256'])
        self.assertTrue(injected['injected'])
        self.assertIn('The target is the fixture.', injected['additionalContext'])


if __name__ == '__main__': unittest.main()


class LiveCaptureProtocol(unittest.TestCase):
    @unittest.skipUnless(__import__('os').environ.get('CREWLOOM_MCP_TESTS') == '1', 'opt in to real SDK stdio')
    def test_read_questions_and_explicit_answer_tool(self):
        import asyncio
        import sys
        from pathlib import Path
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        fixture = test_user_context.UserContextTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.root; task = 'understand-task'
        uc.configure_capture(root, task, 'owner', 'Fix local target', ['Tests pass'])
        question = uc.capture_message(root, task, 'codex', 's', 't1', 'Use [TBD].')['questions'][0]
        uc.capture_message(root, task, 'codex', 's', 't2', 'Use the local fixture.')
        source = next(t['source'] for t in uc.load(root)['captured_tasks'][task]['turns'].values() if t['turn_id'] == 't2')
        async def run():
            args = [str(Path(__file__).with_name('mcp_bridge.py')), '--project', str(root), '--project-id', 'sample-project',
                    '--task-id', task, '--allow-context-update']
            async with Client(StdioServerParameters(command=sys.executable, args=args), mode='legacy') as client:
                self.assertEqual({t.name for t in (await client.list_tools()).tools},
                                 {'crewloom_status', 'crewloom_context', 'crewloom_questions', 'crewloom_answer'})
                status = await client.call_tool('crewloom_status', {}); self.assertFalse(status.is_error)
                questions = await client.call_tool('crewloom_questions', {}); self.assertFalse(questions.is_error)
                self.assertEqual(questions.structured_content['questions'][0]['id'], question['id'])
                stale = await client.call_tool('crewloom_context', {}); self.assertTrue(stale.is_error)
                args = {'question_id': question['id'], 'source': source, 'quote': 'Use the local fixture.'}
                answer = await client.call_tool('crewloom_answer', args); self.assertFalse(answer.is_error, answer)
                self.assertEqual(answer.structured_content['remaining'], 0)
                replay = await client.call_tool('crewloom_answer', args); self.assertTrue(replay.is_error)
        asyncio.run(run())
