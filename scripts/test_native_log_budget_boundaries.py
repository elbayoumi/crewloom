"""Repeated native callbacks keep bounded metadata rather than duplicate injected source."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import host_lifecycle as lifecycle
import test_native_lifecycle_acceptance_boundaries as fixtures

class NativeLogBudgetBoundaries(unittest.TestCase):
    def root(self):
        case=fixtures.NativeLifecycleBoundaries();case.setUp();self.addCleanup(case.doCleanups)
        case.install();return case.root

    def test_injection_log_does_not_duplicate_complete_context_bodies(self):
        root=self.root();context='PRIVATE_SOURCE_BODY_'+'x'*64000
        for number in range(5):
            event={'stage':'inject','native_event':'UserPromptSubmit','additionalContext':context,
                   'context_bytes':len(context),'context_semantic_sha256':'a'*64,'ordinal':number}
            lifecycle._append_event(root,'codex',event)
        events=lifecycle.observed_events(root,'codex')
        injected=[item for item in events if item.get('stage')=='inject']
        self.assertEqual(len(injected),5)
        self.assertTrue(all(item['context_semantic_sha256']=='a'*64 for item in injected))
        self.assertTrue(all('additionalContext' not in item for item in injected))
        self.assertNotIn('PRIVATE_SOURCE_BODY_',lifecycle._events_path(root,'codex').read_text())

    def test_rotation_obeys_byte_budget_and_retains_latest_complete_event(self):
        root=self.root()
        for number in range(100):
            lifecycle._append_event(root,'codex',{'stage':'guard','native_event':'PreToolUse',
                'detail':'x'*4096,'ordinal':number})
        log=lifecycle._events_path(root,'codex')
        self.assertLessEqual(log.stat().st_size,lifecycle.MAX_STATE_BYTES)
        events=lifecycle.observed_events(root,'codex')
        self.assertEqual(events[-1]['ordinal'],99)
        self.assertTrue(all(isinstance(json.loads(line),dict) for line in log.read_text().splitlines()))

if __name__=='__main__':unittest.main()
