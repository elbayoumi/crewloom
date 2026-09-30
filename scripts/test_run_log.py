"""Regression coverage for the run log the dashboard reads."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts' / 'crewloom.py'
LOG = ROOT / '.crewloom' / 'runs.jsonl'


def run(env_extra):
    env = {**os.environ, **env_extra}
    return subprocess.run([sys.executable, str(CLI), 'run', 'workflow-contract', '--', 'examples/workflows/valid.json'],
                          capture_output=True, text=True, timeout=30, env=env, cwd=ROOT)


class RunLogTests(unittest.TestCase):
    def lines(self):
        return LOG.read_text(encoding='utf-8').splitlines() if LOG.exists() else []

    def test_cli_run_appends_record(self):
        before = len(self.lines())
        self.assertEqual(run({}).returncode, 0)
        record = json.loads(self.lines()[-1])
        self.assertEqual((len(self.lines()) - before, record['tool'], record['exit_code'], record['source']),
                         (1, 'workflow-contract', 0, 'cli'))

    def test_no_log_env_skips_record(self):
        before = len(self.lines())
        self.assertEqual(run({'CREWLOOM_NO_LOG': '1'}).returncode, 0)
        self.assertEqual(len(self.lines()), before)


if __name__ == '__main__':
    unittest.main()
