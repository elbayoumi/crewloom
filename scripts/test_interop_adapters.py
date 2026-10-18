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

    def test_empty_writable_set_is_fully_readonly(self):
        tool = CrewloomSandboxTool(workspace_root=self.workspace, writable=[])
        self.assertEqual(tool.writable, ())
        cmd = build_sandbox_command(self.workspace, ["python3", "-c", "print(1)"], writable=tool.writable)
        mounts = [cmd[i + 1] for i, item in enumerate(cmd) if item == "--mount"]
        self.assertEqual(mounts, [f"type=bind,src={self.workspace},dst=/workspace,readonly"])

        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace, writable=())
        self.assertEqual(executor.writable, ())

        node = CrewloomLangGraphNode(workspace_root=self.workspace, writable=[])
        self.assertEqual(node.writable, ())

    def test_path_escape_refused(self):
        with self.assertRaisesRegex(ValueError, "escapes workspace"):
            build_sandbox_command(self.workspace, ["python3"], writable=["../outside"])

    def test_crewai_docker_user_fallback(self):
        import adapters.interop.crewai_sandbox as crewai_mod
        with mock.patch.object(crewai_mod, "_workflow", None):
            with mock.patch("os.getuid", return_value=0), mock.patch("os.getgid", return_value=0):
                # Valid override
                with mock.patch.dict(os.environ, {"CREWLOOM_CONTAINER_USER": "10005:10005"}):
                    self.assertEqual(crewai_mod._docker_user(), "10005:10005")

                # Invalid root override
                with mock.patch.dict(os.environ, {"CREWLOOM_CONTAINER_USER": "0:0"}):
                    with self.assertRaisesRegex(ValueError, "unprivileged"):
                        crewai_mod._docker_user()

                # Root allow fallback
                with mock.patch.dict(os.environ, {"CREWLOOM_CONTAINER_USER": "", "CREWLOOM_ALLOW_CONTAINER_ROOT": "1"}):
                    self.assertEqual(crewai_mod._docker_user(), "10001:10001")


