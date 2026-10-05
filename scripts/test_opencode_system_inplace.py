"""Injected context reaches the model through the system array the host already owns.

OpenCode 1.18.32 reads the system prompt array it built before it invokes
`experimental.chat.system.transform`, so reassigning `output.system` returns a value the host never
reads again: the callback runs, the Crewloom bridge records the injected context, and the model
never sees it. The real-host receipt delivery failed for exactly that reason. These cases hold a
reference to the very array object the host handed the callback and prove the injected context
lands inside that same object, that what the host already wrote stays in place ahead of it, and that
a host that hands over no system array at all is refused instead of being handed a detached one.
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
RECORD = 'CREWLOOM_SYSTEM_RECORD'
MARKER = 'host-owned-turn-context'

BRIDGE = '''import json, os, sys
stage = sys.argv[sys.argv.index('--stage') + 1]
payload = json.load(sys.stdin)
with open(os.environ[%r], 'a', encoding='utf-8') as handle:
    handle.write(json.dumps({'stage': stage, 'payload': payload}) + '\\n')
answers = {'prepare': {'status': 'prepared'}, 'inject': {'additionalContext': %r}}
print(json.dumps(answers.get(stage, {'status': stage})))
''' % (RECORD, MARKER)

PROGRAM = ("import { CrewloomLifecycle } from './plugin.mjs';\n"
           'const hooks = await CrewloomLifecycle({directory: process.cwd(), worktree: process.cwd()});\n'
           "await hooks['chat.message']({sessionID: 's'}, {message: {id: 'msg_turn', sessionID: 's'}});\n")

READBACK = ('const original = output.system;\n'
            "await hooks['experimental.chat.system.transform']({sessionID: 's'}, output);\n"
            "console.log(JSON.stringify({same: original === output.system,"
            ' length: original.length, entries: original}));\n')


@unittest.skipUnless(shutil.which('node'), 'Node is required to exercise the real plugin callbacks')
class OpenCodeSystemInPlace(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        bridge = self.project / 'bridge.py'
        bridge.write_text(BRIDGE, encoding='utf-8')
        source = (ROOT / TEMPLATE).read_text(encoding='utf-8')
        substitutions = {'__CREWLOOM_BRIDGE_ARGV__': json.dumps([sys.executable, str(bridge)]),
                         '__CREWLOOM_ROOT__': json.dumps(str(self.project)),
                         '__CREWLOOM_PROJECT_ID__': json.dumps('opencode-inplace'),
                         '__CREWLOOM_CONFIG_SHA__': json.dumps('c' * 64)}
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
        return [json.loads(line)['stage'] for line in lines]

    def inject(self, literal):
        result = self.node('const output = %s;\n' % literal + READBACK)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def assert_refused(self, literal):
        result = self.node('const output = %s;\n'
                           "await hooks['experimental.chat.system.transform']({sessionID: 's'}, output);" % literal)
        self.assertNotEqual(result.returncode, 0,
                            'A host without its own system array was handed a detached one: ' + result.stdout)
        self.assertIn('system prompt array', result.stderr)

    def test_the_injected_context_lands_in_the_array_the_host_already_owns(self):
        readback = self.inject('{system: []}')
        self.assertTrue(readback['same'], 'The host array was replaced instead of filled')
        self.assertEqual(readback['length'], 1)
        self.assertEqual(readback['entries'], [MARKER])

    def test_the_context_the_host_already_wrote_stays_ahead_of_the_injected_one(self):
        readback = self.inject("{system: ['host rule one', 'host rule two']}")
        self.assertTrue(readback['same'], 'The host array was replaced instead of filled')
        self.assertEqual(readback['length'], 3)
        self.assertEqual(readback['entries'], ['host rule one', 'host rule two', MARKER])

    def test_a_second_turn_appends_to_the_same_host_array_instead_of_replacing_it(self):
        result = self.node("const output = {system: ['host rule']};\n"
                           'const original = output.system;\n'
                           "await hooks['experimental.chat.system.transform']({sessionID: 's'}, output);\n"
                           "await hooks['experimental.chat.system.transform']({sessionID: 's'}, output);\n"
                           "console.log(JSON.stringify({same: original === output.system, entries: original}));")
        self.assertEqual(result.returncode, 0, result.stderr)
        readback = json.loads(result.stdout)
        self.assertTrue(readback['same'], 'The host array was replaced instead of filled')
        self.assertEqual(readback['entries'], ['host rule', MARKER, MARKER])

    def test_a_host_that_handed_over_no_system_array_is_refused(self):
        self.assert_refused('{}')
        self.assert_refused('{system: undefined}')
        self.assert_refused('{system: null}')

    def test_a_system_value_that_is_not_an_array_is_refused(self):
        self.assert_refused("{system: 'host text'}")
        self.assert_refused('{system: {0: %s}}' % json.dumps(MARKER))
        self.assert_refused('{system: 42}')

    def test_the_context_is_produced_once_per_injected_turn(self):
        self.inject('{system: []}')
        self.assertEqual(self.stages(), ['prepare', 'inject'])

    def test_the_adapter_never_reassigns_the_host_system_array(self):
        source = (ROOT / TEMPLATE).read_text(encoding='utf-8')
        for reassignment in ('output.system =', 'output["system"] =', "output['system'] ="):
            self.assertNotIn(reassignment, source,
                             'The adapter rebuilt the host system array instead of filling it: '
                             + reassignment)


if __name__ == '__main__':
    unittest.main()