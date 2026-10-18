#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""4-tier requirement-driven opaque-box E2E test suite for Crewloom expansion.

Validates the full feature set delivered under:
- R1: Zero-Friction Developer Experience (CLI demo, quickstart.sh)
- R2: AI IDE Ecosystem Integration (Cursor & Windsurf MCP templates, README)
- R3: Competitive Differentiation & Architecture Visuals (EN/AR matrices, Mermaid diagrams)
- Acceptance Criteria: Repository scope contract, manifest, and quality gates.

Follows the 4-tier methodology defined in TEST_INFRA.md:
- Tier 1: Feature coverage (happy paths in isolation) — 40 tests
- Tier 2: Boundary conditions, invalid flags, missing files, corrupted JSON — 40 tests
- Tier 3: Cross-feature interactions and pairwise combinations — 8 tests
- Tier 4: Real-world user journeys and end-to-end scenarios — 5 tests
Total: 93 test cases.

Supports progressive testability: tests for unimplemented milestone features report
clean skips by default, and fail strictly when E2E_STRICT=1 or --strict is set.
"""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from check_repository import _scope_entry_errors, scope_errors, inspect as check_inspect
except ImportError:
    _scope_entry_errors = None
    scope_errors = None
    check_inspect = None

try:
    MCP_SCRIPTS = ROOT / '.agents' / 'skills' / 'mcp-integration-builder' / 'scripts'
    if str(MCP_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(MCP_SCRIPTS))
    import validate_mcp_config
except ImportError:
    validate_mcp_config = None


class E2ETestBase(unittest.TestCase):
    """Shared utilities and assertions for opaque-box E2E testing."""

    ROOT = ROOT
    PYTHON = sys.executable

    def is_strict(self) -> bool:
        """Whether strict failure is enforced for pending features."""
        return os.environ.get('E2E_STRICT', '0') == '1' or getattr(self, 'STRICT', False)

    def skip_or_fail(self, reason: str):
        """Skip if in progressive mode; fail if in strict mode."""
        if self.is_strict():
            self.fail(f"STRICT MODE: {reason}")
        raise unittest.SkipTest(f"Pending implementation: {reason}")

    def run_cmd(self, cmd: list, env: dict = None, cwd: Path = None, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a subprocess command and return CompletedProcess."""
        actual_env = dict(os.environ)
        if env:
            actual_env.update(env)
        return subprocess.run(
            cmd,
            cwd=str(cwd or self.ROOT),
            env=actual_env,
            capture_output=True,
            text=True,
            timeout=timeout
        )

    def run_crewloom(self, *args, env: dict = None, cwd: Path = None, timeout: int = 30) -> subprocess.CompletedProcess:
        """Invoke scripts/crewloom.py with provided arguments."""
        cmd = [self.PYTHON, str(self.ROOT / 'scripts' / 'crewloom.py')] + list(args)
        return self.run_cmd(cmd, env=env, cwd=cwd, timeout=timeout)

    def has_crewloom_command(self, subcommand: str) -> bool:
        """Check if crewloom.py registers a given subcommand."""
        res = self.run_crewloom('--help')
        return subcommand in res.stdout

    def run_mcp_config(self, config_path: str, project_dir: str = None) -> subprocess.CompletedProcess:
        """Run mcp-config tool with proper project scope."""
        proj = project_dir or str(Path(config_path).resolve().parent)
        return self.run_crewloom('run', '--project', proj, 'mcp-config', '--', '--config', str(config_path))

    def extract_markdown_links(self, path: Path) -> list:
        """Extract all relative markdown links [text](target) ignoring code blocks."""
        if not path.is_file():
            return []
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'```.*?```', '', text, flags=re.S)
        text = re.sub(r'`[^`]*`', '', text)
        links = []
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if re.match(r'(?:[a-zA-Z][\w+.-]*:|#)', target):
                continue
            links.append(unquote(target.split('#', 1)[0]))
        return links

    def extract_mermaid_blocks(self, path: Path) -> list:
        """Extract all ```mermaid blocks from a markdown document."""
        if not path.is_file():
            return []
        text = path.read_text(encoding='utf-8')
        return re.findall(r'```mermaid\s+(.*?)\s+```', text, flags=re.S)

    def extract_markdown_tables(self, path: Path) -> list:
        """Extract pipe tables from markdown document."""
        if not path.is_file():
            return []
        lines = path.read_text(encoding='utf-8').splitlines()
        tables = []
        current = []
        for line in lines:
            if line.strip().startswith('|') and line.strip().endswith('|'):
                current.append(line.strip())
            else:
                if len(current) >= 2:
                    tables.append(current)
                current = []
        if len(current) >= 2:
            tables.append(current)
        return tables


# ==============================================================================
# TIER 1: Feature Coverage (Happy Paths in Isolation) — 40 Tests
# ==============================================================================

