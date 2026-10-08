"""Only OpenCode is bound by the argv budget; Codex and Claude read the prompt on stdin."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_host as h


class Reached(Exception):
    """Raised in place of launching a process, proving the prompt was accepted."""


class PromptBudget(unittest.TestCase):
    def attempt(self, host):
        oversized = 'x' * (h.MAX_ARGV_TEXT + 100)
        info = {'executable': '/bin/true', 'version': 'v', 'host': host}
        with patch.object(h, 'probe', return_value=info), \
                patch.object(h.subprocess, 'Popen', side_effect=Reached):
            h.generate(host, oversized, ['a.py'], 5, None)

    def test_stdin_hosts_still_accept_a_prompt_larger_than_the_argv_budget(self):
        for host in ('codex', 'claude'):
            with self.subTest(host=host), self.assertRaises(Reached):
                self.attempt(host)

    def test_opencode_refuses_the_same_prompt_before_any_launch(self):
        with self.assertRaises(ValueError) as raised:
            self.attempt('opencode')
        self.assertIn('argv', str(raised.exception))


class EffectiveBound(unittest.TestCase):
    """The capability profile, the preflight and the adapter agree on the transport actually used (W03)."""
    BOUNDS = {'opencode': h.MAX_ARGV_TEXT, 'codex': h.MAX_TEXT, 'claude': h.MAX_TEXT,
              'openai': h.MAX_TEXT, 'anthropic': h.MAX_TEXT}

    def test_each_host_advertises_its_own_documented_bound_and_transport(self):
        for host, bound in self.BOUNDS.items():
            with self.subTest(host=host):
                fact = h.capability_profile(host)['limits']['input_bytes']
                self.assertEqual((fact['value'], fact['basis']), (bound, 'documented'))
                self.assertIn(h.INPUT_TRANSPORT[host], fact['source'])
                self.assertEqual(h.input_bound(host), bound)
        self.assertEqual(h.MAX_ARGV_TEXT, 131072)
        self.assertEqual(h.MAX_TEXT, 262144)
        self.assertIsNone(h.capability_profile('opencode')['limits']['context_window_tokens']['value'],
                          'a context window is never guessed')
        with self.assertRaises(ValueError):
            h.input_bound('nope')

    def test_preflight_uses_the_selected_hosts_exact_bound(self):
        opencode, codex = h.capability_profile('opencode'), h.capability_profile('codex')
        self.assertEqual(h.check_prompt_fits(opencode, h.MAX_ARGV_TEXT), h.MAX_ARGV_TEXT)
        with self.assertRaisesRegex(ValueError, 'exceeds the 131072 byte bound'):
            h.check_prompt_fits(opencode, h.MAX_ARGV_TEXT + 1)
        with self.assertRaisesRegex(ValueError, 'exceeds the 131072 byte bound'):
            h.check_prompt_fits(opencode, 153600)
        self.assertEqual(h.check_prompt_fits(codex, 153600), h.MAX_TEXT)
        self.assertEqual(h.check_prompt_fits(codex, h.MAX_TEXT), h.MAX_TEXT)
        with self.assertRaisesRegex(ValueError, 'exceeds the 262144 byte bound'):
            h.check_prompt_fits(codex, h.MAX_TEXT + 1)

    def reached(self, host, prompt):
        info = {'executable': '/bin/true', 'version': 'v', 'host': host}
        with patch.object(h, 'probe', return_value=info) as probe, \
                patch.object(h.subprocess, 'Popen', side_effect=Reached) as popen:
            try:
                h.generate(host, prompt, ['a.py'], 5, None)
            except Reached:
                return True, probe.called
            except ValueError as exc:
                self.assertFalse(probe.called, 'refused before the host was even probed')
                self.assertFalse(popen.called)
                self.assertIn(str(h.input_bound(host)), str(exc))
                return False, probe.called

    def test_exact_bound_and_one_byte_over_for_the_adapter_in_bytes_not_characters(self):
        for host in ('opencode', 'codex'):
            bound = h.input_bound(host)
            with self.subTest(host=host):
                self.assertEqual(self.reached(host, 'x' * bound), (True, True))
                self.assertEqual(self.reached(host, 'x' * (bound + 1)), (False, False))
        # two-, three- and four-byte characters: the count is the UTF-8 length
        self.assertEqual(self.reached('opencode', '\u00e9' * (h.MAX_ARGV_TEXT // 2)), (True, True))
        self.assertEqual(self.reached('opencode', '\u00e9' * (h.MAX_ARGV_TEXT // 2) + 'x'), (False, False))
        self.assertEqual(self.reached('opencode', '\U0001F600' * (h.MAX_ARGV_TEXT // 4)), (True, True))
        self.assertEqual(self.reached('opencode', '\U0001F600' * (h.MAX_ARGV_TEXT // 4 + 1)), (False, False))
        self.assertEqual(self.reached('opencode', '\u20ac' * (h.MAX_ARGV_TEXT // 3 + 1)), (False, False),
                         'fewer characters than the bound, more bytes than it')
        self.assertEqual(self.reached('codex', '\u20ac' * (h.MAX_ARGV_TEXT // 3 + 1)), (True, True),
                         'a stdin host keeps its own, larger bound')


if __name__ == '__main__':
    unittest.main()
