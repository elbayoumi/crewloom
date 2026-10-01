"""Trial collection must preserve frozen evidence and anonymize scorer inputs."""
import json
from pathlib import Path
import tempfile
import sys
import crewloom
import unittest
from unittest.mock import patch
import evaluate_hosts as e


class TrialTests(unittest.TestCase):
    def test_trial_matrix_reproducible_and_balanced(self):
        order=e.trial_order(['codex','claude'],5,10)
        self.assertEqual(order,e.trial_order(['codex','claude'],5,10));self.assertEqual(len(order),20)
        for host in ('codex','claude'):
            for condition in ('with-role','without-role'):
                self.assertEqual(sum(x['host']==host and x['condition']==condition for x in order),5)

    def test_invalid_matrix_rejected(self):
        for hosts,repeats in (([],5),(['codex','codex'],5),(['unknown'],5),(['codex'],0)):
            with self.assertRaises(ValueError):e.trial_order(hosts,repeats,1)

    def test_frozen_protocol_precedes_generation_and_scorer_has_no_labels(self):
        with tempfile.TemporaryDirectory() as t:
            destination=Path(t)/'evidence'
            def generate(*args):
                self.assertTrue((destination/'protocol.json').is_file())
                return {'src/slug.py':'def slugify(v): return str(v)'},{'host':args[0]}
            def grade(project,image,repeats):
                self.assertEqual(sorted(p.name for p in project.iterdir()),['src'])
                return {'source_sha256':'abc','mean_pass_rate':1,'runs':[]}
            with patch.object(e.w,'inspect_image',return_value='sha256:test'),patch.object(e.host,'generate',side_effect=generate),patch.object(e.grader,'evaluate',side_effect=grade):
                report=e.collect(destination,['codex','claude'],1)
            self.assertTrue(report['cross_host_complete']);self.assertEqual(len(report['results']),4)

    def test_host_failure_budget_skips_remaining_calls(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(e.w,'inspect_image',return_value='sha256:test'),patch.object(e.host,'generate',side_effect=ValueError('auth missing')) as generate:
                report=e.collect(Path(t)/'evidence',['claude'],5)
            self.assertEqual(len(json.loads((Path(t)/'evidence/results.json').read_text())),10)
            self.assertEqual(len(json.loads((Path(t)/'evidence/mapping.json').read_text())),10)
            self.assertEqual(generate.call_count,2);self.assertFalse(report['cross_host_complete'])
            self.assertEqual(report['groups'][0]['mean_pass_rate'],None)
            self.assertEqual(sum(x['status']=='blocked' for x in report['results']),8)

    def test_public_cli_forwards_provider_trial_flags(self):
        argv=['crewloom','evaluate-hosts','--output','fresh-evidence','--host','codex','--repeats','2','--codex-model','configured-model']
        with patch.object(sys,'argv',argv),patch.object(e,'main',return_value=0) as execute:
            self.assertEqual(crewloom.main(),0)
        forwarded=execute.call_args.args[0]
        self.assertEqual(forwarded[forwarded.index('--host')+1],'codex')
        self.assertEqual(forwarded[forwarded.index('--repeats')+1],'2')
        self.assertEqual(forwarded[forwarded.index('--codex-model')+1],'configured-model')

    def test_existing_evidence_never_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaisesRegex(ValueError,'fresh'):e.collect(Path(t),['codex'])


if __name__=='__main__':unittest.main()
