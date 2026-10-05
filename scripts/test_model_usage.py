"""Provider usage semantics and the bounded OpenCode adapter; no provider calls.

The frozen parent transport cases live in
`.crewloom/production-foundation/test_transport_acceptance_boundaries.py` and are
read-only for this task. These cases are this repository's own suite: they reuse
the recorded 1.18.32 event shape, keep the same refusals, and pin the environment
and profile facts the adapter depends on.
"""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import model_host as h

LIB = Path(__file__).resolve().parent
RECORDED = Path(h.__file__).resolve().parents[1] / '.crewloom/production-foundation/opencode-schema-probe/raw-events.jsonl'
ARTIFACT = {'artifacts': [{'path': 'src/result.py', 'content': 'VALUE = 1\n'}]}
FIXTURE_TOKENS = {'total': 151, 'input': 100, 'output': 11, 'reasoning': 3,
                  'cache': {'read': 35, 'write': 2}}
# The actual step_finish tokens and cost recorded by the 2026-10-04 native probe.
LIVE_TOKENS = {'total': 450, 'input': 253, 'output': 21, 'reasoning': 38,
               'cache': {'write': 0, 'read': 138}}


def stream(*events):
    return '\n'.join(json.dumps(event) for event in events)


def text(value=ARTIFACT):
    return {'type': 'text', 'part': {'text': json.dumps(value)}}


def finish(tokens=FIXTURE_TOKENS, cost=0, reason='stop'):
    part = {'reason': reason}
    if tokens is not None:
        part['tokens'] = tokens
    if cost is not None:
        part['cost'] = cost
    return {'type': 'step_finish', 'part': part}