class TestCrewAISandboxTool(unittest.TestCase):
    """Test CrewAI tool interface and execution behavior."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

    def test_tool_metadata_and_func_property(self):
        tool = CrewloomSandboxTool(workspace_root=self.workspace)
        self.assertEqual(tool.name, "crewloom_sandbox")
        self.assertIn("isolated container", tool.description)
        self.assertTrue(callable(tool.func))
        self.assertEqual(tool.func, tool.run)

    @mock.patch("adapters.interop.crewai_sandbox.subprocess.run")
    @mock.patch("adapters.interop.crewai_sandbox.subprocess.Popen")
    def test_execute_sandbox_command_with_mock_popen(self, mock_popen, mock_run):
        import io
        proc = mock.MagicMock()
        proc.stdout = io.BytesIO(b"direct output\n")
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        proc.returncode = 0
        mock_popen.return_value = proc
        res = execute_sandbox_command(self.workspace, ["python3", "-c", "print(1)"])
        self.assertEqual(res["exit_code"], 0)
        self.assertEqual(res["output"], "direct output\n")
        self.assertFalse(res["output_truncated"])

    @mock.patch("adapters.interop.crewai_sandbox.subprocess.run")
    @mock.patch("adapters.interop.crewai_sandbox.subprocess.Popen")
    def test_execute_sandbox_command_cancellation_kills_container(self, mock_popen, mock_run):
        import io
        proc = mock.MagicMock()
        proc.stdout = io.BytesIO(b"partial output\n")
        proc.poll.return_value = None
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        token = mock.Mock()
        token.is_cancelled.return_value = True

        res = execute_sandbox_command(self.workspace, ["python3", "-c", "import time; time.sleep(10)"], cancellation_token=token)
        self.assertEqual(res["exit_code"], 130)
        self.assertTrue(res["cancelled"])
        self.assertIn("Execution cancelled by user", res["output"])
        proc.kill.assert_called()
        kill_calls = [call for call in mock_run.call_args_list if call[0][0][:2] == ["docker", "kill"]]
        self.assertTrue(len(kill_calls) >= 1)

    @mock.patch("adapters.interop.crewai_sandbox.execute_sandbox_command")
    def test_tool_execution_success(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "Hello from isolated container!\n",
            "timed_out": False,
            "duration_ms": 10,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
        tool = CrewloomSandboxTool(workspace_root=self.workspace)
        output = tool.run("print('Hello from isolated container!')")
        self.assertIn("Hello from isolated container!", output)

        call_output = tool("print('Hello from isolated container!')")
        self.assertEqual(call_output, output)

    @mock.patch("adapters.interop.crewai_sandbox.execute_sandbox_command")
    def test_tool_execution_failure(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 1,
            "output": "ZeroDivisionError: division by zero\n",
            "timed_out": False,
            "duration_ms": 5,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
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

    @mock.patch("adapters.interop.autogen_sandbox.execute_sandbox_command")
    def test_execute_code_blocks(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "42\n",
            "timed_out": False,
            "duration_ms": 10,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace)
        result = executor.execute_code_blocks([CodeBlock(language="python", code="print(42)")])
        self.assertIsInstance(result, CommandLineCodeResult)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.output, "42")

    @mock.patch("adapters.interop.autogen_sandbox.execute_sandbox_command")
    def test_execute_markdown_string(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "test passed\n",
            "timed_out": False,
            "duration_ms": 10,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
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

    def test_autogen_cancellation_token_and_async(self):
        import asyncio
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace)
        token = mock.Mock()
        token.is_cancelled.return_value = False
        token.is_set.return_value = False
        with mock.patch("adapters.interop.autogen_sandbox.execute_sandbox_command") as mock_exec:
            mock_exec.return_value = {"exit_code": 0, "output": "ok"}
            res = executor.execute_code_blocks([CodeBlock(language="python", code="1")], cancellation_token=token)
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(res.output, "ok")

        async def run_async():
            with mock.patch("adapters.interop.autogen_sandbox.execute_sandbox_command") as mock_exec:
                mock_exec.return_value = {"exit_code": 0, "output": "async_ok"}
                return await executor.a_execute_code_blocks([CodeBlock(language="python", code="1")], cancellation_token=token)
        async_res = asyncio.run(run_async())
        self.assertEqual(async_res.exit_code, 0)
        self.assertEqual(async_res.output, "async_ok")

    def test_cancellation_token_triggered(self):
        token = mock.Mock()
        token.is_cancelled.return_value = True
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace)
        result = executor.execute_code_blocks([CodeBlock(language="python", code="print(1)")], cancellation_token=token)
        self.assertEqual(result.exit_code, 130)
        self.assertIn("Execution cancelled", result.output)

    def test_cancellation_token_cancelled_between_blocks(self):
        token = mock.Mock()
        # First check False, second check True
        token.is_cancelled.side_effect = [False, False, True]
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace)
        with mock.patch("adapters.interop.autogen_sandbox.execute_sandbox_command") as mock_exec:
            mock_exec.return_value = {"exit_code": 0, "output": "block 1 ok"}
            blocks = [
                CodeBlock(language="python", code="print(1)"),
                CodeBlock(language="python", code="print(2)"),
            ]
            result = executor.execute_code_blocks(blocks, cancellation_token=token)
            self.assertEqual(result.exit_code, 130)
            self.assertIn("Execution cancelled before block 2", result.output)

    def test_stateful_session_wrapper(self):
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace, stateful=True)
        self.assertTrue(executor.stateful)
        with mock.patch("adapters.interop.autogen_sandbox.execute_sandbox_command") as mock_exec:
            mock_exec.return_value = {"exit_code": 0, "output": "stateful_output"}
            res = executor.execute_code_blocks([CodeBlock(language="python", code="x = 10")])
            self.assertEqual(res.exit_code, 0)
            self.assertEqual(res.output, "stateful_output")
            # Verify argv passed to execute_sandbox_command used the stateful wrapper
            called_argv = mock_exec.call_args[1]["argv"]
            self.assertEqual(called_argv[0], "python3")
            self.assertEqual(called_argv[1], "-c")
            self.assertIn("_STATE_FILE", called_argv[2])
            self.assertIn("_HISTORY_FILE", called_argv[2])

    def test_restart_cleans_session_state(self):
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace, stateful=True)
        session_dir = self.workspace / ".crewloom" / "autogen_session"
        session_dir.mkdir(parents=True, exist_ok=True)
        state_file = session_dir / "session_state.pkl"
        hist_file = session_dir / "session_history.py"
        state_file.write_text("dummy state")
        hist_file.write_text("dummy history")

        self.assertTrue(state_file.exists())
        self.assertTrue(hist_file.exists())

        executor.restart()

        self.assertFalse(state_file.exists())
        self.assertFalse(hist_file.exists())

    def test_autogen_cli_runner(self):
        from adapters.interop.autogen_sandbox import main
        import io
        from unittest.mock import patch

        with patch("adapters.interop.autogen_sandbox.execute_sandbox_command") as mock_exec:
            mock_exec.return_value = {"exit_code": 0, "output": "CLI Hello"}
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = main(["--code", "print('CLI Hello')", "--workspace", str(self.workspace), "--json"])
            self.assertEqual(code, 0)
            import json
            data = json.loads(stdout.getvalue())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["output"], "CLI Hello")

        # Missing code/file argument returns 2
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--workspace", str(self.workspace)])
        self.assertEqual(code, 2)

        # Reset flag returns 0 and clears session
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            code = main(["--reset", "--workspace", str(self.workspace), "--json"])
        self.assertEqual(code, 0)
        data = json.loads(stdout.getvalue())
        self.assertTrue(data.get("session_reset"))


class TestLangGraphSandboxNode(unittest.TestCase):
    """Test LangGraph node adapter and state transformations."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name).resolve()
        self.addCleanup(self.temp_dir.cleanup)

    @mock.patch("adapters.interop.langgraph_sandbox.execute_sandbox_command")
    def test_langgraph_node_execution(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "Graph node output\n",
            "timed_out": False,
            "duration_ms": 10,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
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
