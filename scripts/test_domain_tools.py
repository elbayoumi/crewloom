"""Exercise public CLI examples and malformed JSON rejection."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DomainExamples(unittest.TestCase):
    def run_tool(self, tool, *args):
        return subprocess.run([sys.executable, str(ROOT/'scripts/crewloom.py'), 'run', tool, '--', *args], cwd=ROOT, capture_output=True, text=True)

    def test_published_examples(self):
        cases = [
            ('workflow-contract', 'examples/workflows/valid.json'),
            ('seo-packet', '--packet', 'examples/seo/article-packet.json'),
            ('mcp-config', '--config', 'examples/mcp/config.json'),
            ('budget-pacing', '--daily-budget', '100', '--days-elapsed', '3', '--actual-spend', '300'),
            ('script-pacing', '--file', 'examples/video/script.txt', '--duration', '30'),
            ('grid-safety', '--project-dir', 'examples/ui', '--json'),
            ('palette-drift', '--project-dir', 'examples/ui', '--tokens', 'examples/ui/design-tokens.json', '--json'),
        ]
        for case in cases:
            with self.subTest(tool=case[0]):
                result=self.run_tool(*case)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_non_object_json_rejected_without_traceback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input.json'; path.write_text(json.dumps([]))
            for tool, flag in [('seo-packet','--packet'),('mcp-config','--config')]:
                with self.subTest(tool=tool):
                    result=self.run_tool(tool,flag,str(path))
                    self.assertEqual(result.returncode,2)
                    self.assertNotIn('Traceback',result.stderr)

    def test_unknown_tool_rejected(self):
        result=self.run_tool('not-a-tool')
        self.assertNotEqual(result.returncode,0)

if __name__=='__main__':
    unittest.main()
