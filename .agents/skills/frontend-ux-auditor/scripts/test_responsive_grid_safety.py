"""Reject unguarded fixed-px grid floors without flagging safe min()-wrapped or non-px floors."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('check_responsive_grid_safety.py')


class ResponsiveGridSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.write_text(content, encoding='utf-8')
        return path

    def run_gate(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--project-dir', str(self.root), '--json'],
            capture_output=True, text=True, timeout=10,
        )

    def test_fixed_floor_regression_pattern_fails(self):
        """The exact line from AuctionsApp.tsx before the 2026-09-15 fix."""
        self.write('AuctionsApp.tsx', "gridTemplateColumns: 'minmax(340px, 1fr) 1.2fr',")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        payload = json.loads(result.stdout)
        self.assertFalse(payload['pass'])
        self.assertEqual(len(payload['violations']), 1)

    def test_min_wrapped_floor_passes(self):
        """The exact line from AuctionsApp.tsx after the fix."""
        self.write('AuctionsApp.tsx', "gridTemplateColumns: 'repeat(auto-fit, minmax(min(340px, 100%), 1fr))',")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(json.loads(result.stdout)['pass'])

    def test_min_content_floor_passes(self):
        self.write('a.tsx', "gridTemplateColumns: 'repeat(auto-fit, minmax(min-content, 1fr))',")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_percentage_floor_passes(self):
        self.write('a.css', ".grid { grid-template-columns: minmax(20%, 1fr); }")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_breakpoint_prefixed_floor_that_fits_passes(self):
        """The two code-vault grids measured as false positives on 2026-10-01."""
        self.write('a.tsx', '<div className="grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.85fr)]">')
        self.write('b.tsx', '<div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]">')
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_breakpoint_prefixed_floor_too_large_still_fails(self):
        self.write('a.tsx', '<div className="md:grid-cols-[minmax(400px,1fr)_1fr]">')
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_unprefixed_tailwind_floor_still_fails(self):
        self.write('a.tsx', '<div className="grid grid-cols-[minmax(320px,1fr)_1fr]">')
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)

    def test_only_the_matching_token_is_guarded(self):
        self.write('a.tsx', "<div className=\"lg:grid-cols-[minmax(0,1fr)_minmax(320px,1fr)]\" style={{gridTemplateColumns: 'minmax(340px, 1fr) 1fr'}}>")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(len(json.loads(result.stdout)['violations']), 1)

    def test_multiple_files_aggregate(self):
        self.write('a.tsx', "gridTemplateColumns: 'minmax(320px, 1fr)',")
        self.write('b.css', ".x { grid-template-columns: minmax(240px, 1fr); }")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(len(json.loads(result.stdout)['violations']), 2)

    def test_node_modules_excluded(self):
        (self.root / 'node_modules').mkdir()
        self.write('node_modules/vendor.tsx', "gridTemplateColumns: 'minmax(320px, 1fr)',")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == '__main__':
    unittest.main()
