"""A failed actual generation attempt still has measured wall-clock latency."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import evaluate_hosts

class StudyFailureLatencyBoundaries(unittest.TestCase):
    def test_failed_generation_latency_does_not_remain_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(evaluate_hosts.w,'inspect_image',return_value='sha256:fixture'), \
                 patch.object(evaluate_hosts.host,'generate',side_effect=ValueError('transport rejected fixture')):
                report=evaluate_hosts.collect_study(Path(directory)/'study',['codex','opencode'],repeats=1)
        self.assertEqual(len(report['results']),12)
        self.assertTrue(all(row['status']=='failed' for row in report['results']))
        for row in report['results']:
            self.assertIs(type(row['duration_generation_ms']),int)
            self.assertGreaterEqual(row['duration_generation_ms'],0)
            self.assertIsNone(row['input_tokens'])
            self.assertIsNone(row['cost_usd'])

if __name__=='__main__':unittest.main()
