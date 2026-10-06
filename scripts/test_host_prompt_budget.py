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


if __name__ == '__main__':
    unittest.main()
