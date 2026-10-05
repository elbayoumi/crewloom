#!/usr/bin/env python3
"""Run the frozen fixture tests for the reused helpers and record the outcome.

The helper tests ship with the project rather than being generated, so this step is the one
place that proves the reused code still behaves inside the integrated candidate. Each test
module is loaded from its declared file path, because the executor stages declared files and
nothing else.

    python3 tools/run_helper_tests.py
"""
import hashlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

TESTS = ('tests/test_money.py', 'tests/test_scheduling_support.py')
OUT = 'artifacts/helper_tests.json'


def load_suite(relative):
    path = Path(relative)
    spec = importlib.util.spec_from_file_location('helper_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return unittest.defaultTestLoader.loadTestsFromModule(module), hashlib.sha256(
        path.read_bytes()).hexdigest()


def main():
    suite = unittest.TestSuite()
    modules = {}
    for relative in TESTS:
        loaded, digest = load_suite(relative)
        suite.addTests(loaded)
        modules[relative] = digest
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=1).run(suite)
    outcomes = {}
    for test, status in list(result.failures) + list(result.errors):
        outcomes[str(test)] = 'failed: ' + status.strip().splitlines()[-1][:200]
    record = {'tests': modules, 'ran': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped),
              'outcomes': outcomes, 'accepted': result.wasSuccessful()}
    target = Path(OUT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True),
                      encoding='utf-8')
    if not result.wasSuccessful():
        print('helper tests failed: ' + ', '.join(sorted(outcomes)) or 'see the record',
              file=sys.stderr)
        return 1
    print('helper tests passed ' + str(result.testsRun) + ' cases')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())