class UsageMetricTests(unittest.TestCase):
    """Normalized counts are integers or unknown, never plausible guesses."""

    def metrics(self, host, usage):
        value = h.usage_metrics(host, usage)
        self.assertEqual(set(value), set(h.USAGE_KEYS))
        for key, item in value.items():
            self.assertTrue(item is None or (isinstance(item, int) and not isinstance(item, bool)), key)
        return value

    def test_opencode_cache_is_separate_from_input(self):
        value = self.metrics('opencode', FIXTURE_TOKENS)
        self.assertEqual(value, {'input_tokens': 137, 'uncached_input_tokens': 100,
                                 'cached_input_tokens': 35, 'cache_write_tokens': 2,
                                 'output_tokens': 11, 'reasoning_tokens': 3, 'total_tokens': 151})
        self.assertEqual(value['input_tokens'] + value['output_tokens'] + value['reasoning_tokens'],
                         value['total_tokens'])

    def test_recorded_live_probe_tokens_decode_without_invention(self):
        value = self.metrics('opencode', LIVE_TOKENS)
        self.assertEqual((value['input_tokens'], value['uncached_input_tokens'],
                          value['cached_input_tokens'], value['cache_write_tokens'],
                          value['output_tokens'], value['reasoning_tokens'], value['total_tokens']),
                         (391, 253, 138, 0, 21, 38, 450))

    def test_reported_total_is_kept_even_when_components_do_not_add_up(self):
        value = self.metrics('opencode', {'total': 99, 'input': 10, 'output': 1,
                                          'reasoning': 0, 'cache': {'read': 0, 'write': 0}})
        self.assertEqual(value['total_tokens'], 99)

    def test_codex_cached_input_is_a_subset_and_is_never_added_again(self):
        value = self.metrics('codex', {'input_tokens': 100, 'cached_input_tokens': 40,
                                       'output_tokens': 11})
        self.assertEqual((value['input_tokens'], value['uncached_input_tokens'],
                          value['cached_input_tokens'], value['output_tokens']),
                         (100, 60, 40, 11))
        self.assertIsNone(value['cache_write_tokens'])
        self.assertIsNone(value['reasoning_tokens'])

    def test_missing_partial_fields_stay_unknown(self):
        opencode = self.metrics('opencode', {'input': 100, 'output': 11})
        self.assertIsNone(opencode['input_tokens'])
        self.assertIsNone(opencode['cached_input_tokens'])
        self.assertIsNone(opencode['total_tokens'])
        codex = self.metrics('codex', {'input_tokens': 100, 'output_tokens': 11})
        self.assertIsNone(codex['cached_input_tokens'])
        self.assertIsNone(codex['uncached_input_tokens'])

    def test_absent_usage_is_not_zero(self):
        empty = self.metrics('opencode', {'steps': []})
        self.assertTrue(all(item is None for item in empty.values()))

    def test_every_observed_model_step_contributes(self):
        value = self.metrics('opencode', {'steps': [FIXTURE_TOKENS, FIXTURE_TOKENS]})
        self.assertEqual((value['input_tokens'], value['total_tokens']), (274, 302))

    def test_invalid_reported_counts_are_refused(self):
        bad = [('input_tokens', -1), ('input_tokens', True), ('output_tokens', 1.5),
               ('cached_input_tokens', float('nan')), ('output_tokens', '11'),
               ('total_tokens', float('inf'))]
        for key, value in bad:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    h.usage_metrics('codex', dict(FIXTURE_KEYS, **{key: value}))
        for key, value in (('input', -1), ('input', True), ('output', 1.5), ('total', float('nan'))):
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    h.usage_metrics('opencode', dict(FIXTURE_TOKENS, **{key: value}))
        with self.assertRaises(ValueError):
            h.usage_metrics('opencode', {'cache': 3})
        with self.assertRaises(ValueError):
            h.usage_metrics('opencode', 'tokens')
        with self.assertRaisesRegex(ValueError, 'codex and opencode'):
            h.usage_metrics('claude', {})

    def test_cost_zero_is_preserved_and_absent_stays_null(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            _, usage, cost = h.parse_opencode(stream(text(), finish()), scratch)
        self.assertEqual(cost, 0)
        self.assertEqual(usage['cost_reported'], True)
        with tempfile.TemporaryDirectory() as folder:
            _, _, cost = h.parse_opencode(stream(text(), finish(tokens=None, cost=None)), Path(folder))
        self.assertIsNone(cost)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                h.parse_opencode(stream(text(), finish(cost=-1)), Path(folder))
            with self.assertRaises(ValueError):
                h.parse_opencode(stream(text(), finish(cost='free')), Path(folder))


FIXTURE_KEYS = {'input_tokens': 100, 'cached_input_tokens': 40, 'output_tokens': 11}


class OpenCodeTransportTests(unittest.TestCase):
    """A tool-free run is the only accepted OpenCode transport."""

    def decode(self, raw):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            (scratch / 'response.json').write_text(json.dumps(ARTIFACT))
            return h.parse_response('opencode', raw, scratch)

    def test_artifact_and_normalized_usage_come_from_one_completed_step(self):
        value, usage, cost = self.decode(stream(text(), finish()))
        self.assertEqual(value, ARTIFACT)
        self.assertEqual(cost, 0)
        self.assertEqual(usage['observed_model_steps'], 1)
        self.assertEqual(h.usage_metrics('opencode', usage)['input_tokens'], 137)

    def test_commentary_may_precede_one_final_structured_response(self):
        value, usage, _ = self.decode(stream({'type': 'text', 'part': {'text': 'Preparing the summary'}},
                                             finish(), text(), finish()))
        self.assertEqual(value, ARTIFACT)
        self.assertEqual(h.usage_metrics('opencode', usage)['total_tokens'], 302)

    def test_tool_error_failed_incomplete_and_ambiguous_runs_are_refused(self):
        streams = (
            stream({'type': 'tool_use', 'part': {'tool': 'bash'}}, text(), finish()),
            stream({'type': 'tool_use', 'part': {'type': 'tool', 'tool': 'bash'}}, text(), finish()),
            stream(text(), finish(reason='tool-calls')),
            stream(text(), finish(reason='length')),
            stream(text()),
            stream(text(), finish(), {'type': 'error', 'error': {'message': 'failed'}}),
            stream(text(), finish(), {'type': 'tool_use', 'part': {'type': 'tool'}}),
            stream(text(), text(), finish()),
            stream(text(), finish()) + '\nnot-json',
            stream({'type': 'text', 'part': {'text': '{"artifacts": ['}}, finish()),
            stream({'type': 'message', 'part': {}}, finish()),
            '',
        )
        for raw in streams:
            with self.subTest(raw=raw[:70]):
                with self.assertRaises(ValueError):
                    self.decode(raw)

    def test_a_fenced_or_prose_answer_is_not_treated_as_an_artifact(self):
        for body in ('```json\n{"artifacts": []}\n```', 'Here you go: {"artifacts": []}'):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    self.decode(stream({'type': 'text', 'part': {'text': body}}, finish()))

    def test_reported_model_is_observed_or_null_and_never_the_request(self):
        _, usage, _ = self.decode(stream(text(), finish()))
        self.assertIsNone(usage['model_reported'])
        observed = {'type': 'step_finish', 'part': {'reason': 'stop', 'model': 'opencode/space-bunny-free',
                                                    'tokens': FIXTURE_TOKENS, 'cost': 0}}
        _, usage, _ = self.decode(stream(text(), observed))
        self.assertEqual(usage['model_reported'], 'opencode/space-bunny-free')

    def test_codex_usage_sums_every_observed_turn(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            (scratch / 'response.json').write_text(json.dumps(ARTIFACT))
            raw = stream({'type': 'turn.completed', 'usage': {'input_tokens': 10, 'cached_input_tokens': 4}},
                         {'type': 'turn.completed', 'usage': {'input_tokens': 5, 'cached_input_tokens': 1}})
            value, usage, cost = h.parse_response('codex', raw, scratch)
        self.assertEqual(value, ARTIFACT)
        self.assertIsNone(cost)
        self.assertEqual(h.usage_metrics('codex', usage)['uncached_input_tokens'], 10)
        self.assertEqual(usage['observed_model_steps'], 2)

    def test_codex_structured_usage_details_are_retained_not_summed(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            (scratch / 'response.json').write_text(json.dumps(ARTIFACT))
            raw = stream({'type': 'turn.completed',
                          'usage': {'input_tokens': 10, 'details': {'cached': 3}}})
            _, usage, _ = h.parse_response('codex', raw, scratch)
        self.assertEqual(usage['details'], {'cached': 3})
        with self.assertRaises(ValueError):
            with tempfile.TemporaryDirectory() as folder:
                scratch = Path(folder)
                (scratch / 'response.json').write_text(json.dumps(ARTIFACT))
                h.parse_response('codex', stream({'type': 'turn.completed',
                                                  'usage': {'input_tokens': 1.5}}), scratch)

    @unittest.skipUnless(RECORDED.is_file(), 'Recorded native probe stream is not present')
    def test_recorded_native_probe_stream_is_decoded_to_its_actual_numbers(self):
        # The recorded run answered a bare marker, not an artifact, so the transport
        # refuses it. Its recorded step_finish tokens still have to decode exactly.
        raw = RECORDED.read_text(encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'structured artifact'):
            h.parse_opencode(raw, Path(tempfile.gettempdir()))
        recorded = [json.loads(line) for line in raw.splitlines() if line.strip()]
        parts = [event['part'] for event in recorded if event['type'] == 'step_finish']
        self.assertEqual([part['reason'] for part in parts], ['stop'])
        self.assertEqual([part['cost'] for part in parts], [0])
        self.assertIsNone([event for event in recorded if event['type'] == 'step_start'][0]['part'].get('model'))
        self.assertEqual(h.usage_metrics('opencode', {'steps': [part['tokens'] for part in parts]}),
                         {'input_tokens': 391, 'uncached_input_tokens': 253,
                          'cached_input_tokens': 138, 'cache_write_tokens': 0,
                          'output_tokens': 21, 'reasoning_tokens': 38, 'total_tokens': 450})


class OpenCodeIsolationTests(unittest.TestCase):
    """Fresh scratch, deny-all profile, task-scoped configuration, no global edits."""

    def test_deny_all_profile_disables_every_tool_and_the_skill_tool(self):
        profile = h.opencode_agent_config('opencode/space-bunny-free')
        self.assertEqual(profile['permission'], {'*': 'deny'})
        self.assertEqual(profile['tools'], {'*': False, 'skill': False})
        agent = profile['agent'][h.OPENCODE_AGENT]
        self.assertEqual(agent['permission'], {'*': 'deny'})
        self.assertEqual(agent['tools'], {'*': False, 'skill': False})
        self.assertEqual(agent['model'], 'opencode/space-bunny-free')
        self.assertEqual(profile['model'], 'opencode/space-bunny-free')

    def test_task_scoped_configuration_never_moves_home_or_codex_home(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            env = h.opencode_environment(scratch, scratch / 'opencode.json')
            self.assertTrue((scratch / 'xdg-configuration').is_dir())
        self.assertEqual(Path(env['XDG_CONFIG_HOME']), Path(folder) / 'xdg-configuration')
        self.assertEqual(env['OPENCODE_CONFIG'], str(Path(folder) / 'opencode.json'))
        self.assertNotIn('HOME', env)
        self.assertNotIn('CODEX_HOME', env)
        self.assertNotIn('ANTHROPIC_API_KEY', env)
        self.assertEqual(set(env) - {'XDG_CONFIG_HOME', 'OPENCODE_CONFIG'}, set(h.OPENCODE_DISABLE_SWITCHES))

    def test_command_uses_pure_and_a_deny_all_agent_in_fresh_scratch(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            argv = h.command('opencode', 'opencode', scratch, 'opencode/space-bunny-free', 'prompt text')
            profile = json.loads((scratch / 'opencode.json').read_text())
        self.assertEqual(argv[:2], ['opencode', 'run'])
        self.assertIn('--pure', argv)
        self.assertEqual(argv[argv.index('--agent') + 1], h.OPENCODE_AGENT)
        self.assertEqual(argv[argv.index('--model') + 1], 'opencode/space-bunny-free')
        self.assertEqual(argv[argv.index('--format') + 1], 'json')
        self.assertEqual(argv[argv.index('--dir') + 1], str(scratch))
        self.assertEqual(argv[-1], 'prompt text')
        self.assertNotIn('--auto', argv)
        self.assertNotIn('--ignore-user-config', argv)
        self.assertEqual(profile['permission'], {'*': 'deny'})

    def test_argv_prompt_budget_is_refused_rather_than_truncated(self):
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            with self.assertRaisesRegex(ValueError, 'argv budget'):
                h.command('opencode', 'opencode', scratch, None, 'x' * (h.MAX_ARGV_TEXT + 1))

    def test_probe_requires_the_pure_and_agent_flags_on_the_actual_binary(self):
        fake = ('#!/bin/sh\n'
                'case "$1 $2" in\n'
                '  "run --help") echo "Usage: opencode run --pure --model --agent --format --dir";;\n'
                '  "--version ") echo "1.18.32";;\n'
                '  *) exit 1;;\n'
                'esac\n')
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'opencode'
            binary.write_text(fake)
            binary.chmod(0o755)
            with patch.object(h.shutil, 'which', return_value=str(binary)):
                info = h.probe('opencode')
                self.assertEqual(info['version'], '1.18.32')
                self.assertIn('OPENCODE_DISABLE_EXTERNAL_SKILLS', info['disable_switches'])
            binary.write_text(fake.replace('--pure', '--plugins'))
            with patch.object(h.shutil, 'which', return_value=str(binary)):
                with self.assertRaises(h.HostUnavailable):
                    h.probe('opencode')
            with patch.object(h.shutil, 'which', return_value=None):
                with self.assertRaises(h.HostUnavailable):
                    h.probe('opencode')

    def test_codex_bounded_flags_and_disabled_features_are_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            argv = h.command('codex', 'codex', Path(folder))
        for feature in ('shell_tool', 'code_mode', 'code_mode_host', 'plugins', 'hooks',
                        'apps', 'multi_agent', 'browser_use', 'computer_use'):
            self.assertIn('features.' + feature + '=false', argv)
        self.assertIn('features.skip_host_skill_discovery=true', argv)
        self.assertIn('--ignore-user-config', argv)
        self.assertEqual(argv[argv.index('--sandbox') + 1], 'read-only')

    def test_child_environment_is_task_scoped_and_reports_no_credential(self):
        code = ('import json,os\n'
                'observed={"home":os.environ.get("HOME"),"codex_home":os.environ.get("CODEX_HOME"),'
                '"xdg":os.environ.get("XDG_CONFIG_HOME"),"pure":os.environ.get("OPENCODE_DISABLE_EXTERNAL_SKILLS"),'
                '"leaked":os.environ.get("CREWLOOM_PRIVATE_TEST")}\n'
                'artifact={"artifacts":[{"path":"a","content":json.dumps(observed)}]}\n'
                'print(json.dumps({"type":"text","part":{"text":json.dumps(artifact)}}))\n'
                'print(json.dumps({"type":"step_finish","part":{"reason":"stop",'
                '"tokens":' + json.dumps(FIXTURE_TOKENS) + ',"cost":0}}))\n')
        argv = [sys.executable, '-c', code]
        with patch.object(h, 'probe', return_value={'executable': sys.executable,
                                                    'version': 'synthetic-fixture'}), \
                patch.object(h, 'command', return_value=argv), \
                patch.dict(os.environ, {'CREWLOOM_PRIVATE_TEST': 'should-not-forward'}):
            artifacts, evidence = h.generate('opencode', 'study prompt', ['a'], 30,
                                             'opencode/space-bunny-free')
        observed = json.loads(artifacts['a'])
        self.assertIsNone(observed['leaked'])
        self.assertEqual(observed['home'], os.environ.get('HOME'))
        self.assertEqual(observed['codex_home'], os.environ.get('CODEX_HOME'))
        self.assertEqual(observed['pure'], '1')
        self.assertEqual(Path(observed['xdg']).name, 'xdg-configuration')
        self.assertEqual(evidence['model_requested'], 'opencode/space-bunny-free')
        self.assertIsNone(evidence['model_reported'])
        self.assertEqual(evidence['usage_metrics']['input_tokens'], 137)
        self.assertEqual(evidence['cost_usd'], 0)
        self.assertEqual(evidence['prompt_bytes'], len('study prompt'))
        self.assertTrue(evidence['native_host_exception'])
        self.assertIn('not an OS sandbox', evidence['execution_boundary'])


class GrammarCompatibilityTests(unittest.TestCase):
    """The owned modules and the study fixture must parse as Python 3.9."""

    def test_owned_modules_and_fixture_are_python39_grammar(self):
        targets = [Path(h.__file__), LIB / 'evaluate_hosts.py']
        targets.extend(sorted((Path(h.__file__).resolve().parents[1] /
                               'examples/context-study/project/src').glob('*.py')))
        self.assertGreaterEqual(len(targets), 11)
        for path in targets:
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 9))


if __name__ == '__main__':
    unittest.main()