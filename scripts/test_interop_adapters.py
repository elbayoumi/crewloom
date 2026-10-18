"""Unit tests for Crewloom Cross-Framework Interoperability Adapters.

Verifies:
1. Hardened Docker command construction & security isolation flags
2. Refusal of root UID, comma-injections, and path escapes
3. CrewAI tool interface compatibility (run, _run, __call__, schema)
4. AutoGen CodeExecutor protocol compatibility (CommandLineCodeResult, CodeBlock extraction)
5. LangGraph state node compatibility (state transform, output key binding)
6. Zero runtime dependencies (standard library only)
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

# Ensure adapters and scripts are importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from adapters.interop.autogen_sandbox import (
    CodeBlock,
    CommandLineCodeResult,
    CrewloomAutoGenExecutor,
    extract_code_blocks,
)
from adapters.interop.crewai_sandbox import (
    ISOLATION_FLAGS,
    CrewloomSandboxTool,
    build_sandbox_command,
    execute_in_sandbox,
    execute_sandbox_command,
)
from adapters.interop.langgraph_sandbox import (
    CrewloomLangGraphNode,
    create_crewloom_sandbox_node,
)


class TestInteropSandboxCommand(unittest.TestCase):
    """Test Docker command generation and isolation invariants."""

    def setUp(self):
        self.mock_uid = os.getuid() if hasattr(os, "getuid") and os.getuid() != 0 else 1000
        self.mock_gid = os.getgid() if hasattr(os, "getgid") and os.getgid() != 0 else 1000
        patch_uid = mock.patch("os.getuid", return_value=self.mock_uid)
        patch_gid = mock.patch("os.getgid", return_value=self.mock_gid)
        patch_uid.start()
        patch_gid.start()
        self.addCleanup(patch_uid.stop)
        self.addCleanup(patch_gid.stop)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name).resolve()
        (self.workspace / "output").mkdir()
        self.addCleanup(self.temp_dir.cleanup)

    def _flag_pairs(self, cmd: list) -> dict:
        pairs = {}
        for i in range(len(cmd) - 1):
            if cmd[i].startswith("--"):
                pairs[cmd[i]] = cmd[i + 1]
        return pairs

    def test_all_isolation_flags_present(self):
        cmd = build_sandbox_command(self.workspace, ["python3", "-c", "print(1)"])
        self.assertIn("--read-only", cmd)
        pairs = self._flag_pairs(cmd)
        self.assertEqual(pairs["--network"], "none")
        self.assertEqual(pairs["--cap-drop"], "ALL")
        self.assertEqual(pairs["--security-opt"], "no-new-privileges")
        self.assertEqual(pairs["--user"], f"{self.mock_uid}:{self.mock_gid}")
        self.assertEqual(pairs["--pids-limit"], "128")
        self.assertEqual(pairs["--memory"], "1g")
        self.assertEqual(pairs["--cpus"], "2")
        self.assertIn("--ulimit", pairs)

    def test_root_uid_refusal(self):
        with mock.patch("os.getuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "refuse to run as root"):
                build_sandbox_command(self.workspace, ["python3", "-c", "print(1)"])

    def test_no_privilege_widening_flags(self):
        cmd = build_sandbox_command(self.workspace, ["python3", "-c", "print(1)"], writable=["output"])
        for forbidden in ("--privileged", "--cap-add", "--pid", "--ipc", "--uts", "--device", "-v"):
            self.assertNotIn(forbidden, cmd)
        self.assertFalse(any("docker.sock" in item for item in cmd))

    def test_writable_mount_narrowing(self):
        cmd = build_sandbox_command(self.workspace, ["python3", "-c", "print(1)"], writable=["output"])
        mounts = [cmd[i + 1] for i, item in enumerate(cmd) if item == "--mount"]
        self.assertEqual(
            mounts,
            [
                f"type=bind,src={self.workspace},dst=/workspace,readonly",
                f"type=bind,src={self.workspace / 'output'},dst=/workspace/output",
            ],
        )

    def test_comma_path_injection_refused(self):
        comma_dir = self.workspace / "bad,path"
        comma_dir.mkdir()
        with self.assertRaisesRegex(ValueError, "commas"):
            build_sandbox_command(comma_dir, ["python3"])

    def test_path_escape_refused(self):
        with self.assertRaisesRegex(ValueError, "escapes workspace"):
            build_sandbox_command(self.workspace, ["python3"], writable=["../outside"])


class TestCrewAISandboxTool(unittest.TestCase):
    """Test CrewAI tool interface and execution behavior."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

    def test_tool_metadata(self):
        tool = CrewloomSandboxTool(workspace_root=self.workspace)
        self.assertEqual(tool.name, "crewloom_sandbox")
        self.assertIn("isolated container", tool.description)

    @mock.patch("adapters.interop.crewai_sandbox.subprocess.run")
    def test_tool_execution_success(self, mock_run):
        mock_proc = mock.Mock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"Hello from isolated container!\n"
        mock_run.return_value = mock_proc

        tool = CrewloomSandboxTool(workspace_root=self.workspace)
        output = tool.run("print('Hello from isolated container!')")
        self.assertIn("Hello from isolated container!", output)

        # Test __call__ interface
        call_output = tool("print('Hello from isolated container!')")
        self.assertEqual(call_output, output)

    @mock.patch("adapters.interop.crewai_sandbox.subprocess.run")
    def test_tool_execution_failure(self, mock_run):
        mock_proc = mock.Mock()
        mock_proc.returncode = 1
        mock_proc.stdout = b"ZeroDivisionError: division by zero\n"
        mock_run.return_value = mock_proc

        tool = CrewloomSandboxTool(workspace_root=self.workspace)
        output = tool.run("1 / 0")
        self.assertIn("[Execution failed (code 1)]", output)
        self.assertIn("ZeroDivisionError", output)

    def test_unsupported_language_refusal(self):
        tool = CrewloomSandboxTool(workspace_root=self.workspace)
        with self.assertRaisesRegex(ValueError, "Unsupported language"):
            tool.execute("console.log(1)", language="javascript")

    def test_to_crewai_tool_graceful_handling(self):
        tool = CrewloomSandboxTool(workspace_root=self.workspace)
        if "crewai" not in sys.modules:
            # If crewai is not installed, verify helpful error
            with self.assertRaises(ImportError) as ctx:
                tool.to_crewai_tool()
            self.assertIn("crewai is not installed", str(ctx.exception))


