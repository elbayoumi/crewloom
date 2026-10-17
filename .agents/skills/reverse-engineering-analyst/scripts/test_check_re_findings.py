"""Findings packet bookkeeping regressions."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_re_findings as checker

EXAMPLE = json.loads((HERE.parents[3] / 'examples' / 're' / 'findings.json').read_text(encoding='utf-8'))


class FindingsPacket(unittest.TestCase):
    def mutated(self, change):
        packet = copy.deepcopy(EXAMPLE)
        change(packet)
        return checker.check(packet)

    def test_published_example_passes(self):
        self.assertEqual(checker.check(EXAMPLE), [])

    def test_missing_authorization_rejected(self):
        errors = self.mutated(lambda p: p['target'].update(authorization='  '))
        self.assertTrue(any('authorization' in e for e in errors))

    def test_bad_hash_rejected(self):
        for value in ('abc', 'G' * 64, 'A' * 64, None):
            with self.subTest(value=value):
                errors = self.mutated(lambda p: p['target'].update(sha256=value))
                self.assertTrue(any('sha256' in e for e in errors))

    def test_observation_without_evidence_rejected(self):
        errors = self.mutated(lambda p: p['findings'][0].update(evidence_ids=[]))
        self.assertTrue(any('must cite evidence' in e for e in errors))

    def test_dangling_evidence_rejected(self):
        errors = self.mutated(lambda p: p['findings'][0].update(evidence_ids=['missing']))
        self.assertTrue(any("unknown evidence id 'missing'" in e for e in errors))

    def test_inference_and_unknown_need_limitations(self):
        errors = self.mutated(lambda p: [p['findings'][2].pop('limitations'), p['findings'][3].pop('limitations')])
        self.assertEqual(len([e for e in errors if 'limitations' in e]), 2)

    def test_unknown_kind_and_duplicates_rejected(self):
        errors = self.mutated(lambda p: [p['findings'][0].update(kind='fact'), p['findings'][1].update(id='f-1')])
        self.assertTrue(any('kind must be one of' in e for e in errors))
        self.assertTrue(any('duplicate finding id' in e for e in errors))

    def test_embedded_secret_rejected(self):
        errors = self.mutated(lambda p: p['findings'][0].update(claim='key ghp_abcdefghijklmnopqrstuvwxyz0123456789'))
        self.assertTrue(any('embedded secret' in e for e in errors))

    def test_non_object_and_malformed_shapes_do_not_raise(self):
        self.assertEqual(checker.check([]), ['top-level JSON must be an object'])
        for broken in ({}, {'target': 1, 'evidence': 'x', 'findings': 'y'}, {'findings': [1], 'evidence': [None]}):
            with self.subTest(broken=broken):
                self.assertTrue(checker.check(broken))

    def test_cli_exit_codes(self):
        script = str(HERE / 'check_re_findings.py')
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / 'good.json'
            good.write_text(json.dumps(EXAMPLE))
            bad = Path(folder) / 'bad.json'
            bad.write_text(json.dumps({}))
            broken = Path(folder) / 'broken.json'
            broken.write_text('{')
            codes = [subprocess.run([sys.executable, script, '--findings', str(p)], capture_output=True, text=True)
                     for p in (good, bad, broken)]
        self.assertEqual([c.returncode for c in codes], [0, 2, 1])
        self.assertNotIn('Traceback', ''.join(c.stderr for c in codes))


if __name__ == '__main__':
    unittest.main()
