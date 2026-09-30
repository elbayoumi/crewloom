"""Reject literal colors outside the approved tokens; accept token colors in any supported notation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('check_palette_drift.py')
TOKENS = {"color": {"ink": "#1b1b18", "accent": "#2B4FD8", "rule": "rgb(226, 224, 216)"}}


class PaletteDriftTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.tokens = self.root / 'design-tokens.json'
        self.tokens.write_text(json.dumps(TOKENS), encoding='utf-8')

    def write(self, name, content):
        (self.root / name).write_text(content, encoding='utf-8')

    def run_gate(self, *extra, tokens=None):
        return subprocess.run([sys.executable, str(SCRIPT), '--project-dir', str(self.root), '--tokens',
                               str(tokens or self.tokens), '--json', *extra], capture_output=True, text=True, timeout=10)

    def test_off_token_color_fails_with_location(self):
        """The two off-token colors seeded in the 2026-10-01 fixture."""
        self.write('a.css', ".price { color: #ff6600; }\n.card { border: 1px solid #ddd; }")
        result = self.run_gate()
        self.assertEqual(result.returncode, 1, result.stdout)
        found = {(v['line'], v['color']) for v in json.loads(result.stdout)['violations']}
        self.assertEqual(found, {(1, '#ff6600'), (2, '#dddddd')})

    def test_token_colors_pass_in_hex_upper_short_and_rgb_forms(self):
        self.write('a.css', ".a{color:#1B1B18}.b{color:#2b4fd8}.c{border-color:rgb(226,224,216)}.d{color:rgba(27,27,24,.5)}")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_alpha_suffix_is_ignored_for_comparison(self):
        self.write('a.css', ".a{color:#1b1b18cc}")
        self.assertEqual(self.run_gate().returncode, 0)

    def test_inline_tsx_style_is_checked(self):
        self.write('a.tsx', '<button style={{ background: "#f60", color: "#fff" }}>x</button>')
        result = self.run_gate()
        self.assertEqual(result.returncode, 1)
        self.assertEqual({v['color'] for v in json.loads(result.stdout)['violations']}, {'#ff6600', '#ffffff'})

    def test_allow_list_accepts_neutrals(self):
        self.write('a.css', ".a{color:#fff}.b{color:#000}")
        self.assertEqual(self.run_gate('--allow', '#fff,#000').returncode, 0)

    def test_id_selectors_and_anchors_are_not_colors(self):
        self.write('a.css', "#header{margin:0}\na[href='#abc123x']{color:#1b1b18}")
        self.assertEqual(self.run_gate().returncode, 0)

    def test_unused_token_is_warning_only(self):
        self.write('a.css', ".a{color:#1b1b18}")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(json.loads(result.stdout)['unused_tokens']), 2)

    def test_tokens_file_inside_project_is_not_scanned_as_source(self):
        self.write('a.css', ".a{color:#1b1b18}")
        self.tokens.rename(self.root / 'tokens.html')
        payload = json.loads(self.run_gate(tokens=self.root / 'tokens.html').stdout)
        self.assertEqual((payload['state'], payload['files']), ('clean', 1))

    def test_unverified_inputs_exit_2(self):
        self.write('a.css', ".a{color:#ff6600}")
        self.assertEqual(self.run_gate(tokens=self.root / 'missing.json').returncode, 2)
        self.tokens.write_text('{"space": {"sm": "8px"}}', encoding='utf-8')
        self.assertEqual(self.run_gate().returncode, 2)
        self.tokens.write_text('not json', encoding='utf-8')
        self.assertEqual(self.run_gate().returncode, 2)

    def test_vendored_directories_are_skipped(self):
        (self.root / '.venv').mkdir()
        (self.root / '.venv' / 'v.html').write_text("<style>a{color:#00cc33}</style>", encoding='utf-8')
        self.write('a.css', ".a{color:#1b1b18}")
        self.assertEqual(self.run_gate().returncode, 0)

    def test_no_source_files_exit_2(self):
        self.assertEqual(self.run_gate().returncode, 2)


if __name__ == '__main__':
    unittest.main()
