"""The tool payload a real host delivers is what the guard decides and the checkpoint reads.

Codex 0.155.1 and Claude 2.1.150 deliver `tool_name` beside `tool_input`; the OpenCode plugin
delivers `tool` beside `args`; and none of them reports a synthetic changed-path list after a tool
has run. A normalized actor payload hid all three facts, so every real Codex edit was denied for
the shape of its envelope and every real edit invalidated nothing. These cases drive the shipped
engine with the payloads the schema probe actually recorded, and through the real bridge command
wherever the answer is a host wire document, so the decision follows the arguments the host sent
rather than the keys a unit payload happened to use. Every case is offline: no host provider is
called, no authentication is read and no global configuration is written.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_lifecycle as hl
import repo_map
import test_host_lifecycle as fixture

BRIDGE = Path(__file__).resolve().parent / 'host_lifecycle.py'
MOVE_TARGET = fixture.DECLARED


class NativeToolPayload(fixture.Fixture):
    """One installed Codex contract whose declared scope is the real source and one report."""

    def setUp(self):
        super().setUp()
        self.record = self.install(outputs=(fixture.SOURCE_FILE, MOVE_TARGET))
        self.injected = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit',
                                    self.payload())

    def native(self, native_tool, native_args, **extra):
        """The Codex and Claude Code shape, exactly as the guard schema probe recorded it."""
        return self.payload(tool_name=native_tool, tool_input=native_args, **extra)

    def guard(self, payload):
        return hl.callback(self.root, fixture.PROJECT, 'codex', 'PreToolUse', payload)

    def checkpoint(self, payload):
        return hl.callback(self.root, fixture.PROJECT, 'codex', 'PostToolUse', payload)

    def wire(self, event, payload):
        """One real hook invocation, exactly as the installed control config runs it."""
        argv = [sys.executable, str(BRIDGE), 'event', '--project', str(self.root),
                '--project-id', fixture.PROJECT, '--host', 'codex', '--event', event,
                '--config-sha', self.record['payload_sha256']]
        return subprocess.run(argv, input=json.dumps(payload), cwd=str(self.root),
                              env=repo_map.git_environment(), capture_output=True, text=True,
                              timeout=60)

    # --------------------------------------------------------------------------- guard payloads

    def test_a_real_codex_patch_payload_is_decided_on_its_own_arguments(self):
        response = self.guard(self.native('apply_patch', {'command': fixture.patch_text(
            ('update', fixture.SOURCE_FILE, '    return user'))}))
        self.assertEqual(response['permissionDecision'], 'allow', response)
        self.assertEqual(response['decision']['operations'], ['update'])
        self.assertIn(fixture.SOURCE_FILE, response['decision']['targets'])

    def test_a_claude_file_tool_is_decided_on_the_target_key_its_schema_uses(self):
        for key in ('file_path', 'filePath', 'path'):
            with self.subTest(key=key):
                response = self.guard(self.native('Edit', {key: fixture.SOURCE_FILE,
                                                           'old_string': 'return user',
                                                           'new_string': 'return str(user)'}))
                self.assertEqual(response['permissionDecision'], 'allow', response)
                self.assertEqual(response['decision']['operations'], ['write'])

    def test_the_normalized_api_still_decides_the_same_boundary(self):
        allowed = self.guard(self.payload(tool='apply_patch', args={'command': fixture.patch_text(
            ('add', fixture.DECLARED, 'done'))}))
        self.assertEqual(allowed['permissionDecision'], 'allow', allowed)
        denied = self.guard(self.payload(tool='apply_patch', args={'command': fixture.patch_text(
            ('add', 'out/undeclared.txt', 'no'))}))
        self.assertEqual(denied['permissionDecision'], 'deny')
        self.assertIn('not a declared output', denied['permissionDecisionReason'])

    def test_a_native_payload_keeps_the_strict_unknown_and_compound_guards(self):
        # A real denial has to name the boundary that refused the call. A native payload that was
        # denied for the shape of its envelope instead would block every real edit while reporting
        # a protection this engine never actually applied.
        cases = (('web_search', {'query': 'anything'}, 'denied under strict policy'),
                 ('mcp__filesystem__write', {'path': fixture.SOURCE_FILE},
                  'denied under strict policy'),
                 ('shell', {'command': 'python3 -m unittest discover -s tests && rm -rf /',
                            'workdir': str(self.root)}, 'outside managed coverage'),
                 ('shell', {'command': 'python3 -m unittest discover -s tests', 'workdir': '/tmp'},
                  'canonical project root'))
        for tool, arguments, reason in cases:
            with self.subTest(tool=tool, arguments=arguments):
                response = self.guard(self.native(tool, arguments))
                self.assertEqual(response['permissionDecision'], 'deny', response)
                self.assertIn(reason, response['permissionDecisionReason'])

    def test_a_native_payload_never_grants_permission_to_host_authority(self):
        response = self.guard(self.native('Write', {'filePath': '.codex/hooks.json'}))
        self.assertEqual(response['permissionDecision'], 'deny')
        self.assertIn('never declared outputs', response['permissionDecisionReason'])

    # --------------------------------------------------------------------------- checkpoint payloads

    def test_every_endpoint_of_a_real_move_is_read_by_the_checkpoint(self):
        response = self.checkpoint(self.native('apply_patch', {'command': fixture.patch_text(
            ('update', fixture.SOURCE_FILE, '    return user', MOVE_TARGET))}))
        self.assertEqual(response['declared_changes'], sorted([fixture.SOURCE_FILE, MOVE_TARGET]))
        self.assertTrue(response['invalidated'])

    def test_a_checkpoint_never_claims_an_edit_it_was_not_told_about(self):
        for tool, arguments in (('bash', {'command': 'python3 -m unittest discover -s tests'}),
                                ('web_search', {'query': 'anything'})):
            with self.subTest(tool=tool):
                response = self.checkpoint(self.payload(tool=tool, args=arguments))
                self.assertEqual(response['declared_changes'], [])
                self.assertIsNone(response['invalidated'])
                self.assertEqual(response['tool'], tool)
        silent = self.checkpoint(self.payload())
        self.assertEqual(silent['declared_changes'], [])
        self.assertEqual(silent['changed_from'], 'no_tool_payload')
        self.assertIsNone(silent['tool'])

    def test_an_undeclared_touched_path_invalidates_nothing_and_still_checkpoints(self):
        response = self.checkpoint(self.native('apply_patch', {'command': fixture.patch_text(
            ('add', 'out/undeclared.txt', 'no'))}))
        self.assertTrue(response['checkpointed'])
        self.assertEqual(response['declared_changes'], [])
        self.assertIsNone(response['invalidated'])
        self.assertFalse((self.root / 'out' / 'undeclared.txt').exists())

    def test_the_explicit_changed_path_api_is_honoured_when_it_is_really_given(self):
        response = self.checkpoint(self.payload(tool='apply_patch',
                                                args={'changed_paths': [fixture.SOURCE_FILE]}))
        self.assertEqual(response['changed_from'], 'declared_changed_paths')
        self.assertEqual(response['declared_changes'], [fixture.SOURCE_FILE])
        self.assertTrue(response['invalidated'])
        # An empty list claims nothing about any file, so the real tool arguments still decide.
        empty = self.checkpoint(self.payload(tool='apply_patch', args={
            'paths': [], 'command': fixture.patch_text(
                ('update', fixture.SOURCE_FILE, '    return user'))}))
        self.assertEqual(empty['changed_from'], 'native_tool_arguments')
        self.assertEqual(empty['declared_changes'], [fixture.SOURCE_FILE])

    def test_a_checkpoint_after_a_real_edit_leaves_the_next_turn_fresh(self):
        (self.root / fixture.SOURCE_FILE).write_text(
            'def login(user):\n    """Authenticate a user."""\n    return str(user)\n', encoding='utf-8')
        self.checkpoint(self.native('apply_patch', {'command': fixture.patch_text(
            ('update', fixture.SOURCE_FILE, '    return user', MOVE_TARGET))}))
        again = hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())
        self.assertNotEqual(again['context_semantic_sha256'],
                            self.injected['context_semantic_sha256'])
        self.assertIn('return str(user)', again['additionalContext'])

    # --------------------------------------------------------------------------- refusals

    def test_a_malformed_native_payload_is_refused_instead_of_skipped(self):
        cases = {
            'contradictory tool names': self.native('apply_patch', {}, tool='edit'),
            'contradictory argument objects': self.native('apply_patch', {'command': 'x'},
                                                          args={'command': 'y'}),
            'argument object that is not an object': self.native('apply_patch', 'not-an-object'),
            'patch tool without its patch payload': self.native('apply_patch', {'unrelated': 1}),
            'unparseable patch payload': self.native('apply_patch', {'command': 'not a patch'}),
            'file tool without a target': self.native('Edit', {'old_string': 'a'}),
            'file tool with contradictory targets': self.native(
                'Write', {'filePath': fixture.SOURCE_FILE, 'file_path': MOVE_TARGET}),
            'malformed changed-path list': self.payload(tool='apply_patch',
                                                       args={'changed_paths': fixture.SOURCE_FILE}),
            'changed-path list with a non-path member': self.payload(
                tool='apply_patch', args={'changed_paths': [fixture.SOURCE_FILE, 7]}),
            'absolute endpoint': self.native('apply_patch', {'command': fixture.patch_text(
                ('update', '/etc/hosts', 'old'))}),
            'escaping endpoint': self.native('apply_patch', {'command': fixture.patch_text(
                ('update', '../outside.py', 'old'))}),
            'host authority endpoint': self.native('apply_patch', {'command': fixture.patch_text(
                ('add', '.crewloom/escaped.txt', 'no'))}),
        }
        for label, payload in cases.items():
            with self.subTest(payload=label):
                with self.assertRaises(hl.LifecycleError):
                    self.checkpoint(payload)

    # --------------------------------------------------------------------------- real wire

    def test_a_real_codex_wire_allows_a_declared_edit_and_denies_a_forbidden_one(self):
        allowed = self.wire('PreToolUse', dict(
            self.native('apply_patch', {'command': fixture.patch_text(
                ('update', fixture.SOURCE_FILE, '    return user'))}),
            hook_event_name='PreToolUse'))
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(allowed.stderr, '')
        hook = json.loads(allowed.stdout)['hookSpecificOutput']
        self.assertEqual(hook['hookEventName'], 'PreToolUse')
        self.assertEqual(hook['permissionDecision'], 'allow')
        denied = self.wire('PreToolUse', dict(
            self.native('apply_patch', {'command': fixture.patch_text(
                ('add', 'out/undeclared.txt', 'no'))}),
            hook_event_name='PreToolUse'))
        self.assertEqual(denied.returncode, 0, denied.stderr)
        hook = json.loads(denied.stdout)['hookSpecificOutput']
        self.assertEqual(hook['permissionDecision'], 'deny')
        self.assertIn('not a declared output', hook['permissionDecisionReason'])

    def test_a_refused_native_checkpoint_writes_no_document_and_keeps_stdout_clean(self):
        result = self.wire('PostToolUse', dict(self.native('apply_patch', {'unrelated': 1}),
                                               hook_event_name='PostToolUse'))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '', 'a refusal is never a successful checkpoint receipt')
        self.assertIn('real patchText payload', result.stderr)
        self.assertLessEqual(len(result.stderr.encode('utf-8')), hl.MAX_HOOK_ERROR_BYTES)

    def test_a_real_codex_wire_checkpoint_of_a_real_edit_writes_only_its_wire_shape(self):
        result = self.wire('PostToolUse', dict(
            self.native('apply_patch', {'command': fixture.patch_text(
                ('update', fixture.SOURCE_FILE, '    return user', MOVE_TARGET))}),
            hook_event_name='PostToolUse'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {},
                         'a checkpoint has no supported host document to answer with')
        logged = [item for item in hl.observed_events(self.root, 'codex')
                  if item.get('stage') == 'checkpoint']
        self.assertEqual(logged[-1]['declared_changes'], sorted([fixture.SOURCE_FILE, MOVE_TARGET]))
        self.assertEqual(logged[-1]['changed_from'], 'native_tool_arguments')
        self.assertTrue(logged[-1]['invalidated'])


class NativeOpenCodeToolPayload(fixture.Fixture):
    """The OpenCode plugin delivers `tool` and `args`, and reports no changed-path list either."""

    def setUp(self):
        super().setUp()
        self.record = self.install(host='opencode')
        hl.callback(self.root, fixture.PROJECT, 'opencode', 'experimental.chat.system.transform',
                    {'session_id': 'session-1', 'turn_id': 'turn-1', 'cwd': str(self.root)})

    def after(self, tool, arguments, **extra):
        payload = {'session_id': 'session-1', 'turn_id': 'turn-1', 'cwd': str(self.root),
                   'call_id': 'call-1', 'tool': tool, 'args': arguments}
        payload.update(extra)
        return hl.callback(self.root, fixture.PROJECT, 'opencode', 'tool.execute.after', payload)

    def test_a_real_opencode_edit_argument_object_invalidates_the_declared_source(self):
        response = self.after('edit', {'filePath': fixture.SOURCE_FILE,
                                       'oldString': '    return user',
                                       'newString': '    return str(user)'})
        self.assertEqual(response['declared_changes'], [fixture.SOURCE_FILE], response)
        self.assertEqual(response['changed_from'], 'native_tool_arguments')
        self.assertEqual(response['tool'], 'edit')
        self.assertTrue(response['invalidated'])

    def test_a_real_opencode_patch_payload_is_read_through_the_guard_parser(self):
        response = self.after('patch', {'patchText': fixture.patch_text(
            ('update', fixture.SOURCE_FILE, '    return user'))})
        self.assertEqual(response['declared_changes'], [fixture.SOURCE_FILE], response)
        self.assertTrue(response['invalidated'])

    def test_an_opencode_post_event_without_a_tool_records_no_edit(self):
        response = hl.callback(self.root, fixture.PROJECT, 'opencode', 'tool.execute.after',
                               {'session_id': 'session-1', 'turn_id': 'turn-1',
                                'cwd': str(self.root), 'tool': None, 'args': {}})
        self.assertTrue(response['checkpointed'])
        self.assertIsNone(response['invalidated'])
        self.assertEqual(response['changed_from'], 'no_tool_payload')


class NativeAliasedToolPayload(fixture.Fixture):
    """A declared output spelled in another case is the same file, and may not be replayed as one."""

    ALIASED = 'src/LOGIN.py'

    def setUp(self):
        super().setUp()
        self.record = self.install(outputs=(self.ALIASED, MOVE_TARGET))
        hl.callback(self.root, fixture.PROJECT, 'codex', 'UserPromptSubmit', self.payload())

    def test_a_declared_endpoint_reached_through_a_case_alias_is_refused(self):
        if not (self.root / 'SRC').exists():
            self.skipTest('Actual case-insensitive filesystem required; the macOS CI job proves it')
        # The spelling folds to the recorded declaration, so this engine knows exactly which file
        # the host touched, and it still refuses: reporting a change it cannot name is reporting no
        # change, and the next turn would keep reading a generation the host has already replaced.
        with self.assertRaises(hl.LifecycleError) as raised:
            hl.callback(self.root, fixture.PROJECT, 'codex', 'PostToolUse',
                        self.payload(tool_name='apply_patch', tool_input={'command':
                            fixture.patch_text(('update', self.ALIASED, '    return user'))}))
        self.assertIn('physical case alias', str(raised.exception))
        self.assertEqual([item for item in hl.observed_events(self.root, 'codex')
                          if item.get('stage') == 'checkpoint'], [],
                         'a refused checkpoint records no change at all')


if __name__ == '__main__':
    unittest.main()