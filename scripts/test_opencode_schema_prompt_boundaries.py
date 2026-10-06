"""Independent acceptance for telling OpenCode the artifact schema.

Written before the implementation and frozen: the implementer may not edit this file.

Evidence from the frozen study of 2026-10-05: all 14 OpenCode generations that finished but were
refused had invented their own response shape (13 flat `{"src/x.py": "..."}` maps and one
`{"files": ...}`), because `opencode run` has no schema option and the prompt only said "matching
the schema" without stating it. Codex and Claude receive the schema through a CLI flag.

These cases pin the fix without loosening the contract: the schema is stated in OpenCode's agent
system prompt (the task-scoped profile file), deterministically and with the declared output paths,
while the user message stays the study prompt byte for byte and exactly once in argv; other hosts
are untouched, and every invented shape is still refused.

Every case is offline: a real POSIX shell script stands in for the `opencode` executable and answers
like a model that follows the schema only if the prompt actually states it.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_host as h

FLAGS = ' '.join(h.OPENCODE_REQUIRED_FLAGS)


def event(kind, part):
    return json.dumps({'type': kind, 'timestamp': 1, 'sessionID': 's', 'part': part})


def stream(text):
    return '\n'.join([
        event('step_start', {'type': 'step-start'}),
        event('text', {'type': 'text', 'text': text}),
        event('step_finish', {'type': 'step-finish', 'reason': 'stop', 'cost': 0,
                              'tokens': {'total': 10, 'input': 4, 'output': 6, 'reasoning': 0,
                                         'cache': {'write': 0, 'read': 0}}}),
    ])


def model_that_follows_the_schema(outputs):
    """What a compliant model answers, and what the failed generations answered instead."""
    good = {'artifacts': [{'path': path, 'content': 'print(1)\n'} for path in outputs]}
    invented = {path: 'print(1)\n' for path in outputs}
    return json.dumps(good), json.dumps(invented)


def write_fake_opencode(folder, record, good, invented):
    """A real executable: probe answers, and `run` records its prompt and answers by what it saw."""
    good_file = Path(folder) / 'good.jsonl'
    bad_file = Path(folder) / 'bad.jsonl'
    good_file.write_text(stream(good) + '\n')
    bad_file.write_text(stream(invented) + '\n')
    script = '\n'.join([
        '#!/bin/sh',
        'if [ "$1" = "--version" ]; then echo 1.18.32; exit 0; fi',
        'if [ "$1" = "run" ] && [ "$2" = "--help" ]; then echo "%s" 1>&2; exit 0; fi' % FLAGS,
        'for last; do :; done',
        'printf "%%s" "$last" > "%s"' % record,
        # A model only follows a schema it was shown: it needs the wrapper key and the content key,
        # which reach it through the agent profile the executable is pointed at.
        'if grep -q artifacts "$OPENCODE_CONFIG" && grep -q content "$OPENCODE_CONFIG"; then cat "%s"; else cat "%s"; fi' % (good_file, bad_file),
        'exit 0', ''])
    binary = Path(folder) / 'opencode'
    binary.write_text(script)
    binary.chmod(0o755)
    return binary


class Instruction(unittest.TestCase):
    def test_it_states_the_exact_shape_and_every_declared_path_in_order(self):
        text = h.opencode_schema_instruction(['src/a.py', 'src/b.py'])
        for needle in ('"artifacts"', '"path"', '"content"', 'src/a.py', 'src/b.py'):
            self.assertIn(needle, text)
        self.assertLess(text.index('src/a.py'), text.index('src/b.py'))
        self.assertLess(len(text.encode()), 2048)

    def test_it_is_deterministic_and_changes_only_with_the_declared_paths(self):
        self.assertEqual(h.opencode_schema_instruction(['src/a.py']),
                         h.opencode_schema_instruction(['src/a.py']))
        self.assertNotEqual(h.opencode_schema_instruction(['src/a.py']),
                            h.opencode_schema_instruction(['src/b.py']))

    def test_paths_are_json_escaped_so_the_instruction_cannot_be_broken_by_a_path(self):
        path = 'src/we"ird\\name.py'
        self.assertIn(json.dumps(path), h.opencode_schema_instruction([path]))

    def test_invalid_declared_outputs_are_refused(self):
        for bad in ([], ['a', 'a'], [''], [1], 'src/a.py', None, ['a', None]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                h.opencode_schema_instruction(bad)


class AgentProfile(unittest.TestCase):
    BASE = 'Answer with text only. Use no tools and return only the requested JSON artifact.'

    def prompt(self, outputs=None, model='opencode/test-model'):
        profile = h.opencode_agent_config(model, outputs) if outputs is not None else h.opencode_agent_config(model)
        return profile['agent'][h.OPENCODE_AGENT]['prompt']

    def test_without_declared_outputs_the_profile_prompt_is_exactly_what_it_was(self):
        self.assertEqual(self.prompt(), self.BASE)

    def test_with_declared_outputs_the_instruction_is_added_after_the_original_text(self):
        text = self.prompt(['src/a.py', 'src/b.py'])
        self.assertTrue(text.startswith(self.BASE))
        self.assertTrue(text.endswith(h.opencode_schema_instruction(['src/a.py', 'src/b.py'])))

    def test_the_deny_all_profile_is_otherwise_unchanged(self):
        plain = h.opencode_agent_config('opencode/test-model')
        stated = h.opencode_agent_config('opencode/test-model', ['src/a.py'])
        for profile in (plain, stated):
            agent = profile['agent'][h.OPENCODE_AGENT]
            self.assertEqual(profile['permission'], {'*': 'deny'})
            self.assertEqual(profile['tools'], {'*': False, 'skill': False})
            self.assertEqual(agent['permission'], {'*': 'deny'})
            self.assertEqual(agent['tools'], {'*': False, 'skill': False})
            self.assertEqual(agent['model'], 'opencode/test-model')
        self.assertEqual({k: v for k, v in stated['agent'][h.OPENCODE_AGENT].items() if k != 'prompt'},
                         {k: v for k, v in plain['agent'][h.OPENCODE_AGENT].items() if k != 'prompt'})

    def test_invalid_declared_outputs_are_refused_by_the_profile_too(self):
        for bad in ([], ['a', 'a'], [''], 'src/a.py'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                h.opencode_agent_config('opencode/test-model', bad)

    def test_the_command_builder_writes_the_instruction_into_the_profile_it_points_at(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            argv = h.command('opencode', 'fixture-opencode', scratch, 'opencode/test-model',
                             prompt='task prompt', outputs=['src/a.py'])
            profile = json.loads((scratch / 'opencode.json').read_text())
        self.assertIn(h.opencode_schema_instruction(['src/a.py']),
                      profile['agent'][h.OPENCODE_AGENT]['prompt'])
        self.assertEqual(argv.count('task prompt'), 1)

    def test_codex_and_claude_builders_are_unchanged_by_declared_outputs(self):
        for host in ('codex', 'claude'):
            with tempfile.TemporaryDirectory() as folder:
                scratch = Path(folder)
                plain = h.command(host, 'fixture', scratch, None, prompt='p')
                stated = h.command(host, 'fixture', scratch, None, prompt='p', outputs=['src/a.py'])
            self.assertEqual(plain, stated, host)


class EndToEnd(unittest.TestCase):
    def run_generate(self, outputs, prompt='Produce the artifacts.\n{"x":1}', evidence=True):
        folder = tempfile.TemporaryDirectory(prefix='crewloom-opencode-schema-')
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        record = root / 'recorded-prompt'
        good, invented = model_that_follows_the_schema(outputs)
        binary = write_fake_opencode(root, record, good, invented)
        evidence_dir = root / 'evidence' if evidence else None
        with patch.object(h.shutil, 'which', return_value=str(binary)):
            result = h.generate('opencode', prompt, outputs, 30, 'opencode/test-model',
                                evidence=evidence_dir)
        return result, record, evidence_dir

    def test_a_model_that_follows_a_stated_schema_now_produces_accepted_artifacts(self):
        (artifacts, info), record, _ = self.run_generate(['src/a.py'])
        self.assertEqual(artifacts, {'src/a.py': 'print(1)\n'})
        self.assertEqual(info['host'], 'opencode')

    def test_the_process_still_receives_the_study_prompt_exactly_once_and_unchanged(self):
        prompt = 'Produce the artifacts.\n{"x":1}'
        _, record, _ = self.run_generate(['src/a.py', 'src/b.py'], prompt)
        self.assertEqual(record.read_text(), prompt)

    def test_the_retained_evidence_and_byte_count_still_describe_the_study_prompt(self):
        prompt = 'Produce the artifacts.\n{"x":1}'
        (_, info), record, evidence = self.run_generate(['src/a.py'], prompt)
        self.assertEqual((evidence / 'prompt.txt').read_text(encoding='utf-8'), prompt)
        self.assertEqual(info['prompt_bytes'], len(prompt.encode()))

    def test_the_stated_schema_does_not_use_up_the_argv_budget(self):
        prompt = 'x' * (h.MAX_ARGV_TEXT - 10)
        (artifacts, _), record, _ = self.run_generate(['src/a.py'], prompt)
        self.assertEqual(artifacts, {'src/a.py': 'print(1)\n'})
        self.assertEqual(len(record.read_text().encode()), len(prompt.encode()))


class ContractIsNotLoosened(unittest.TestCase):
    def test_every_shape_the_failed_generations_invented_is_still_refused(self):
        invented = [{'src/ledger.py': 'print(1)'},
                    {'files': [{'path': 'src/ledger.py', 'content': 'print(1)'}]},
                    {'artifacts': {'src/ledger.py': 'print(1)'}},
                    {'artifacts': [{'path': 'src/ledger.py', 'content': 'x', 'extra': 1}]},
                    ['src/ledger.py']]
        for value in invented:
            with self.subTest(value=value), self.assertRaises(ValueError):
                h.validate_artifacts(value, ['src/ledger.py'])

    def test_a_model_that_ignores_the_instruction_is_still_refused_end_to_end(self):
        outputs = ['src/a.py']
        folder = tempfile.TemporaryDirectory(prefix='crewloom-opencode-schema-')
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        good, invented = model_that_follows_the_schema(outputs)
        # This stand-in answers the invented shape no matter what it was shown.
        binary = write_fake_opencode(root, root / 'recorded', invented, invented)
        with patch.object(h.shutil, 'which', return_value=str(binary)):
            with self.assertRaises(ValueError):
                h.generate('opencode', 'Produce.\n{}', outputs, 30, 'opencode/test-model')


if __name__ == '__main__':
    unittest.main()
