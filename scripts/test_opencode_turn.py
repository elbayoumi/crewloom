"""The real OpenCode turn identity reaches every Crewloom stage from either host identity.

OpenCode 1.18.32 generates the user turn inside the host and hands the callback the resulting
`UserMessage` as `output.message`, while `input.messageID` is optional in the installed hook
types. These cases exercise the shipped adapter template through the real callback engine and a
bridge that records exactly what reached it, so a turn is proven to be bound to the identity the
host actually produced, and every unsupported identity is proven to stop generation before the
engine is called at all.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = 'adapters/opencode/crewloom-lifecycle.js'
RECORD = 'CREWLOOM_TURN_RECORD'
MARKER = 'generated-turn-context'
MAX_ID_LENGTH = 200
STAGES = ('prepare', 'inject', 'guard', 'checkpoint', 'verify')

BRIDGE = '''import json, os, sys
stage = sys.argv[sys.argv.index('--stage') + 1]
payload = json.load(sys.stdin)
with open(os.environ[%r], 'a', encoding='utf-8') as handle:
    handle.write(json.dumps({'stage': stage, 'payload': payload}) + '\\n')
answers = {
    'prepare': {'status': 'prepared'},
    'inject': {'additionalContext': %r},
    'guard': {'permissionDecision': 'allow'},
}
print(json.dumps(answers.get(stage, {'status': stage})))
''' % (RECORD, MARKER)

PROGRAM = ("import { CrewloomLifecycle } from './plugin.mjs';\n"
           'const hooks = await CrewloomLifecycle({directory: process.cwd(), worktree: process.cwd()});\n')

LIFECYCLE = ("await hooks['chat.message']({sessionID: 's'}, {message: {id: 'msg_generated', sessionID: 's'}});"
             "const output = {system: []};"
             "await hooks['experimental.chat.system.transform']({sessionID: 's'}, output);"
             "await hooks['tool.execute.before']({sessionID: 's', callID: 'c', tool: 'bash'}, {args: {command: 'ls'}});"
             "await hooks['tool.execute.after']({sessionID: 's', callID: 'c', tool: 'bash'});"
             "await hooks['event']({event: {type: 'session.idle', properties: {sessionID: 's'}}});"
             'console.log(JSON.stringify(output));')


@unittest.skipUnless(shutil.which('node'), 'Node is required to exercise the real plugin callbacks')
class OpenCodeTurnIdentity(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        bridge = self.project / 'bridge.py'
        bridge.write_text(BRIDGE, encoding='utf-8')
        source = (ROOT / TEMPLATE).read_text(encoding='utf-8')
        substitutions = {'__CREWLOOM_BRIDGE_ARGV__': json.dumps([sys.executable, str(bridge)]),
                         '__CREWLOOM_ROOT__': json.dumps(str(self.project)),
                         '__CREWLOOM_PROJECT_ID__': json.dumps('opencode-turn'),
                         '__CREWLOOM_CONFIG_SHA__': json.dumps('b' * 64)}
        for key, value in substitutions.items():
            source = source.replace(key, value)
        self.assertNotIn('__CREWLOOM_', source, 'The owned template was not fully rendered')
        (self.project / 'plugin.mjs').write_text(source, encoding='utf-8')
        self.record = self.project / 'record.jsonl'
        previous = os.environ.get(RECORD)
        os.environ[RECORD] = str(self.record)

        def restore():
            if previous is None:
                os.environ.pop(RECORD, None)
            else:
                os.environ[RECORD] = previous

        self.addCleanup(restore)

    def node(self, body):
        return subprocess.run([shutil.which('node'), '--input-type=module', '-e', PROGRAM + body],
                              cwd=str(self.project), capture_output=True, text=True, timeout=30)

    def stages(self):
        if not self.record.exists():
            return []
        lines = [line for line in self.record.read_text(encoding='utf-8').splitlines() if line.strip()]
        return [(json.loads(line)['stage'], json.loads(line)['payload']) for line in lines]

    def assert_refused_before_the_engine(self, body, reason):
        result = self.node(body)
        self.assertNotEqual(result.returncode, 0,
                            'An unsupported turn identity was silently accepted: ' + result.stdout)
        self.assertIn(reason, result.stderr)
        self.assertEqual(self.stages(), [],
                         'A refused turn identity still reached the Crewloom lifecycle engine')

    def test_generated_user_message_reaches_every_stage_as_the_turn(self):
        result = self.node(LIFECYCLE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['system'], [MARKER])
        recorded = self.stages()
        self.assertEqual([stage for stage, _ in recorded], list(STAGES))
        for _, payload in recorded:
            self.assertEqual(payload['turn_id'], 'msg_generated')
            self.assertEqual(payload['session_id'], 's')

    def test_the_old_declared_message_id_shape_still_binds_its_turn(self):
        result = self.node("await hooks['chat.message']({sessionID: 's', messageID: 'legacy_turn'}, {});"
                           "const output = {system: []};"
                           "await hooks['experimental.chat.system.transform']({sessionID: 's'}, output);"
                           'console.log(JSON.stringify(output));')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['system'], [MARKER])
        self.assertEqual([payload['turn_id'] for _, payload in self.stages()],
                         ['legacy_turn', 'legacy_turn'])

    def test_two_identities_that_agree_prepare_one_turn(self):
        result = self.node("await hooks['chat.message']({sessionID: 's', messageID: 'agreed'},"
                           " {message: {id: 'agreed', sessionID: 's'}});"
                           "const output = {system: []};"
                           "await hooks['experimental.chat.system.transform']({sessionID: 's'}, output);"
                           'console.log(JSON.stringify(output));')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([stage for stage, _ in self.stages()], ['prepare', 'inject'])

    def test_a_generated_message_from_a_foreign_session_is_refused(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({sessionID: 's'}, {message: {id: 't', sessionID: 'foreign'}});",
            'from another session')

    def test_two_different_identities_for_one_turn_are_refused(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({sessionID: 's', messageID: 'input_turn'},"
            " {message: {id: 'output_turn', sessionID: 's'}});",
            'two different host message identities')

    def test_a_declared_identity_is_never_replaced_by_the_generated_message(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({sessionID: 's', messageID: '   '},"
            " {message: {id: 'msg_generated', sessionID: 's'}});",
            'not a real turn identity')

    def test_a_generated_message_without_a_real_id_is_refused(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({sessionID: 's'}, {message: {id: '', sessionID: 's'}});",
            'not a real turn identity')

    def test_a_generated_message_without_its_own_session_is_refused(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({sessionID: 's'}, {message: {id: 'msg_generated'}});",
            'from another session')

    def test_no_identity_at_all_is_refused_and_nothing_is_invented(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({sessionID: 's'}, {});",
            'without a real host message identity')

    def test_the_identity_bound_matches_the_engine_text_limit(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({sessionID: 's'}, {message: {id: '%s', sessionID: 's'}});"
            % ('x' * (MAX_ID_LENGTH + 1)),
            'not a real turn identity')
        result = self.node("await hooks['chat.message']({sessionID: 's'},"
                           " {message: {id: '%s', sessionID: 's'}});"
                           % ('x' * MAX_ID_LENGTH))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.stages()[0][1]['turn_id'], 'x' * MAX_ID_LENGTH)

    def test_the_session_identity_is_still_required(self):
        self.assert_refused_before_the_engine(
            "await hooks['chat.message']({}, {message: {id: 'msg_generated', sessionID: 's'}});",
            'without a real host sessionID')

    def test_the_adapter_has_no_way_to_invent_a_turn_identity(self):
        source = (ROOT / TEMPLATE).read_text(encoding='utf-8')
        for generator in ('randomUUID', 'Math.random', 'Date.now'):
            self.assertNotIn(generator, source,
                             'The adapter grew a fabricated turn identity source: ' + generator)


if __name__ == '__main__':
    unittest.main()