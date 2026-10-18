"""Candidate import boundaries and optional live stdio protocol acceptance."""
import asyncio
import copy
import json
import os
import re
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import crewloom
import execution_policy as ep
import mcp_bridge
import project_binding as pb
import repo_map
import workflow as w


def fixture(root):
    subprocess.run(['git', 'init', '-q'], cwd=root, env=repo_map.git_environment(), check=True)
    pb.bootstrap(root, project_id='mcp-fixture', mode='enforced')
    _, errors = crewloom.install_skills(root, 'agents', ['fullstack-mvp-engineer'], False)
    if errors:
        raise AssertionError(errors)
    (root / 'contract.txt').write_text('candidate.txt must contain exactly correct')
    (root / 'verify.py').write_text("from pathlib import Path\nassert Path('candidate.txt').read_text() == 'correct'\nPath('receipt.json').write_text('{\"passed\":true}')\n")
    plan = {'schema_version': 1, 'id': 'mcp-task', 'steps': [
        {'id': 'produce', 'kind': 'task', 'role': 'fullstack-mvp-engineer',
         'summary': 'Implement the text contract', 'inputs': ['contract.txt'], 'outputs': ['candidate.txt']},
        {'id': 'verify', 'kind': 'command', 'role': 'fullstack-mvp-engineer',
         'summary': 'Verify the candidate', 'argv': ['python3', 'verify.py'],
         'inputs': ['candidate.txt', 'verify.py'], 'outputs': ['receipt.json']}]}
    (root / 'workflow.json').write_text(json.dumps(plan))
    plan, fingerprint = w.read_plan(root, 'workflow.json')
    result = w.run(root, plan, fingerprint, w.DEFAULT_IMAGE)
    if result['status'] != 'awaiting_task':
        raise AssertionError(result)
    return plan, fingerprint


class BridgeTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, repo_map.git_environment(), clear=True)
        env.start(); self.addCleanup(env.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan, self.fingerprint = fixture(self.root)
        self.bridge = mcp_bridge.Bridge(str(self.root), 'mcp-fixture', 'mcp-task', 'workflow.json')
        self.response = {'artifacts': [{'path': 'candidate.txt', 'content': 'correct'}]}

    def test_read_only_calls_do_not_change_files_and_refuse_writes(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(self.bridge.status()['task_id'], 'mcp-task')
        self.assertEqual(self.bridge.context()['scope']['task_id'], 'mcp-task')
        packet = self.bridge.packet()
        self.assertEqual(packet['output_sha256'], {'candidate.txt': None})
        with self.assertRaisesRegex(ValueError, 'disabled'):
            self.bridge.import_candidate(packet, self.response)
        with self.assertRaisesRegex(ValueError, 'disabled'):
            self.bridge.verify()
        after = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before, after)

    def test_import_records_private_candidate_without_accepting_task(self):
        bridge = mcp_bridge.Bridge(str(self.root), 'mcp-fixture', 'mcp-task', 'workflow.json', True)
        packet = bridge.packet()
        state_path = w.runtime(self.root, 'mcp-task') / 'state.json'
        before = state_path.read_bytes()
        result = bridge.import_candidate(packet, self.response)
        self.assertEqual((self.root / 'candidate.txt').read_text(), 'correct')
        self.assertFalse(result['execution_verified'])
        self.assertEqual(state_path.read_bytes(), before)
        reply = Path(result['reply_record'])
        self.assertEqual(reply.stat().st_mode & 0o777, 0o600)
        self.assertEqual(reply.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(json.loads(reply.read_text())['status'], 'imported')
        with self.assertRaisesRegex(ValueError, 'stale'):
            bridge.import_candidate(packet, self.response)

    def test_refuses_foreign_packet_and_changed_inputs_prompt_outputs(self):
        packet = self.bridge.packet()
        for key, value in [('checkout_id', '0' * 32), ('project_id', 'another-project'),
                           ('workflow', 'foreign-task'), ('prompt', 'different prompt')]:
            changed = copy.deepcopy(packet); changed[key] = value
            with self.assertRaises(ValueError):
                w.import_reply(self.root, self.plan, self.fingerprint, changed, self.response)
        (self.root / 'candidate.txt').write_text('owner edit')
        with self.assertRaisesRegex(ValueError, 'stale'):
            w.import_reply(self.root, self.plan, self.fingerprint, packet, self.response)
        self.assertEqual((self.root / 'candidate.txt').read_text(), 'owner edit')
        (self.root / 'contract.txt').write_text('new contract')
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.bridge.packet()

    def test_rejects_unscoped_response_and_publication_race(self):
        packet = self.bridge.packet()
        for response in ({'artifacts': []}, {'artifacts': [{'path': '../outside.txt', 'content': 'bad'}]},
                         {'artifacts': [{'path': '.codex/config.toml', 'content': 'bad'}]},
                         {'artifacts': [{'path': 'candidate.txt', 'content': ''}]}):
            with self.assertRaises(ValueError):
                w.import_reply(self.root, self.plan, self.fingerprint, packet, response)
        publish = ep.publish
        def changed(*args, **kwargs):
            (self.root / 'candidate.txt').write_text('concurrent owner edit')
            return publish(*args, **kwargs)
        with patch.object(ep, 'publish', side_effect=changed), self.assertRaisesRegex(ValueError, 'Outputs changed'):
            w.import_reply(self.root, self.plan, self.fingerprint, packet, self.response)
        self.assertEqual((self.root / 'candidate.txt').read_text(), 'concurrent owner edit')
        rejected = list((self.root / '.crewloom/private/agent-replies').rglob('reply.json'))
        self.assertEqual(json.loads(rejected[0].read_text())['status'], 'rejected')

    def test_bridge_refuses_identity_policy_plan_and_task_changes(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            mcp_bridge.Bridge(str(self.root), 'foreign-project', 'mcp-task')
        with self.assertRaisesRegex(ValueError, 'plan ID'):
            mcp_bridge.Bridge(str(self.root), 'mcp-fixture', 'foreign-task', 'workflow.json')
        value = json.loads((self.root / 'workflow.json').read_text())
        value['steps'][0]['summary'] = 'changed scope'
        (self.root / 'workflow.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            self.bridge.status()

    def test_bridge_refuses_policy_binding_and_reservation_changes(self):
        config = self.root / 'crewloom.project.json'
        original = config.read_bytes()
        value = json.loads(original); value['language'] = 'ar'
        config.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'policy changed'):
            self.bridge.status()
        config.write_bytes(original)
        binding = self.root / '.crewloom/binding.json'
        original = binding.read_bytes()
        value = json.loads(original); value['checkout_id'] = '0' * 32
        binding.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'binding changed'):
            self.bridge.status()
        binding.write_bytes(original)
        active = self.root / '.crewloom/active_task.json'
        value = json.loads(active.read_text()); value['task_id'] = 'different-task'
        active.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'another active project task'):
            self.bridge.status()

    def test_publication_rechecks_owner_bytes_after_staging(self):
        packet = self.bridge.packet()
        stage = ep._stage
        def changed(*args, **kwargs):
            result = stage(*args, **kwargs)
            (self.root / 'candidate.txt').write_text('owner edit after staging')
            return result
        with patch.object(ep, '_stage', side_effect=changed), self.assertRaisesRegex(ValueError, 'publication preparation'):
            w.import_reply(self.root, self.plan, self.fingerprint, packet, self.response)
        self.assertEqual((self.root / 'candidate.txt').read_text(), 'owner edit after staging')
        self.assertEqual(list((self.root / '.crewloom/execution/pending').glob('*')), [])

    def test_output_links_and_private_reply_links_are_rejected(self):
        outside = self.root / 'outside.txt'; outside.write_text('owner bytes')
        (self.root / 'candidate.txt').symlink_to(outside)
        with self.assertRaises(ValueError):
            self.bridge.packet()
        (self.root / 'candidate.txt').unlink()
        packet = self.bridge.packet()
        (self.root / '.crewloom/private').mkdir(exist_ok=True)
        (self.root / '.crewloom/private/agent-replies').symlink_to(self.root)
        with self.assertRaises(ValueError):
            w.import_reply(self.root, self.plan, self.fingerprint, packet, self.response)
        self.assertFalse((self.root / 'candidate.txt').exists())


@unittest.skipUnless(os.environ.get('CREWLOOM_MCP_TESTS') == '1', 'opt in to official SDK stdio acceptance')
class LiveProtocolTest(unittest.TestCase):
    def test_all_exposed_tools_and_real_docker_acceptance(self):
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            plan, fingerprint = fixture(root)
            command = [str(Path(__file__).with_name('mcp_bridge.py')), '--project', str(root),
                       '--project-id', 'mcp-fixture', '--task-id', 'mcp-task', '--plan', 'workflow.json']
            async def calls():
                for writable in (False, True):
                    args = command + (['--allow-import', '--allow-verify'] if writable else [])
                    async with Client(StdioServerParameters(command=sys.executable, args=args), mode='legacy') as client:
                        listed = await client.list_tools()
                        names = {tool.name for tool in listed.tools}
                        expected = {'crewloom_status', 'crewloom_context', 'crewloom_task_packet', 'crewloom_questions'}
                        if writable:
                            expected |= {'crewloom_import_reply', 'crewloom_verify'}
                        self.assertEqual(names, expected)
                        for name in ('crewloom_status', 'crewloom_context', 'crewloom_questions'):
                            result = await client.call_tool(name, {})
                            self.assertFalse(result.is_error, result)
                        bad = await client.call_tool('crewloom_status', {'project': '/foreign/project'})
                        # SDK schemas may ignore unknown arguments; they can never change the launch scope.
                        self.assertFalse(bad.is_error)
                        self.assertEqual(bad.structured_content['project_root'], str(root))
                        result = await client.call_tool('crewloom_task_packet', {})
                        self.assertFalse(result.is_error, result)
                        packet = result.structured_content
                        if writable:
                            response = {'artifacts': [{'path': 'candidate.txt', 'content': 'correct'}]}
                            imported = await client.call_tool('crewloom_import_reply', {'packet': packet, 'response': response})
                            self.assertFalse(imported.is_error, imported)
                            self.assertFalse(imported.structured_content['execution_verified'])
                            waiting = await client.call_tool('crewloom_verify', {})
                            self.assertFalse(waiting.is_error, waiting)
                            self.assertEqual(waiting.structured_content['status'], 'awaiting_task')
                            # Separate operator review, then the MCP tool invokes the unchanged container verifier.
                            w.run(root, plan, fingerprint, w.DEFAULT_IMAGE, accept='produce', reviewer='fixture-reviewer')
                            verified = await client.call_tool('crewloom_verify', {})
                            self.assertFalse(verified.is_error, verified)
                            self.assertEqual(verified.structured_content['status'], 'complete')
            asyncio.run(calls())
            self.assertEqual(json.loads((root / 'receipt.json').read_text()), {'passed': True})


@unittest.skipUnless(os.environ.get('CREWLOOM_BROWSER_MCP_TESTS') == '1', 'opt in to official Playwright MCP acceptance')
class LiveBrowserProtocolTest(unittest.TestCase):
    def test_isolated_navigation_snapshot_click_and_close(self):
        from mcp import Client
        from mcp.client.stdio import StdioServerParameters
        npx = shutil.which('npx')
        self.assertIsNotNone(npx, 'Install Node/npm before enabling the browser integration test')
        class Page(BaseHTTPRequestHandler):
            def do_GET(self):
                body = b'<!doctype html><html><title>MCP fixture</title><button onclick="document.getElementById(\'counter\').textContent=\'count:1\'">Increment</button><p id="counter">count:0</p></html>'
                self.send_response(200); self.send_header('Content-Type', 'text/html')
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *args):
                pass
        http = ThreadingHTTPServer(('127.0.0.1', 0), Page)
        thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            args = ['-y', '@playwright/mcp@0.0.83', '--isolated', '--headless', '--no-webmcp',
                    '--block-service-workers', '--output-dir', str(root / '.crewloom/private/browser')]
            env = {}
            if os.environ.get('PLAYWRIGHT_MCP_EXECUTABLE_PATH'):
                env['PLAYWRIGHT_MCP_EXECUTABLE_PATH'] = os.environ['PLAYWRIGHT_MCP_EXECUTABLE_PATH']
            def text(result):
                self.assertFalse(result.is_error, result)
                return '\n'.join(block.text for block in result.content if block.type == 'text')
            async def calls():
                params = StdioServerParameters(command=npx, args=args, env=env, cwd=str(root))
                async with Client(params, mode='legacy') as client:
                    names = {tool.name for tool in (await client.list_tools()).tools}
                    self.assertTrue({'browser_navigate', 'browser_snapshot', 'browser_click', 'browser_close'} <= names)
                    text(await client.call_tool('browser_navigate', {'url': 'http://127.0.0.1:' + str(http.server_port)}))
                    snapshot = text(await client.call_tool('browser_snapshot', {}))
                    match = re.search(r'button "Increment" \[ref=([^\]]+)\]', snapshot)
                    self.assertIsNotNone(match, snapshot)
                    text(await client.call_tool('browser_click', {'element': 'Increment button', 'target': match.group(1)}))
                    self.assertIn('count:1', text(await client.call_tool('browser_snapshot', {})))
                    text(await client.call_tool('browser_close', {}))
            asyncio.run(calls())


if __name__ == '__main__':
    unittest.main()
