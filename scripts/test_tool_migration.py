"""N04 tool-library acceptance: direct domain CLIs with clean and adverse inputs in disposable roots.

Independent of catalog freshness so recording new evidence never depends on that same evidence.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = {
    'workflow': 'automation-ops-engineer/scripts/check_workflow_contract.py',
    'seo': 'seo-growth-engineer/scripts/check_seo_content_packet.py',
    'mcp': 'mcp-integration-builder/scripts/validate_mcp_config.py',
    'pacing': 'video-script-architect/scripts/validate_script_pacing.py',
    'budget': 'paid-media-buyer/scripts/budget_pacer.py',
    'layout': 'frontend-ux-auditor/scripts/check_layout_overlap.py',
    'resource': 'ultra-light-optimizer/scripts/check_resource_budget.py',
}


class DirectToolAcceptance(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='crewloom-tools-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def run_tool(self, name, *args):
        return subprocess.run([sys.executable, str(ROOT / '.agents/skills' / TOOLS[name]), *map(str, args)],
                              cwd=self.root, capture_output=True, text=True, timeout=15)

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def assertResult(self, result, code, fragment=None):
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        if fragment:
            self.assertIn(fragment, result.stdout + result.stderr)

    def test_workflow_contract_accepts_references_and_refuses_embedded_secret(self):
        value = {'nodes': [{'id': '1', 'name': 'HTTP', 'type': 'http',
                           'credentials': {'http': {'id': 'reference-only'}}}], 'connections': {}}
        self.assertResult(self.run_tool('workflow', self.write('workflow.json', value)), 0, 'PASS')
        value['nodes'][0]['parameters'] = {'secret': 'synthetic-not-a-real-secret'}
        self.assertResult(self.run_tool('workflow', self.write('workflow.json', value)), 2, 'embedded secret')

    def test_seo_packet_accepts_required_fields_and_refuses_bad_slug(self):
        value = json.loads((ROOT / 'examples/seo/article-packet.json').read_text())
        self.assertResult(self.run_tool('seo', '--packet', self.write('seo.json', value)), 0, 'PASS')
        value['slug'] = 'Invalid Slug'
        self.assertResult(self.run_tool('seo', '--packet', self.write('seo.json', value)), 2, 'kebab-case')

    def test_mcp_config_accepts_placeholder_and_refuses_unsupported_transport(self):
        value = {'mcpServers': {'fixture': {'command': 'python', 'env': {'TOKEN': '${TOKEN}'}}}}
        self.assertResult(self.run_tool('mcp', '--config', self.write('mcp.json', value)), 0, 'PASS')
        value['mcpServers']['fixture']['transport'] = 'unsupported'
        self.assertResult(self.run_tool('mcp', '--config', self.write('mcp.json', value)), 2, 'unknown transport')

    def test_script_pacing_preserves_advisory_warnings_and_refuses_invalid_duration(self):
        self.assertResult(self.run_tool('pacing', '--text', 'word ' * 75, '--duration', '30'), 0, 'PASS')
        self.assertResult(self.run_tool('pacing', '--text', 'short', '--duration', '30'), 0, 'WARN')
        self.assertResult(self.run_tool('pacing', '--text', 'word', '--duration', 'nan'), 2)

    def test_budget_pacing_reports_actual_difference_and_refuses_invalid_numbers(self):
        self.assertResult(self.run_tool('budget', '--daily-budget', '100', '--days-elapsed', '3',
                                       '--actual-spend', '330'), 0, '+30.00')
        for value in ('-1', 'nan', 'inf'):
            self.assertResult(self.run_tool('budget', '--daily-budget', '100', '--days-elapsed', '3',
                                           '--actual-spend', value), 1)

    def test_layout_snapshot_accepts_separation_and_detects_observed_overlap(self):
        left = {'normalFlow': True, 'text': 'left', 'x': 0, 'y': 0, 'w': 100, 'h': 20}
        right = dict(left, text='right', y=30)
        value = {'viewport': {'w': 400}, 'elements': [left, right]}
        result = self.run_tool('layout', '--snapshot', self.write('layout.json', value), '--json')
        self.assertResult(result, 0)
        self.assertTrue(json.loads(result.stdout)['pass'])
        right['y'] = 10
        result = self.run_tool('layout', '--snapshot', self.write('layout.json', value), '--json')
        self.assertResult(result, 1)
        self.assertEqual(json.loads(result.stdout)['findings'][0]['overlap_px']['y'], 10)

    def test_malformed_layout_is_rejected_without_traceback(self):
        for value in ([], {'elements': [None]}, {'elements': [{'text': 'x', 'normalFlow': True}]}):
            self.assertResult(self.run_tool('layout', '--snapshot', self.write('bad.json', value), '--json'), 2)

    def test_resource_checker_accepts_clean_code_and_reports_unbounded_query(self):
        file = self.root / 'app.ts'
        file.write_text('export const pageSize = 20;\n')
        self.assertResult(self.run_tool('resource', '--project-dir', self.root), 0)
        file.write_text('const result = "SELECT id FROM users";\n')
        self.assertResult(self.run_tool('resource', '--project-dir', self.root), 1, 'R-HARD-03')


if __name__ == '__main__':
    unittest.main()