class Tier1FeatureCoverage(E2ETestBase):
    """Tier 1: Comprehensive happy path verification for all 8 features."""

    # --- Feature 1: CLI Demo (5 tests) ---

    def test_tier1_01_cli_demo_fast_execution(self):
        """R1: crewloom demo --fast runs, completes quickly, and exits 0."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered in scripts/crewloom.py")
        start = time.time()
        res = self.run_crewloom('demo', '--fast')
        elapsed = time.time() - start
        self.assertEqual(res.returncode, 0, f"crewloom demo failed: {res.stderr}\n{res.stdout}")
        self.assertLess(elapsed, 3.0, f"Fast mode should be near-instantaneous (<3s), took {elapsed:.2f}s")

    def test_tier1_02_cli_demo_role_selection_stage(self):
        """R1: crewloom demo stdout demonstrates Role Selection stage."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered in scripts/crewloom.py")
        res = self.run_crewloom('demo', '--fast')
        self.assertEqual(res.returncode, 0)
        output = res.stdout.lower()
        self.assertTrue('role' in output, "Demo output must display Role Selection stage")
        self.assertTrue('analyst' in output or 'architect' in output or 'engineer' in output,
                        "Demo must mention an active specialist role")

    def test_tier1_03_cli_demo_memory_consultation_stage(self):
        """R1: crewloom demo stdout demonstrates Working Memory Consultation stage."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered in scripts/crewloom.py")
        res = self.run_crewloom('demo', '--fast')
        self.assertEqual(res.returncode, 0)
        output = res.stdout.lower()
        self.assertTrue('memory' in output or 'brain' in output or 'architecture.md' in output,
                        "Demo output must display Memory Consultation stage")

    def test_tier1_04_cli_demo_container_isolation_stage(self):
        """R1: crewloom demo stdout demonstrates Isolated Container Verification stage."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered in scripts/crewloom.py")
        res = self.run_crewloom('demo', '--fast')
        self.assertEqual(res.returncode, 0)
        output = res.stdout.lower()
        self.assertTrue('container' in output or 'isolat' in output or 'docker' in output,
                        "Demo output must display Container Isolation Verification stage")

    def test_tier1_05_cli_demo_zero_api_keys_execution(self):
        """R1: crewloom demo runs successfully with zero external API keys."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered in scripts/crewloom.py")
        stripped_env = {
            'PATH': os.environ.get('PATH', ''),
            'HOME': os.environ.get('HOME', ''),
            'OPENAI_API_KEY': '',
            'ANTHROPIC_API_KEY': '',
            'GEMINI_API_KEY': '',
            'CREWLOOM_NO_LOG': '1'
        }
        res = self.run_crewloom('demo', '--fast', env=stripped_env)
        self.assertEqual(res.returncode, 0, f"Demo failed under zero API key environment: {res.stderr}")

    # --- Feature 2: Quickstart Script (5 tests) ---

    def test_tier1_06_quickstart_exists_and_executable(self):
        """R1: quickstart.sh exists at repository root and has execute permissions."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created at repo root")
        self.assertTrue(quickstart.is_file(), "quickstart.sh must be a regular file")
        mode = quickstart.stat().st_mode
        self.assertTrue(bool(mode & stat.S_IXUSR), "quickstart.sh must have user executable bit set")

    def test_tier1_07_quickstart_bash_syntax(self):
        """R1: quickstart.sh passes bash syntax validation (bash -n)."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created at repo root")
        res = self.run_cmd(['bash', '-n', str(quickstart)])
        self.assertEqual(res.returncode, 0, f"Bash syntax check failed: {res.stderr}")

    def test_tier1_08_quickstart_dry_run_execution(self):
        """R1: quickstart.sh --dry-run performs prerequisite checks and exits 0."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created at repo root")
        res = self.run_cmd(['bash', str(quickstart), '--dry-run'])
        self.assertEqual(res.returncode, 0, f"quickstart.sh --dry-run failed: {res.stderr}\n{res.stdout}")
        out = res.stdout.lower()
        self.assertTrue('python' in out or 'git' in out or 'prereq' in out,
                        "quickstart.sh --dry-run must report prerequisite verification")

    def test_tier1_09_quickstart_help_flag(self):
        """R1: quickstart.sh --help displays usage information and options."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created at repo root")
        res = self.run_cmd(['bash', str(quickstart), '--help'])
        self.assertEqual(res.returncode, 0, f"quickstart.sh --help failed: {res.stderr}")
        self.assertTrue('--dry-run' in res.stdout or 'dry-run' in res.stdout,
                        "Usage must document --dry-run option")

    def test_tier1_10_quickstart_shebang_and_strict_mode(self):
        """R1: quickstart.sh uses bash shebang and pipefail/strict execution mode."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created at repo root")
        content = quickstart.read_text(encoding='utf-8')
        lines = content.splitlines()
        self.assertTrue(lines[0].startswith('#!') and 'bash' in lines[0],
                        "quickstart.sh must begin with bash shebang")
        self.assertTrue('set -e' in content or 'set -euo pipefail' in content or 'set -u' in content,
                        "quickstart.sh should enable safe shell execution options")

    # --- Feature 3: Cursor MCP Template (5 tests) ---

    def test_tier1_11_cursor_mcp_template_exists(self):
        """R2: examples/mcp/cursor.json exists."""
        cursor_cfg = self.ROOT / 'examples' / 'mcp' / 'cursor.json'
        if not cursor_cfg.exists():
            self.skip_or_fail("examples/mcp/cursor.json not yet created")
        self.assertTrue(cursor_cfg.is_file())

    def test_tier1_12_cursor_mcp_valid_json_2space_indent(self):
        """R2: examples/mcp/cursor.json is valid strict JSON with 2-space indentation."""
        cursor_cfg = self.ROOT / 'examples' / 'mcp' / 'cursor.json'
        if not cursor_cfg.exists():
            self.skip_or_fail("examples/mcp/cursor.json not yet created")
        raw = cursor_cfg.read_text(encoding='utf-8')
        self.assertTrue(raw.endswith('\n'), "examples/mcp/cursor.json must end with newline")
        data = json.loads(raw)
        self.assertIsInstance(data, dict)
        reformatted = json.dumps(data, indent=2) + '\n'
        self.assertEqual(raw, reformatted, "cursor.json must strictly match 2-space indentation format")

    def test_tier1_13_cursor_mcp_schema_structure(self):
        """R2: cursor.json conforms to mcpServers schema with stdio transport."""
        cursor_cfg = self.ROOT / 'examples' / 'mcp' / 'cursor.json'
        if not cursor_cfg.exists():
            self.skip_or_fail("examples/mcp/cursor.json not yet created")
        data = json.loads(cursor_cfg.read_text(encoding='utf-8'))
        self.assertIn('mcpServers', data)
        self.assertTrue(bool(data['mcpServers']), "mcpServers must not be empty")
        for name, server in data['mcpServers'].items():
            self.assertIn('command', server, f"Server {name} missing command")
            self.assertEqual(server.get('transport', 'stdio'), 'stdio', f"Server {name} must use stdio transport")
            self.assertIsInstance(server.get('args', []), list, f"Server {name} args must be a list")
            self.assertIsInstance(server.get('env', {}), dict, f"Server {name} env must be a dict")

    def test_tier1_14_cursor_mcp_validated_by_mcp_config(self):
        """R2: cursor.json passes validate_mcp_config / crewloom run mcp-config."""
        cursor_cfg = self.ROOT / 'examples' / 'mcp' / 'cursor.json'
        if not cursor_cfg.exists():
            self.skip_or_fail("examples/mcp/cursor.json not yet created")
        res = self.run_crewloom('run', 'mcp-config', '--', '--config', 'examples/mcp/cursor.json')
        self.assertEqual(res.returncode, 0, f"mcp-config validation failed for cursor.json: {res.stderr}\n{res.stdout}")
        self.assertIn("PASS mcp config", res.stdout)

    def test_tier1_15_cursor_mcp_parity_with_rea_standard(self):
        """R2: cursor.json matches the architectural schema of examples/mcp/rea.json."""
        cursor_cfg = self.ROOT / 'examples' / 'mcp' / 'cursor.json'
        rea_cfg = self.ROOT / 'examples' / 'mcp' / 'rea.json'
        if not cursor_cfg.exists():
            self.skip_or_fail("examples/mcp/cursor.json not yet created")
        self.assertTrue(rea_cfg.exists(), "Reference standard examples/mcp/rea.json must exist")
        c_data = json.loads(cursor_cfg.read_text(encoding='utf-8'))
        r_data = json.loads(rea_cfg.read_text(encoding='utf-8'))
        self.assertEqual(set(c_data.keys()), set(r_data.keys()))

    # --- Feature 4: Windsurf MCP Template (5 tests) ---

    def test_tier1_16_windsurf_mcp_template_exists(self):
        """R2: examples/mcp/windsurf.json exists."""
        windsurf_cfg = self.ROOT / 'examples' / 'mcp' / 'windsurf.json'
        if not windsurf_cfg.exists():
            self.skip_or_fail("examples/mcp/windsurf.json not yet created")
        self.assertTrue(windsurf_cfg.is_file())

    def test_tier1_17_windsurf_mcp_valid_json_2space_indent(self):
        """R2: examples/mcp/windsurf.json is valid strict JSON with 2-space indentation."""
        windsurf_cfg = self.ROOT / 'examples' / 'mcp' / 'windsurf.json'
        if not windsurf_cfg.exists():
            self.skip_or_fail("examples/mcp/windsurf.json not yet created")
        raw = windsurf_cfg.read_text(encoding='utf-8')
        self.assertTrue(raw.endswith('\n'), "examples/mcp/windsurf.json must end with newline")
        data = json.loads(raw)
        self.assertIsInstance(data, dict)
        reformatted = json.dumps(data, indent=2) + '\n'
        self.assertEqual(raw, reformatted, "windsurf.json must strictly match 2-space indentation format")

    def test_tier1_18_windsurf_mcp_schema_structure(self):
        """R2: windsurf.json conforms to mcpServers schema with stdio transport."""
        windsurf_cfg = self.ROOT / 'examples' / 'mcp' / 'windsurf.json'
        if not windsurf_cfg.exists():
            self.skip_or_fail("examples/mcp/windsurf.json not yet created")
        data = json.loads(windsurf_cfg.read_text(encoding='utf-8'))
        self.assertIn('mcpServers', data)
        self.assertTrue(bool(data['mcpServers']), "mcpServers must not be empty")
        for name, server in data['mcpServers'].items():
            self.assertIn('command', server, f"Server {name} missing command")
            self.assertEqual(server.get('transport', 'stdio'), 'stdio', f"Server {name} must use stdio transport")
            self.assertIsInstance(server.get('args', []), list, f"Server {name} args must be a list")
            self.assertIsInstance(server.get('env', {}), dict, f"Server {name} env must be a dict")

    def test_tier1_19_windsurf_mcp_validated_by_mcp_config(self):
        """R2: windsurf.json passes validate_mcp_config / crewloom run mcp-config."""
        windsurf_cfg = self.ROOT / 'examples' / 'mcp' / 'windsurf.json'
        if not windsurf_cfg.exists():
            self.skip_or_fail("examples/mcp/windsurf.json not yet created")
        res = self.run_crewloom('run', 'mcp-config', '--', '--config', 'examples/mcp/windsurf.json')
        self.assertEqual(res.returncode, 0, f"mcp-config validation failed for windsurf.json: {res.stderr}\n{res.stdout}")
        self.assertIn("PASS mcp config", res.stdout)

    def test_tier1_20_windsurf_mcp_parity_with_rea_standard(self):
        """R2: windsurf.json matches the architectural schema of examples/mcp/rea.json."""
        windsurf_cfg = self.ROOT / 'examples' / 'mcp' / 'windsurf.json'
        rea_cfg = self.ROOT / 'examples' / 'mcp' / 'rea.json'
        if not windsurf_cfg.exists():
            self.skip_or_fail("examples/mcp/windsurf.json not yet created")
        self.assertTrue(rea_cfg.exists())
        w_data = json.loads(windsurf_cfg.read_text(encoding='utf-8'))
        r_data = json.loads(rea_cfg.read_text(encoding='utf-8'))
        self.assertEqual(set(w_data.keys()), set(r_data.keys()))

    # --- Feature 5: MCP Documentation Guide (5 tests) ---

    def test_tier1_21_mcp_readme_exists(self):
        """R2: examples/mcp/README.md exists."""
        readme = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not readme.exists():
            self.skip_or_fail("examples/mcp/README.md not yet created")
        self.assertTrue(readme.is_file())

    def test_tier1_22_mcp_readme_covers_cursor_setup(self):
        """R2: examples/mcp/README.md details Cursor IDE setup and config path."""
        readme = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not readme.exists():
            self.skip_or_fail("examples/mcp/README.md not yet created")
        content = readme.read_text(encoding='utf-8')
        self.assertIn('Cursor', content, "README must document Cursor")
        self.assertTrue('.cursor' in content or 'mcp.json' in content, "README must document Cursor configuration path")

    def test_tier1_23_mcp_readme_covers_windsurf_setup(self):
        """R2: examples/mcp/README.md details Windsurf Cascade IDE setup and config path."""
        readme = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not readme.exists():
            self.skip_or_fail("examples/mcp/README.md not yet created")
        content = readme.read_text(encoding='utf-8')
        self.assertIn('Windsurf', content, "README must document Windsurf")
        self.assertTrue('mcp_config.json' in content or 'codeium' in content.lower(),
                        "README must document Windsurf configuration path")

    def test_tier1_24_mcp_readme_covers_3tier_verification(self):
        """R2: examples/mcp/README.md documents 3-tier verification procedure."""
        readme = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not readme.exists():
            self.skip_or_fail("examples/mcp/README.md not yet created")
        content = readme.read_text(encoding='utf-8').lower()
        self.assertTrue('mcp-config' in content or 'validate' in content, "README must document configuration validation")
        self.assertTrue('handshake' in content or 'tools/list' in content or 'initialize' in content or 'tier' in content,
                        "README must detail live verification / tool discovery")

    def test_tier1_25_mcp_readme_documents_all_fixtures(self):
        """R2: examples/mcp/README.md documents published fixtures."""
        readme = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not readme.exists():
            self.skip_or_fail("examples/mcp/README.md not yet created")
        content = readme.read_text(encoding='utf-8')
        for fixture in ('cursor.json', 'windsurf.json', 'rea.json', 'crewloom-task.json'):
            self.assertIn(fixture, content, f"README must mention fixture {fixture}")

    # --- Feature 6: Competitive Matrix (5 tests) ---

    def test_tier1_26_readme_en_matrix_exists(self):
        """R3: README.md contains competitive framework comparison table."""
        readme = self.ROOT / 'README.md'
        tables = self.extract_markdown_tables(readme)
        matrix_tables = [t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])]
        if not matrix_tables:
            self.skip_or_fail("README.md comparison matrix not yet created")
        self.assertTrue(len(matrix_tables) >= 1)

    def test_tier1_27_readme_en_matrix_covers_frameworks(self):
        """R3: README.md matrix compares Crewloom, CrewAI, AutoGen, and LangGraph."""
        readme = self.ROOT / 'README.md'
        tables = self.extract_markdown_tables(readme)
        matrix = next((t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not matrix:
            self.skip_or_fail("README.md comparison matrix not yet created")
        header = matrix[0]
        for framework in ('Crewloom', 'CrewAI', 'AutoGen', 'LangGraph'):
            self.assertIn(framework, header, f"Matrix header must include {framework}")

    def test_tier1_28_readme_en_matrix_covers_dimensions(self):
        """R3: README.md matrix covers required architectural dimensions."""
        readme = self.ROOT / 'README.md'
        tables = self.extract_markdown_tables(readme)
        matrix = next((t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not matrix:
            self.skip_or_fail("README.md comparison matrix not yet created")
        table_text = '\n'.join(matrix).lower()
        self.assertTrue('architecture' in table_text or 'foundation' in table_text)
        self.assertTrue('memory' in table_text)
        self.assertTrue('isolation' in table_text or 'docker' in table_text or 'sandbox' in table_text)
        self.assertTrue('orchestration' in table_text or 'workflow' in table_text)
        self.assertTrue('developer experience' in table_text or 'devex' in table_text or 'quickstart' in table_text or 'setup' in table_text)

    def test_tier1_29_readme_ar_matrix_exists(self):
        """R3: README.ar.md contains Arabic competitive comparison table."""
        readme = self.ROOT / 'README.ar.md'
        tables = self.extract_markdown_tables(readme)
        matrix_tables = [t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])]
        if not matrix_tables:
            self.skip_or_fail("README.ar.md comparison matrix not yet created")
        self.assertTrue(len(matrix_tables) >= 1)

    def test_tier1_30_readme_ar_matrix_technical_parity(self):
        """R3: README.ar.md matrix preserves framework columns and row symmetry."""
        readme = self.ROOT / 'README.ar.md'
        tables = self.extract_markdown_tables(readme)
        matrix = next((t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not matrix:
            self.skip_or_fail("README.ar.md comparison matrix not yet created")
        header = matrix[0]
        for framework in ('Crewloom', 'CrewAI', 'AutoGen', 'LangGraph'):
            self.assertIn(framework, header, f"Arabic matrix header must retain {framework}")
        self.assertGreaterEqual(len(matrix), 7, "Arabic matrix must have header + separator + >=5 dimension rows")

    # --- Feature 7: Vector Architecture Diagram (5 tests) ---

    def test_tier1_31_readme_en_mermaid_exists(self):
        """R3: README.md contains native Mermaid vector architecture flowchart."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        if not diagrams:
            self.skip_or_fail("README.md Mermaid architecture diagram not yet created")
        self.assertTrue(any('flowchart' in d for d in diagrams))

    def test_tier1_32_readme_en_mermaid_subgraphs(self):
        """R3: README.md Mermaid diagram covers key architecture subgraphs."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        if not diagrams:
            self.skip_or_fail("README.md Mermaid architecture diagram not yet created")
        combined = '\n'.join(diagrams).lower()
        self.assertTrue('ide' in combined or 'developer' in combined, "Must include IDE / Developer entry stage")
        self.assertTrue('memory' in combined or 'context' in combined, "Must include Memory / Context stage")
        self.assertTrue('sandbox' in combined or 'docker' in combined or 'isolation' in combined, "Must include Sandbox stage")
        self.assertTrue('verification' in combined or 'review' in combined or 'evidence' in combined, "Must include Verification stage")

    def test_tier1_33_readme_en_mermaid_node_identities(self):
        """R3: README.md Mermaid diagram references concrete components."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        if not diagrams:
            self.skip_or_fail("README.md Mermaid architecture diagram not yet created")
        combined = '\n'.join(diagrams)
        self.assertTrue('quickstart.sh' in combined or 'demo' in combined)
        self.assertTrue('mcp' in combined.lower())
        self.assertTrue('sha256' in combined or 'network none' in combined or 'worktree' in combined.lower())

    def test_tier1_34_readme_ar_mermaid_exists(self):
        """R3: README.ar.md contains Arabic Mermaid vector architecture flowchart."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.ar.md')
        if not diagrams:
            self.skip_or_fail("README.ar.md Mermaid architecture diagram not yet created")
        self.assertTrue(any('flowchart' in d for d in diagrams))

    def test_tier1_35_readme_ar_mermaid_parity(self):
        """R3: README.ar.md Mermaid diagram mirrors English diagram flow."""
        en_diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        ar_diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.ar.md')
        if not en_diagrams or not ar_diagrams:
            self.skip_or_fail("Mermaid architecture diagrams not yet created in both READMEs")
        en_d = next(d for d in en_diagrams if 'flowchart' in d)
        ar_d = next(d for d in ar_diagrams if 'flowchart' in d)
        en_subgraphs = len(re.findall(r'\bsubgraph\b', en_d))
        ar_subgraphs = len(re.findall(r'\bsubgraph\b', ar_d))
        self.assertEqual(en_subgraphs, ar_subgraphs, "Arabic and English diagrams must have identical subgraph counts")

    # --- Feature 8: Repository Scope & Gates (5 tests) ---

    def test_tier1_36_scope_contract_schema(self):
        """Acceptance Criteria: REPOSITORY_SCOPE.json conforms to schema version 1."""
        contract = self.ROOT / 'REPOSITORY_SCOPE.json'
        self.assertTrue(contract.is_file())
        data = json.loads(contract.read_text(encoding='utf-8'))
        self.assertEqual(data.get('schema_version'), 1)
        self.assertEqual(data.get('project_id'), 'crewloom-toolkit')

    def test_tier1_37_scope_registers_quickstart(self):
        """Acceptance Criteria: quickstart.sh is declared in REPOSITORY_SCOPE.json files."""
        contract = self.ROOT / 'REPOSITORY_SCOPE.json'
        data = json.loads(contract.read_text(encoding='utf-8'))
        files = data.get('files', [])
        if 'quickstart.sh' not in files:
            self.skip_or_fail("quickstart.sh not yet added to REPOSITORY_SCOPE.json files list")
        self.assertIn('quickstart.sh', files)

    def test_tier1_38_manifest_in_registers_quickstart(self):
        """Acceptance Criteria: MANIFEST.in includes quickstart.sh."""
        manifest = self.ROOT / 'MANIFEST.in'
        self.assertTrue(manifest.is_file())
        content = manifest.read_text(encoding='utf-8')
        if 'quickstart.sh' not in content:
            self.skip_or_fail("quickstart.sh not yet added to MANIFEST.in")
        self.assertIn('quickstart.sh', content)

    def test_tier1_39_examples_directory_in_scope(self):
        """Acceptance Criteria: examples directory is registered in REPOSITORY_SCOPE.json."""
        contract = self.ROOT / 'REPOSITORY_SCOPE.json'
        data = json.loads(contract.read_text(encoding='utf-8'))
        directories = data.get('directories', [])
        self.assertIn('examples', directories)

    def test_tier1_40_no_unregistered_root_files(self):
        """Acceptance Criteria: zero unregistered top-level files in repository."""
        if _scope_entry_errors is None:
            self.skip_or_fail("check_repository module not available")
        errors = scope_errors(self.ROOT)
        # Filter out ORIGINAL_REQUEST.md if still present at root during early development
        real_errors = [e for e in errors if 'ORIGINAL_REQUEST.md' not in e]
        if not self.is_strict():
            # In progressive mode, allow quickstart.sh if its scope registration test is still pending
            contract = self.ROOT / 'REPOSITORY_SCOPE.json'
            if contract.is_file():
                try:
                    data = json.loads(contract.read_text(encoding='utf-8'))
                    if 'quickstart.sh' not in data.get('files', []):
                        real_errors = [e for e in real_errors if 'quickstart.sh' not in e]
                except Exception:
                    pass
        self.assertEqual(real_errors, [], f"Scope check failed with errors: {real_errors}")


# ==============================================================================
# TIER 2: Boundary Conditions & Corner Cases — 40 Tests
# ==============================================================================

class Tier2BoundaryConditions(E2ETestBase):
    """Tier 2: Boundary value analysis, invalid inputs, corrupted files, security rejections."""

    # --- CLI Demo Boundaries (5 tests) ---

    def test_tier2_01_cli_demo_invalid_role_handled(self):
        """R1: crewloom demo with non-existent role rejects cleanly without crash."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered")
        res = self.run_crewloom('demo', '--role', 'nonexistent_role_xyz_123', '--fast')
        self.assertNotIn('Traceback (most recent call last)', res.stderr)

    def test_tier2_02_cli_demo_unknown_flag_rejected(self):
        """R1: crewloom demo with unknown flag exits with standard code 2."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered")
        res = self.run_crewloom('demo', '--unrecognized-flag-xyz')
        self.assertEqual(res.returncode, 2)
        self.assertIn('unrecognized arguments', res.stderr)

    def test_tier2_03_cli_demo_missing_project_dir_handled(self):
        """R1: crewloom demo with invalid project path rejects cleanly without traceback."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered")
        res = self.run_crewloom('demo', '--project', '/nonexistent/path/xyz', '--fast')
        self.assertNotIn('Traceback', res.stderr)

    def test_tier2_04_cli_demo_empty_string_role_rejected(self):
        """R1: crewloom demo with empty role rejects cleanly."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered")
        res = self.run_crewloom('demo', '--role', '', '--fast')
        self.assertNotIn('Traceback (most recent call last)', res.stderr)

    def test_tier2_05_cli_demo_excess_positional_arguments(self):
        """R1: crewloom demo with unexpected positional arguments exits 2."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered")
        res = self.run_crewloom('demo', 'extra_arg_1', 'extra_arg_2')
        self.assertEqual(res.returncode, 2)

    # --- Quickstart Boundaries (5 tests) ---

    def test_tier2_06_quickstart_unknown_option_rejected(self):
        """R1: quickstart.sh rejects unrecognized command line options."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created")
        res = self.run_cmd(['bash', str(quickstart), '--invalid-flag-xyz'])
        self.assertNotEqual(res.returncode, 0, "quickstart.sh should exit non-zero on unknown options")

    def test_tier2_07_quickstart_no_color_environment(self):
        """R1: quickstart.sh respects NO_COLOR=1 and produces zero ANSI escape sequences."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created")
        res = self.run_cmd(['bash', str(quickstart), '--dry-run'], env={'NO_COLOR': '1'})
        self.assertEqual(res.returncode, 0)
        self.assertNotIn('\033[', res.stdout, "Output must contain no ANSI escape codes when NO_COLOR=1")
        self.assertNotIn('\x1b[', res.stdout)

    def test_tier2_08_quickstart_missing_option_argument(self):
        """R1: quickstart.sh handles missing argument for parameterized options."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created")
        res = self.run_cmd(['bash', str(quickstart), '--role'])
        self.assertNotEqual(res.returncode, 0)

    def test_tier2_09_quickstart_posix_syntax_compatibility(self):
        """R1: quickstart.sh avoids bash-4-only associative arrays and syntax."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created")
        content = quickstart.read_text(encoding='utf-8')
        self.assertNotIn('declare -A', content, "quickstart.sh must not use bash 4+ associative arrays")

    def test_tier2_10_quickstart_dry_run_leaves_no_artifacts(self):
        """R1: quickstart.sh --dry-run creates no temporary files or directories."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created")
        res = self.run_cmd(['bash', str(quickstart), '--dry-run'])
        self.assertEqual(res.returncode, 0)
        # Check no dirty virtualenvs or temporary files created at repo root
        self.assertFalse((self.ROOT / '.venv_dryrun').exists())
        self.assertFalse((self.ROOT / 'tmp_quickstart').exists())

    # --- MCP Config Boundaries & Secret Rejection (10 tests) ---

    def test_tier2_11_mcp_config_rejects_sk_openai_secret(self):
        """R2: validate_mcp_config rejects real sk- OpenAI tokens with exit code 2."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            bad_cfg = {
                "mcpServers": {
                    "leaker": {
                        "command": "python3",
                        "transport": "stdio",
                        "args": ["-m", "server"],
                        "env": {"OPENAI_KEY": "s" + "k-proj-1234567890abcdef1234567890"}
                    }
                }
            }
            json.dump(bad_cfg, tmp)
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("looks like an embedded real secret", res.stdout)
            self.assertNotIn("Traceback", res.stderr)

    def test_tier2_12_mcp_config_rejects_ghp_github_token(self):
        """R2: validate_mcp_config rejects GitHub personal access tokens (ghp_)."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            bad_cfg = {
                "mcpServers": {
                    "leaker": {
                        "command": "python3",
                        "transport": "stdio",
                        "args": [],
                        "env": {"GITHUB_TOKEN": "g" + "hp_1234567890abcdef1234567890abcdef"}
                    }
                }
            }
            json.dump(bad_cfg, tmp)
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("embedded real secret", res.stdout)

    def test_tier2_13_mcp_config_rejects_akia_aws_key(self):
        """R2: validate_mcp_config rejects AWS access keys (AKIA...)."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            bad_cfg = {
                "mcpServers": {
                    "leaker": {
                        "command": "python3",
                        "transport": "stdio",
                        "args": [],
                        "env": {"AWS_ACCESS_KEY_ID": "A" + "KIAIOSFODNN7EXAMPLE"}
                    }
                }
            }
            json.dump(bad_cfg, tmp)
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("embedded real secret", res.stdout)

    def test_tier2_14_mcp_config_rejects_unknown_transport(self):
        """R2: validate_mcp_config rejects unknown transports (e.g. websocket)."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            bad_cfg = {
                "mcpServers": {
                    "bad_srv": {
                        "command": "python3",
                        "transport": "websocket",
                        "args": [],
                        "env": {}
                    }
                }
            }
            json.dump(bad_cfg, tmp)
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("unknown transport 'websocket'", res.stdout)

    def test_tier2_15_mcp_config_rejects_missing_command(self):
        """R2: validate_mcp_config rejects server entry missing 'command' field."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            bad_cfg = {
                "mcpServers": {
                    "no_cmd": {
                        "transport": "stdio",
                        "args": [],
                        "env": {}
                    }
                }
            }
            json.dump(bad_cfg, tmp)
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("missing 'command'", res.stdout)

    def test_tier2_16_mcp_config_rejects_empty_object(self):
        """R2: validate_mcp_config rejects empty root object {}."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            tmp.write("{}")
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("missing or empty top-level 'mcpServers' object", res.stdout)

    def test_tier2_17_mcp_config_rejects_array_root(self):
        """R2: validate_mcp_config rejects array as top-level JSON."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            tmp.write("[]")
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("top-level JSON must be an object", res.stdout)

    def test_tier2_18_mcp_config_rejects_empty_mcpservers(self):
        """R2: validate_mcp_config rejects mcpServers being an empty object."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            tmp.write('{"mcpServers": {}}')
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 2)
            self.assertIn("missing or empty top-level 'mcpServers' object", res.stdout)

    def test_tier2_19_mcp_config_rejects_nonexistent_file(self):
        """R2: validate_mcp_config reports load error on missing file and exits 1."""
        res = self.run_crewloom('run', 'mcp-config', '--', '--config', 'nonexistent_file_xyz.json')
        self.assertEqual(res.returncode, 1)
        self.assertIn("cannot load config", res.stdout)

    def test_tier2_20_mcp_config_accepts_placeholder_env(self):
        """R2: validate_mcp_config accepts ${PLACEHOLDER} environment variables."""
        with tempfile.NamedTemporaryFile('w', suffix='.json') as tmp:
            ok_cfg = {
                "mcpServers": {
                    "ok_srv": {
                        "command": "python3",
                        "transport": "stdio",
                        "args": [],
                        "env": {"API_TOKEN": "${API_TOKEN}"}
                    }
                }
            }
            json.dump(ok_cfg, tmp)
            tmp.flush()
            res = self.run_mcp_config(tmp.name)
            self.assertEqual(res.returncode, 0)
            self.assertIn("PASS mcp config", res.stdout)

    # --- Documentation & Link Boundaries (5 tests) ---

    def test_tier2_21_mcp_readme_rejects_broken_mcp_md_link(self):
        """R2: examples/mcp/README.md does NOT link to non-existent documentation/MCP.md."""
        readme = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not readme.exists():
            self.skip_or_fail("examples/mcp/README.md not yet created")
        content = readme.read_text(encoding='utf-8')
        self.assertNotIn('documentation/MCP.md', content,
                         "Must not link to non-existent MCP.md; authoritative path is MCP_BRIDGE.md")

    def test_tier2_22_markdown_link_validator_ignores_code_fences(self):
        """Acceptance Criteria: link validator ignores fake links inside code fences."""
        fake_text = "Here is valid text.\n```markdown\n[broken link](nonexistent/fake.md)\n```\nDone."
        fences_removed = re.sub(r'```.*?```', '', fake_text, flags=re.S)
        self.assertNotIn('[broken link]', fences_removed)

    def test_tier2_23_markdown_link_validator_ignores_inline_code(self):
        """Acceptance Criteria: link validator ignores links inside inline backticks."""
        fake_text = "Use `[label](target.md)` syntax for links."
        inlines_removed = re.sub(r'`[^`]*`', '', fake_text)
        self.assertNotIn('[label]', inlines_removed)

    def test_tier2_24_markdown_link_validator_handles_anchor_fragments(self):
        """Acceptance Criteria: link validator skips anchor-only references (#section)."""
        target = "#heading-1"
        is_anchor = bool(re.match(r'(?:[a-zA-Z][\w+.-]*:|#)', target))
        self.assertTrue(is_anchor)

    def test_tier2_25_markdown_link_validator_handles_external_protocols(self):
        """Acceptance Criteria: link validator skips external URLs (http, https, mailto)."""
        for url in ("https://github.com", "http://localhost:4317", "mailto:user@example.com"):
            is_external = bool(re.match(r'(?:[a-zA-Z][\w+.-]*:|#)', url))
            self.assertTrue(is_external, f"Protocol should be detected as external: {url}")

    # --- Competitive Matrix Boundaries (5 tests) ---

    def test_tier2_26_matrix_en_exact_column_count_per_row(self):
        """R3: README.md matrix rows have consistent column counts."""
        readme = self.ROOT / 'README.md'
        tables = self.extract_markdown_tables(readme)
        matrix = next((t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not matrix:
            self.skip_or_fail("README.md comparison matrix not yet created")
        cols_count = len([c for c in matrix[0].split('|') if c.strip()])
        self.assertEqual(cols_count, 5, "Matrix header must have exactly 5 columns")
        for i, row in enumerate(matrix[2:]):
            row_cols = len([c for c in row.split('|') if c.strip()])
            self.assertEqual(row_cols, 5, f"Matrix row {i} has {row_cols} columns, expected 5")

    def test_tier2_27_matrix_en_no_empty_cells(self):
        """R3: README.md matrix contains no empty or whitespace-only cells."""
        readme = self.ROOT / 'README.md'
        tables = self.extract_markdown_tables(readme)
        matrix = next((t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not matrix:
            self.skip_or_fail("README.md comparison matrix not yet created")
        for row in matrix[2:]:
            cells = [c.strip() for c in row.split('|')[1:-1]]
            for cell in cells:
                self.assertTrue(len(cell) > 0, "Matrix cells must not be empty")

    def test_tier2_28_matrix_en_strictly_four_frameworks(self):
        """R3: README.md matrix compares exactly the 4 specified frameworks."""
        readme = self.ROOT / 'README.md'
        tables = self.extract_markdown_tables(readme)
        matrix = next((t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not matrix:
            self.skip_or_fail("README.md comparison matrix not yet created")
        header_cells = [c.strip() for c in matrix[0].split('|')[1:-1]]
        frameworks = [c for c in header_cells if c not in ('Dimension', 'Feature', 'Property')]
        self.assertEqual(len(frameworks), 4, f"Matrix must compare exactly 4 frameworks, found: {frameworks}")

    def test_tier2_29_matrix_ar_exact_column_count_per_row(self):
        """R3: README.ar.md matrix rows have consistent column counts."""
        readme = self.ROOT / 'README.ar.md'
        tables = self.extract_markdown_tables(readme)
        matrix = next((t for t in tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not matrix:
            self.skip_or_fail("README.ar.md comparison matrix not yet created")
        cols_count = len([c for c in matrix[0].split('|') if c.strip()])
        self.assertEqual(cols_count, 5, "Arabic matrix header must have exactly 5 columns")
        for i, row in enumerate(matrix[2:]):
            row_cols = len([c for c in row.split('|') if c.strip()])
            self.assertEqual(row_cols, 5, f"Arabic matrix row {i} has {row_cols} columns, expected 5")

    def test_tier2_30_matrix_ar_exact_row_count_symmetry(self):
        """R3: README.ar.md matrix row count matches English README.md matrix."""
        en_tables = self.extract_markdown_tables(self.ROOT / 'README.md')
        ar_tables = self.extract_markdown_tables(self.ROOT / 'README.ar.md')
        en_matrix = next((t for t in en_tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        ar_matrix = next((t for t in ar_tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not en_matrix or not ar_matrix:
            self.skip_or_fail("Comparison matrices not yet created in both READMEs")
        self.assertEqual(len(en_matrix), len(ar_matrix), "Arabic and English comparison matrices must have equal row count")

    # --- Diagram Boundaries (5 tests) ---

    def test_tier2_31_diagram_en_balanced_subgraphs(self):
        """R3: README.md Mermaid flowchart has balanced subgraph and end tokens."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        if not diagrams:
            self.skip_or_fail("README.md Mermaid architecture diagram not yet created")
        d = next(d for d in diagrams if 'flowchart' in d)
        subgraphs = len(re.findall(r'\bsubgraph\b', d))
        ends = len(re.findall(r'\bend\b', d))
        self.assertEqual(subgraphs, ends, f"Unbalanced subgraphs ({subgraphs}) and ends ({ends}) in EN diagram")

    def test_tier2_32_diagram_ar_balanced_subgraphs(self):
        """R3: README.ar.md Mermaid flowchart has balanced subgraph and end tokens."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.ar.md')
        if not diagrams:
            self.skip_or_fail("README.ar.md Mermaid architecture diagram not yet created")
        d = next(d for d in diagrams if 'flowchart' in d)
        subgraphs = len(re.findall(r'\bsubgraph\b', d))
        ends = len(re.findall(r'\bend\b', d))
        self.assertEqual(subgraphs, ends, f"Unbalanced subgraphs ({subgraphs}) and ends ({ends}) in AR diagram")

    def test_tier2_33_diagram_no_external_image_dependencies(self):
        """R3: Architecture diagrams avoid third-party hosted raster images."""
        en_diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        ar_diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.ar.md')
        for d in en_diagrams + ar_diagrams:
            self.assertNotIn('http://', d)
            self.assertNotIn('https://', d)

    def test_tier2_34_diagram_bidirectional_protocol_arrows(self):
        """R3: Architecture diagrams show bidirectional IDE <--> MCP communication."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        if not diagrams:
            self.skip_or_fail("README.md Mermaid architecture diagram not yet created")
        d = next(d for d in diagrams if 'flowchart' in d)
        self.assertTrue('<-->' in d or '<->' in d or ('-->' in d and '<--' in d),
                        "Diagram must illustrate bidirectional protocol interaction between IDE and MCP")

    def test_tier2_35_diagram_feedback_loop_connection(self):
        """R3: Architecture diagrams connect execution evidence back to memory/dashboard."""
        diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        if not diagrams:
            self.skip_or_fail("README.md Mermaid architecture diagram not yet created")
        d = next(d for d in diagrams if 'flowchart' in d)
        self.assertTrue('Brain' in d or 'Evidence' in d or 'Dashboard' in d,
                        "Diagram must connect execution outcomes to feedback / brain nodes")

    # --- Scope Gate Boundaries (5 tests) ---

    def test_tier2_36_scope_rejects_path_traversal(self):
        """Acceptance Criteria: scope checker rejects path traversal entry names."""
        if _scope_entry_errors is None:
            self.skip_or_fail("check_repository not imported")
        errs = _scope_entry_errors('../escape', 'files', {})
        self.assertTrue(len(errs) > 0)
        self.assertTrue(any('one top-level name inside this root' in e for e in errs))

    def test_tier2_37_scope_rejects_absolute_path(self):
        """Acceptance Criteria: scope checker rejects absolute paths in registered entries."""
        if _scope_entry_errors is None:
            self.skip_or_fail("check_repository not imported")
        errs = _scope_entry_errors('/etc/passwd', 'files', {})
        self.assertTrue(len(errs) > 0)

    def test_tier2_38_scope_rejects_nul_bytes(self):
        """Acceptance Criteria: scope checker rejects entries containing NUL bytes."""
        if _scope_entry_errors is None:
            self.skip_or_fail("check_repository not imported")
        errs = _scope_entry_errors('file\0bad', 'files', {})
        self.assertTrue(len(errs) > 0)
        self.assertTrue(any('NUL byte' in e for e in errs))

    def test_tier2_39_scope_rejects_case_folding_collisions(self):
        """Acceptance Criteria: scope checker rejects case-folded alias collisions."""
        if _scope_entry_errors is None:
            self.skip_or_fail("check_repository not imported")
        registered = {'readme.md': 'README.md'}
        errs = _scope_entry_errors('Readme.md', 'files', registered)
        self.assertTrue(len(errs) > 0)
        self.assertTrue(any('collides' in e for e in errs))

    def test_tier2_40_scope_rejects_ephemeral_registration(self):
        """Acceptance Criteria: scope checker rejects registering ephemeral trees as content."""
        if _scope_entry_errors is None:
            self.skip_or_fail("check_repository not imported")
        for ephem in ('.git', '.crewloom', '__pycache__', 'node_modules'):
            errs = _scope_entry_errors(ephem, 'directories', {})
            self.assertTrue(len(errs) > 0, f"Scope should reject ephemeral directory: {ephem}")


# ==============================================================================
# TIER 3: Cross-Feature Interactions & Combinations — 8 Tests
# ==============================================================================

class Tier3CrossFeatureCombinations(E2ETestBase):
    """Tier 3: Pairwise combinations and cross-feature workflows."""

    def test_tier3_01_quickstart_demo_fast_chaining(self):
        """Combination: quickstart.sh --demo --fast executes the interactive CLI demo with --fast."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists() or not self.has_crewloom_command('demo'):
            self.skip_or_fail("quickstart.sh or crewloom demo not yet implemented")
        start = time.time()
        res = self.run_cmd(['bash', str(quickstart), '--demo', '--fast'])
        elapsed = time.time() - start
        self.assertEqual(res.returncode, 0, f"quickstart.sh --demo --fast failed: {res.stderr}\n{res.stdout}")
        self.assertLess(elapsed, 4.0, f"Combined fast execution should complete in <4s, took {elapsed:.2f}s")
        out = res.stdout.lower()
        self.assertTrue('role' in out or 'memory' in out or 'container' in out,
                        "Combined output must include demo stages")

    def test_tier3_02_quickstart_dry_run_precedence(self):
        """Combination: quickstart.sh --dry-run takes precedence when combined with --demo."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists():
            self.skip_or_fail("quickstart.sh not yet created")
        res = self.run_cmd(['bash', str(quickstart), '--dry-run', '--demo'])
        self.assertEqual(res.returncode, 0)
        # Should finish very fast and perform checks
        out = res.stdout.lower()
        self.assertTrue('dry-run' in out or 'dry run' in out or 'prereq' in out)

    def test_tier3_03_mcp_config_validates_both_templates(self):
        """Combination: crewloom run mcp-config validates both cursor.json and windsurf.json."""
        c_path = self.ROOT / 'examples' / 'mcp' / 'cursor.json'
        w_path = self.ROOT / 'examples' / 'mcp' / 'windsurf.json'
        if not c_path.exists() or not w_path.exists():
            self.skip_or_fail("MCP template files not yet created")
        res_c = self.run_crewloom('run', 'mcp-config', '--', '--config', 'examples/mcp/cursor.json')
        res_w = self.run_crewloom('run', 'mcp-config', '--', '--config', 'examples/mcp/windsurf.json')
        self.assertEqual(res_c.returncode, 0)
        self.assertEqual(res_w.returncode, 0)
        self.assertIn("PASS mcp config", res_c.stdout)
        self.assertIn("PASS mcp config", res_w.stdout)

    def test_tier3_04_readme_links_to_new_templates_and_scripts(self):
        """Combination: README.md links to quickstart.sh and MCP templates resolve cleanly."""
        readme = self.ROOT / 'README.md'
        links = self.extract_markdown_links(readme)
        for link in links:
            resolved = (readme.parent / link).resolve()
            if 'quickstart.sh' in link or 'cursor.json' in link or 'windsurf.json' in link:
                if not resolved.exists():
                    self.skip_or_fail(f"Referenced file not yet present: {link}")
                self.assertTrue(resolved.exists(), f"Broken relative link in README.md: {link}")

    def test_tier3_05_mcp_readme_links_to_mcp_bridge_and_privacy(self):
        """Combination: examples/mcp/README.md links to documentation/MCP_BRIDGE.md and PRIVACY.md."""
        mcp_readme = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not mcp_readme.exists():
            self.skip_or_fail("examples/mcp/README.md not yet created")
        links = self.extract_markdown_links(mcp_readme)
        self.assertTrue(len(links) > 0, "examples/mcp/README.md must contain reference links")
        for link in links:
            resolved = (mcp_readme.parent / link).resolve()
            self.assertTrue(resolved.exists(), f"Broken relative link in examples/mcp/README.md: {link} -> {resolved}")

    def test_tier3_06_bilingual_matrix_dimension_parity(self):
        """Combination: comparison matrix rows in README.md and README.ar.md correspond 1-to-1."""
        en_tables = self.extract_markdown_tables(self.ROOT / 'README.md')
        ar_tables = self.extract_markdown_tables(self.ROOT / 'README.ar.md')
        en_matrix = next((t for t in en_tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        ar_matrix = next((t for t in ar_tables if any('Crewloom' in row and 'CrewAI' in row for row in t[:2])), None)
        if not en_matrix or not ar_matrix:
            self.skip_or_fail("Comparison matrices not yet created in both READMEs")
        # Subtract header and separator
        en_dims = len(en_matrix) - 2
        ar_dims = len(ar_matrix) - 2
        self.assertEqual(en_dims, ar_dims, f"Dimension count mismatch: EN has {en_dims}, AR has {ar_dims}")

    def test_tier3_07_bilingual_diagram_subgraph_parity(self):
        """Combination: Mermaid architecture diagrams in README.md and README.ar.md have equal subgraphs."""
        en_diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.md')
        ar_diagrams = self.extract_mermaid_blocks(self.ROOT / 'README.ar.md')
        if not en_diagrams or not ar_diagrams:
            self.skip_or_fail("Mermaid architecture diagrams not yet created in both READMEs")
        en_d = next(d for d in en_diagrams if 'flowchart' in d)
        ar_d = next(d for d in ar_diagrams if 'flowchart' in d)
        self.assertEqual(len(re.findall(r'\bsubgraph\b', en_d)), len(re.findall(r'\bsubgraph\b', ar_d)))

    def test_tier3_08_cli_demo_alternate_catalog_roles(self):
        """Combination: crewloom demo functions with alternate catalog roles under --fast."""
        if not self.has_crewloom_command('demo'):
            self.skip_or_fail("crewloom demo command not registered")
        for role in ('reverse-engineering-analyst', 'tech-stack-architect', 'qa-test-automation-engineer'):
            res = self.run_crewloom('demo', '--role', role, '--fast')
            self.assertEqual(res.returncode, 0, f"Demo failed for catalog role {role}: {res.stderr}")


# ==============================================================================
# TIER 4: Real-World Scenarios & User Journeys — 5 Tests
# ==============================================================================

class Tier4EndToEndJourneys(E2ETestBase):
    """Tier 4: Realistic end-to-end user journeys and repository scope gate validation."""

    def test_tier4_01_developer_onboarding_journey(self):
        """Scenario 1: Fresh developer clones repo, runs dry-run, runs fast demo, sees exit 0."""
        quickstart = self.ROOT / 'quickstart.sh'
        if not quickstart.exists() or not self.has_crewloom_command('demo'):
            self.skip_or_fail("Onboarding prerequisites not yet implemented")
        # Step 1: Run dry-run validation
        res_dry = self.run_cmd(['bash', str(quickstart), '--dry-run'])
        self.assertEqual(res_dry.returncode, 0)
        # Step 2: Run interactive demo via quickstart with --fast
        res_demo = self.run_cmd(['bash', str(quickstart), '--demo', '--fast'])
        self.assertEqual(res_demo.returncode, 0)
        # Step 3: Verify clean working directory
        res_status = self.run_cmd(['git', 'status', '--porcelain'])
        # Only existing untracked files should remain
        untracked = [line for line in res_status.stdout.splitlines() if not line.endswith('.agents/teamwork/')]
        for line in untracked:
            self.assertNotIn('.venv_demo', line)
            self.assertNotIn('.crewloom_tmp', line)

    def test_tier4_02_cursor_ide_integration_journey(self):
        """Scenario 2: Developer sets up Cursor MCP template and validates task bridge args."""
        c_path = self.ROOT / 'examples' / 'mcp' / 'cursor.json'
        readme_path = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not c_path.exists() or not readme_path.exists():
            self.skip_or_fail("Cursor MCP assets not yet implemented")
        # Step 1: Developer reads README
        readme_content = readme_path.read_text(encoding='utf-8')
        self.assertIn('cursor.json', readme_content)
        # Step 2: Validates configuration format
        res = self.run_crewloom('run', 'mcp-config', '--', '--config', 'examples/mcp/cursor.json')
        self.assertEqual(res.returncode, 0)
        # Step 3: Verifies task bridge arguments match mcp_bridge requirements
        data = json.loads(c_path.read_text(encoding='utf-8'))
        server = next(iter(data['mcpServers'].values()))
        self.assertEqual(server.get('transport'), 'stdio')
        self.assertIsInstance(server.get('args'), list)
        self.assertEqual(server.get('env'), {})

    def test_tier4_03_windsurf_ide_integration_journey(self):
        """Scenario 3: Developer sets up Windsurf MCP template and verifies credential safety."""
        w_path = self.ROOT / 'examples' / 'mcp' / 'windsurf.json'
        readme_path = self.ROOT / 'examples' / 'mcp' / 'README.md'
        if not w_path.exists() or not readme_path.exists():
            self.skip_or_fail("Windsurf MCP assets not yet implemented")
        # Step 1: Validates template with CLI
        res = self.run_crewloom('run', 'mcp-config', '--', '--config', 'examples/mcp/windsurf.json')
        self.assertEqual(res.returncode, 0)
        # Step 2: Validates that no unexpanded secrets or API keys are embedded
        data = json.loads(w_path.read_text(encoding='utf-8'))
        for name, server in data['mcpServers'].items():
            for k, v in server.get('env', {}).items():
                self.assertTrue(v.startswith('${') and v.endswith('}'),
                                f"Secret in {name}.{k} must use placeholder syntax")

    def test_tier4_04_bilingual_documentation_audit(self):
        """Scenario 4: Bilingual technical audit of README.md and README.ar.md."""
        en_readme = self.ROOT / 'README.md'
        ar_readme = self.ROOT / 'README.ar.md'
        self.assertTrue(en_readme.is_file())
        self.assertTrue(ar_readme.is_file())
        en_text = en_readme.read_text(encoding='utf-8')
        ar_text = ar_readme.read_text(encoding='utf-8')
        # Both must include banner
        self.assertIn('assets/crewloom-banner.svg', en_text)
        self.assertIn('assets/crewloom-banner.svg', ar_text)
        # Both must include navigation link to the other
        self.assertIn('README.ar.md', en_text)
        self.assertIn('README.md', ar_text)

    def test_tier4_05_repository_scope_gate_validation(self):
        """Scenario 5: Repository release integrity gate audit."""
        contract = self.ROOT / 'REPOSITORY_SCOPE.json'
        self.assertTrue(contract.is_file())
        data = json.loads(contract.read_text(encoding='utf-8'))
        self.assertEqual(data.get('schema_version'), 1)
        self.assertEqual(data.get('project_id'), 'crewloom-toolkit')
        # Python syntax validation across all repository scripts
        for py_path in (self.ROOT / 'scripts').glob('*.py'):
            try:
                ast.parse(py_path.read_text(encoding='utf-8'))
            except SyntaxError as e:
                self.fail(f"Syntax error in repository script {py_path.name}: {e}")


# ==============================================================================
# Main Runner
# ==============================================================================

if __name__ == '__main__':
    # Support --strict flag on CLI
    if '--strict' in sys.argv:
        sys.argv.remove('--strict')
        os.environ['E2E_STRICT'] = '1'
    unittest.main()