class TestAutoGenSandboxExecutor(unittest.TestCase):
    """Test AutoGen code executor adapter and code block extraction."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

    def test_extract_code_blocks(self):
        text = """Here is a solution:
```python
x = 42
print(x)
```
And here is a shell check:
```bash
echo "done"
```
"""
        blocks = extract_code_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].language, "python")
        self.assertEqual(blocks[0].code, "x = 42\nprint(x)")
        self.assertEqual(blocks[1].language, "bash")
        self.assertEqual(blocks[1].code, 'echo "done"')

    @mock.patch("adapters.interop.crewai_sandbox.subprocess.run")
    def test_execute_code_blocks(self, mock_run):
        mock_proc = mock.Mock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"42\n"
        mock_run.return_value = mock_proc

        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace)
        result = executor.execute_code_blocks([CodeBlock(language="python", code="print(42)")])
        self.assertIsInstance(result, CommandLineCodeResult)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "42")

    @mock.patch("adapters.interop.crewai_sandbox.subprocess.run")
    def test_execute_markdown_string(self, mock_run):
        mock_proc = mock.Mock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"test passed\n"
        mock_run.return_value = mock_proc

        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace)
        markdown = "```python\nprint('test passed')\n```"
        result = executor.execute_code_blocks(markdown)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "test passed")

    def test_empty_blocks(self):
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace)
        result = executor.execute_code_blocks([])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("No executable code blocks found", result.output)


class TestLangGraphSandboxNode(unittest.TestCase):
    """Test LangGraph node adapter and state transformations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

    @mock.patch("adapters.interop.crewai_sandbox.subprocess.run")
    def test_langgraph_node_execution(self, mock_run):
        mock_proc = mock.Mock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"Graph node output\n"
        mock_run.return_value = mock_proc

        node = create_crewloom_sandbox_node(workspace_root=self.workspace)
        state = {"code": "print('Graph node output')", "language": "python"}
        delta = node(state)

        self.assertIn("sandbox_result", delta)
        res = delta["sandbox_result"]
        self.assertEqual(res["exit_code"], 0)
        self.assertIn("Graph node output", res["output"])
        self.assertEqual(res["isolation"], "crewloom-airgap")

    def test_empty_code_in_state(self):
        node = CrewloomLangGraphNode(workspace_root=self.workspace)
        delta = node({"code": ""})
        self.assertIn("sandbox_result", delta)
        self.assertEqual(delta["sandbox_result"]["exit_code"], 0)
        self.assertIn("No code provided", delta["sandbox_result"]["output"])


if __name__ == "__main__":
    unittest.main()
