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

import json
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

    def test_omitted_write_set_is_readonly(self):
        cmd = build_sandbox_command(self.workspace, ['python3', '-c', 'print(1)'])
        mounts = [cmd[i+1] for i, part in enumerate(cmd) if part == '--mount']
        self.assertEqual(mounts, [f'type=bind,src={self.workspace},dst=/workspace,readonly'])

    def test_control_paths_aliases_and_parent_grants_are_refused_before_writes(self):
        (self.workspace / 'output/.git').mkdir()
        for path in ('.git', '.GiT/config', '.crewloom', '.codex', 'crewloom.project.json',
                     'output', '../outside', '.', '/tmp'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_sandbox_command(self.workspace, ['python3'], writable=['new-output', path])
            self.assertFalse((self.workspace / 'new-output').exists())
        (self.workspace / 'alias').symlink_to(self.workspace / 'output', target_is_directory=True)
        with self.assertRaises(ValueError):
            build_sandbox_command(self.workspace, ['python3'], writable=['alias'])
        (self.workspace / 'source.txt').write_text('original')
        os.link(self.workspace / 'source.txt', self.workspace / 'output/linked.txt')
        (self.workspace / 'output/.git').rmdir()
        with self.assertRaisesRegex(ValueError, 'hardlinks'):
            build_sandbox_command(self.workspace, ['python3'], writable=['output'])


    def test_all_adapters_reject_non_sequence_write_grants_before_side_effects(self):
        before = sorted(self.workspace.rglob("*"))
        for factory in (CrewloomSandboxTool, CrewloomAutoGenExecutor, CrewloomLangGraphNode):
            for invalid in ('out', b'out', ['out', 4], [''], ['x\0y'], iter(['out']), 4):
                with self.subTest(adapter=factory.__name__, value=repr(invalid)):
                    with mock.patch('subprocess.Popen') as launch, mock.patch('subprocess.run') as run:
                        with self.assertRaises(ValueError):
                            factory(self.workspace, writable=invalid)
                        launch.assert_not_called()
                        run.assert_not_called()
                    self.assertEqual(sorted(self.workspace.rglob("*")), before)

    def test_alternate_bound_policy_cannot_be_a_write_grant(self):
        (self.workspace / 'config').mkdir()
        policy = self.workspace / 'config/custom.json'
        policy.write_text('{}')
        (self.workspace / '.crewloom').mkdir()
        binding = self.workspace / '.crewloom/binding.json'
        binding.write_text(json.dumps({'project_root': str(self.workspace), 'config_path': 'config/custom.json'}))
        for grant in ('config', 'config/custom.json', 'CONFIG/CUSTOM.JSON'):
            with self.subTest(grant=grant), self.assertRaisesRegex(ValueError, 'project control'):
                build_sandbox_command(self.workspace, ['python3'], writable=[grant])
        build_sandbox_command(self.workspace, ['python3'], writable=['config/result'])
        binding.write_text('invalid')
        with self.assertRaisesRegex(ValueError, 'Invalid project binding'):
            build_sandbox_command(self.workspace, ['python3'], writable=['output'])

    def test_invalid_timeout_does_not_create_outputs_or_start_a_container(self):
        with mock.patch('adapters.interop.crewai_sandbox.subprocess.Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'timeout'):
                execute_sandbox_command(self.workspace, ['python3'], timeout=0, writable=['new-output'])
        launch.assert_not_called()
        self.assertFalse((self.workspace / 'new-output').exists())

    def test_crewai_docker_user_fallback(self):
        import adapters.interop.crewai_sandbox as crewai_mod
        with mock.patch("os.getuid", return_value=0), mock.patch("os.getgid", return_value=0):
            # Valid override
            with mock.patch.dict(os.environ, {"CREWLOOM_CONTAINER_USER": "10005:10005"}):
                self.assertEqual(crewai_mod._docker_user(), "10005:10005")

            # Invalid root override
            with mock.patch.dict(os.environ, {"CREWLOOM_CONTAINER_USER": "00:0"}):
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

    def test_stateful_execution_delegates_without_host_history_replay(self):
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace, stateful=True)
        with mock.patch.object(executor._session, 'execute', return_value={'exit_code': 0, 'output': '42'}) as execute:
            result = executor.execute_code_blocks([CodeBlock('python', 'print(x)')])
        self.assertEqual(result.output, '42')
        execute.assert_called_once_with('print(x)', None)
        self.assertFalse((self.workspace / '.crewloom/autogen_session').exists())

    def test_restart_releases_the_owned_interpreter(self):
        executor = CrewloomAutoGenExecutor(workspace_root=self.workspace, stateful=True)
        with mock.patch.object(executor._session, 'close') as close:
            executor.restart()
        close.assert_called_once_with()

    def test_session_cannot_reuse_or_remove_a_foreign_container(self):
        executor = CrewloomAutoGenExecutor(self.workspace, stateful=True, session_id='owned')
        response = mock.Mock(returncode=0, stdout=json.dumps({'labels': {}, 'running': True}))
        with mock.patch('adapters.interop.autogen_sandbox.subprocess.run', return_value=response) as run:
            with self.assertRaisesRegex(ValueError, 'not owned'):
                executor.close()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][:2], ['docker', 'inspect'])

    def test_missing_session_recognizes_docker_error_case_variants(self):
        executor = CrewloomAutoGenExecutor(self.workspace, stateful=True, session_id='missing')
        for error in ('error: no such object: fixture', 'Error: No such container: fixture'):
            with self.subTest(error=error), mock.patch('adapters.interop.autogen_sandbox.subprocess.run',
                    return_value=mock.Mock(returncode=1, stderr=error)):
                self.assertIsNone(executor._session._inspect())

    def test_session_cleanup_reports_daemon_failures(self):
        executor = CrewloomAutoGenExecutor(self.workspace, stateful=True, session_id='unavailable')
        response = mock.Mock(returncode=1, stderr='Cannot connect to Docker daemon')
        with mock.patch('adapters.interop.autogen_sandbox.subprocess.run', return_value=response):
            with self.assertRaisesRegex(ValueError, 'Cannot inspect'):
                executor.close()

    def test_close_waits_for_owned_autoremove_but_keeps_other_errors_visible(self):
        executor = CrewloomAutoGenExecutor(self.workspace, stateful=True, session_id='race')
        session = executor._session
        session.started = True
        deleting = mock.Mock(returncode=1, stderr='removal of container fixture is already in progress')
        with mock.patch.object(session, '_inspect', side_effect=[{'running': True}, None]), \
                mock.patch('adapters.interop.autogen_sandbox.subprocess.run', return_value=deleting):
            executor.close()
        self.assertFalse(session.started)
        session.started = True
        with mock.patch.object(session, '_inspect', side_effect=[{'running': True}, ValueError('not owned')]), \
                mock.patch('adapters.interop.autogen_sandbox.subprocess.run', return_value=deleting):
            with self.assertRaisesRegex(ValueError, 'not owned'):
                executor.close()
        self.assertTrue(session.started)

    def test_unsupported_batch_is_refused_before_any_supported_prefix_executes(self):
        executor = CrewloomAutoGenExecutor(self.workspace)
        for language in ('ruby', None, 42):
            with self.subTest(language=language), \
                    mock.patch('adapters.interop.autogen_sandbox.execute_sandbox_command') as execute:
                result = executor.execute_code_blocks([CodeBlock('python', 'print(42)'), CodeBlock(language, 'x')])
                self.assertEqual(result.exit_code, 2)
                self.assertIn('Unsupported language', result.output)
                execute.assert_not_called()

    def test_native_async_cancellation_waits_for_worker_cleanup(self):
        import asyncio
        import threading
        import time
        started, finished = threading.Event(), threading.Event()
        executor = CrewloomAutoGenExecutor(self.workspace)

        def execute(*args, cancellation_token=None, **kwargs):
            started.set()
            deadline = time.monotonic() + 2
            from adapters.interop.crewai_sandbox import _is_cancelled
            while time.monotonic() < deadline and not _is_cancelled(cancellation_token):
                time.sleep(0.01)
            finished.set()
            return {'exit_code': 130, 'output': 'cancelled', 'cancelled': True}

        async def run():
            task = asyncio.create_task(executor.as_async_executor().execute_code_blocks([CodeBlock('python', 'x')]))
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            self.assertTrue(finished.is_set())

        with mock.patch('adapters.interop.autogen_sandbox.execute_sandbox_command', side_effect=execute):
            asyncio.run(run())

    def test_cancelled_session_admission_does_not_wait_for_another_block(self):
        import asyncio
        executor = CrewloomAutoGenExecutor(self.workspace, stateful=True)
        session = executor._session
        session._lock.acquire()

        async def run():
            task = asyncio.create_task(executor.a_execute_code_blocks([CodeBlock('python', 'x')]))
            await asyncio.sleep(0.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 1)

        try:
            with mock.patch.object(session, '_ensure') as ensure:
                asyncio.run(run())
                ensure.assert_not_called()
        finally:
            session._lock.release()

    def test_named_session_policy_changes_require_reset(self):
        executor = CrewloomAutoGenExecutor(self.workspace, stateful=True, session_id='policy')
        info = {'running': True, 'labels': {'crewloom.interop-policy': 'old-policy'}}
        with mock.patch.object(executor._session, '_inspect', return_value=info):
            result = executor.execute_code_blocks([CodeBlock('python', 'print(42)')])
        self.assertEqual(result.exit_code, 1)
        self.assertIn('reset', result.output)

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
        with patch("sys.stdout", stdout), patch("adapters.interop.autogen_sandbox._PythonSession.close"):
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

    @mock.patch("adapters.interop.langgraph_sandbox.execute_sandbox_command")
    def test_markdown_code_block_extraction(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "hello world\n",
            "timed_out": False,
            "duration_ms": 10,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
        node = CrewloomLangGraphNode(workspace_root=self.workspace)
        markdown_text = (
            "Here is the code:\n"
            "```python\n"
            "print('hello world')\n"
            "```\n"
            "End of message."
        )
        delta = node({"code": markdown_text, "language": "python"})
        self.assertIn("sandbox_result", delta)
        self.assertEqual(delta["sandbox_result"]["exit_code"], 0)
        # Verify markdown fences were stripped and raw python code was executed
        called_argv = mock_exec.call_args[1]["argv"]
        self.assertEqual(called_argv, ["python3", "-c", "print('hello world')"])

    def test_cancellation_token_in_state(self):
        node = CrewloomLangGraphNode(workspace_root=self.workspace)
        token = mock.MagicMock()
        token.is_cancelled = mock.MagicMock(return_value=True)

        delta = node({"code": "print('should not run')", "cancellation_token": token})
        res = delta["sandbox_result"]
        self.assertEqual(res["exit_code"], 130)
        self.assertTrue(res["cancelled"])
        self.assertIn("cancelled by user", res["output"])

    def test_unsupported_language_never_runs_as_python(self):
        node = CrewloomLangGraphNode(self.workspace)
        for language in ('ruby', 42, None, []):
            with self.subTest(language=language), \
                    mock.patch('adapters.interop.langgraph_sandbox.execute_sandbox_command') as execute:
                result = node({'code': 'print(42)', 'language': language})['sandbox_result']
                self.assertEqual(result['exit_code'], 2)
                self.assertIn('Unsupported language', result['output'])
                execute.assert_not_called()

    @mock.patch("adapters.interop.langgraph_sandbox.execute_sandbox_command")
    def test_messages_fallback(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "message output\n",
            "timed_out": False,
            "duration_ms": 10,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
        node = CrewloomLangGraphNode(workspace_root=self.workspace)
        delta = node({"messages": [{"content": "print('message output')"}]})
        self.assertIn("sandbox_result", delta)
        self.assertEqual(delta["sandbox_result"]["exit_code"], 0)
        called_argv = mock_exec.call_args[1]["argv"]
        self.assertEqual(called_argv, ["python3", "-c", "print('message output')"])

    def test_langgraph_cli_runner(self):
        from adapters.interop.langgraph_sandbox import main
        import io
        from unittest.mock import patch

        with patch("adapters.interop.langgraph_sandbox.execute_sandbox_command") as mock_exec:
            mock_exec.return_value = {
                "exit_code": 0,
                "output": "LangGraph CLI",
                "timed_out": False,
                "cancelled": False,
                "duration_ms": 5,
                "output_truncated": False,
                "isolation": "crewloom-airgap",
                "image_id": "python:3.11-slim",
            }
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                code = main(["--code", "print('LangGraph CLI')", "--workspace", str(self.workspace), "--json"])
            self.assertEqual(code, 0)
            data = json.loads(stdout.getvalue())
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["output"], "LangGraph CLI")

        # Missing code/file argument returns 2
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--workspace", str(self.workspace)])
        self.assertEqual(code, 2)

        # File not found returns 2
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["--file", "nonexistent.py", "--workspace", str(self.workspace)])
        self.assertEqual(code, 2)

    @mock.patch("adapters.interop.langgraph_sandbox.execute_sandbox_command")
    def test_raw_code_with_internal_markdown_literal_preserved(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "literal printed\n",
            "timed_out": False,
            "duration_ms": 10,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
        node = CrewloomLangGraphNode(workspace_root=self.workspace)
        raw_code = 'print("""```python\\nprint(999)\\n```""")'
        delta = node({"code": raw_code, "language": "python"})
        self.assertIn("sandbox_result", delta)
        called_argv = mock_exec.call_args[1]["argv"]
        # Raw program must be preserved verbatim, not truncated to print(999)
        self.assertEqual(called_argv, ["python3", "-c", raw_code])

    @mock.patch("adapters.interop.langgraph_sandbox.execute_sandbox_command")
    def test_positional_factory_arguments_compatibility(self, mock_exec):
        mock_exec.return_value = {
            "exit_code": 0,
            "output": "positional ok\n",
            "timed_out": False,
            "duration_ms": 5,
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": "python:3.11-slim",
        }
        # Positional arguments: workspace_root, image_id, timeout, writable, input_key, output_key
        node = create_crewloom_sandbox_node(
            self.workspace,
            "python:3.11-slim",
            30,
            None,
            "custom_code",
            "custom_output",
        )
        delta = node({"custom_code": "print('positional test')"})
        self.assertIn("custom_output", delta)
        self.assertEqual(delta["custom_output"]["exit_code"], 0)


@unittest.skipUnless(os.environ.get('CREWLOOM_DOCKER_TESTS') == '1',
                     'Enable actual interop Docker acceptance explicitly')
class TestActualInteropDocker(unittest.TestCase):
    """Observe real mounts and interpreter side effects instead of mocked argv alone."""

    def setUp(self):
        import subprocess
        available = subprocess.run(['docker', 'image', 'inspect', 'python:3.14-slim'],
                                   capture_output=True, timeout=10)
        self.assertEqual(available.returncode, 0, 'Pull python:3.14-slim for explicit acceptance')
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / 'out').mkdir()
        (self.root / '.git').mkdir()
        (self.root / '.git' / 'control').write_text('original')
        (self.root / 'source.txt').write_text('original')

    def test_default_mount_refuses_source_and_git_writes_for_all_adapters(self):
        code = '''from pathlib import Path
for name in ('source.txt', '.git/control'):
    try:
        Path(name).write_text('changed')
    except OSError:
        pass
    else:
        raise AssertionError('write was allowed: ' + name)
print('refused')'''
        tool = CrewloomSandboxTool(self.root, image_id='python:3.14-slim')
        self.assertEqual(tool.execute(code)['exit_code'], 0)
        executor = CrewloomAutoGenExecutor(self.root, image_id='python:3.14-slim')
        self.assertEqual(executor.execute_code_blocks([CodeBlock('python', code)]).exit_code, 0)
        node = CrewloomLangGraphNode(self.root, image_id='python:3.14-slim')
        self.assertEqual(node({'code': code})['sandbox_result']['exit_code'], 0)
        self.assertEqual((self.root / 'source.txt').read_text(), 'original')
        self.assertEqual((self.root / '.git/control').read_text(), 'original')

    def test_explicit_output_is_writable_and_runtime_is_hidden(self):
        (self.root / '.crewloom').mkdir()
        (self.root / '.crewloom/private.txt').write_text('private fixture')
        result = execute_sandbox_command(self.root, ['python3', '-c',
            "from pathlib import Path; assert not Path('.crewloom/private.txt').exists(); "
            "Path('out/result.txt').write_text('accepted')"],
            image_id='python:3.14-slim', writable=['out'])
        self.assertEqual(result['exit_code'], 0, result['output'])
        self.assertEqual((self.root / 'out/result.txt').read_text(), 'accepted')

    def test_stateful_functions_imports_and_files_are_not_replayed(self):
        with CrewloomAutoGenExecutor(self.root, image_id='python:3.14-slim',
                                     writable=['out'], stateful=True) as executor:
            first = executor.execute_code_blocks([CodeBlock('python',
                "from pathlib import Path\nimport math\nx=42\n"
                "def twice(value): return value*2\n"
                "with Path('out/counter.txt').open('a') as f: f.write('x')")])
            self.assertEqual(first.exit_code, 0, first.output)
            second = executor.execute_code_blocks([CodeBlock('python', 'print(twice(x), math.sqrt(9))')])
            self.assertEqual(second.exit_code, 0, second.output)
            self.assertEqual(second.output, '84 3.0')
            self.assertEqual((self.root / 'out/counter.txt').read_text(), 'x')
            # Failures are visible and never trigger history replay either.
            failed = executor.execute_code_blocks([CodeBlock('python', "raise ValueError('visible failure')")])
            self.assertEqual(failed.exit_code, 1)
            self.assertIn('visible failure', failed.output)
            self.assertEqual(executor.execute_code_blocks([CodeBlock('python', 'print(x)')]).output, '42')
            name = executor._session.name
        import subprocess
        self.assertNotEqual(subprocess.run(['docker', 'inspect', name], capture_output=True).returncode, 0)

    def test_timeout_and_reset_do_not_replay_or_silently_recover_state(self):
        with CrewloomAutoGenExecutor(self.root, image_id='python:3.14-slim',
                                     timeout=1, stateful=True) as executor:
            self.assertEqual(executor.execute_code_blocks([CodeBlock('python', 'x=42')]).exit_code, 0)
            timed_out = executor.execute_code_blocks([CodeBlock('python', 'import time; time.sleep(30)')])
            self.assertEqual(timed_out.exit_code, 124, timed_out.output)
            lost = executor.execute_code_blocks([CodeBlock('python', 'print(x)')])
            self.assertEqual(lost.exit_code, 1)
            self.assertIn('reset', lost.output)
            executor.restart()
            fresh = executor.execute_code_blocks([CodeBlock('python', 'print("x" in globals())')])
            self.assertEqual(fresh.output, 'False')

    def test_cancellation_destroys_only_the_owned_session(self):
        import threading
        with CrewloomAutoGenExecutor(self.root, image_id='python:3.14-slim', stateful=True) as executor:
            self.assertEqual(executor.execute_code_blocks([CodeBlock('python', 'x=42')]).exit_code, 0)
            event = threading.Event()
            timer = threading.Timer(0.2, event.set)
            timer.start()
            try:
                cancelled = executor.execute_code_blocks(
                    [CodeBlock('python', 'import time; time.sleep(30)')], cancellation_token=event)
            finally:
                timer.cancel()
            self.assertEqual(cancelled.exit_code, 130, cancelled.output)
            self.assertIn('reset', executor.execute_code_blocks([CodeBlock('python', 'print(x)')]).output)

    def test_replaced_workspace_cannot_reuse_old_mounts_or_python_state(self):
        project = self.root / 'project'
        project.mkdir()
        with CrewloomAutoGenExecutor(project, image_id='python:3.14-slim', stateful=True) as executor:
            first = executor.execute_code_blocks([CodeBlock('python', 'x=42')])
            self.assertEqual(first.exit_code, 0, first.output)
            project.rename(self.root / 'previous-project')
            project.mkdir()
            result = executor.execute_code_blocks([CodeBlock('python', 'print(x)')])
            self.assertEqual(result.exit_code, 1)
            self.assertIn('reset', result.output)

    def test_stateful_captures_child_and_raw_output_with_a_bounded_result(self):
        import subprocess
        with CrewloomAutoGenExecutor(self.root, image_id='python:3.14-slim', stateful=True) as executor:
            result = executor.execute_code_blocks([CodeBlock('python',
                "import os, subprocess; subprocess.run(['python3', '-c', \"import sys; print('CHILD'); print('ERR',file=sys.stderr)\"],check=True); os.write(1,b'RAW'); os.write(2,b'RAWERR')")])
            self.assertEqual(result.exit_code, 0, result.output)
            for marker in ('CHILD', 'ERR', 'RAW', 'RAWERR'):
                self.assertIn(marker, result.output)
            flooded = executor.execute_code_blocks([CodeBlock('python', "os.write(1,b'Z'*131072)")])
            self.assertNotEqual(flooded.exit_code, 0)
            self.assertLessEqual(len(flooded.output.encode()), 32768)
            self.assertIn('output limit exceeded', flooded.output)
            invalid = executor.execute_code_blocks([CodeBlock('python', "os.write(2,b'\\xff'*32768)")])
            self.assertNotEqual(invalid.exit_code, 0)
            self.assertLessEqual(len(invalid.output.encode()), 32768)
            self.assertEqual(executor.execute_code_blocks([CodeBlock('python', "print('alive')")]).output, 'alive')
            info = subprocess.run(['docker', 'inspect', '--format', '{{.HostConfig.LogConfig.Type}}',
                                   executor._session.name], capture_output=True, text=True, timeout=10)
            self.assertEqual(info.stdout.strip(), 'none')
            logs = subprocess.run(['docker', 'logs', executor._session.name], capture_output=True, timeout=10)
            self.assertNotIn(b'Z' * 1024, logs.stdout + logs.stderr)

    def test_real_autogen_agent_uses_async_executor_without_a_model(self):
        if os.environ.get('CREWLOOM_AUTOGEN_TESTS') != '1':
            self.skipTest('Enable official AutoGen SDK acceptance explicitly')
        import asyncio
        # Missing dependencies fail this explicitly requested test rather than skipping silently.
        from autogen_agentchat.agents import CodeExecutorAgent
        from autogen_agentchat.messages import TextMessage
        from autogen_core import CancellationToken

        async def run():
            with CrewloomAutoGenExecutor(self.root, image_id='python:3.14-slim', stateful=True) as sync:
                async with sync.as_async_executor() as executor:
                    agent = CodeExecutorAgent('runner', code_executor=executor)
                    response = await agent.on_messages(
                        [TextMessage(content="```python\nx=42; print(x)\n```", source='user')], CancellationToken())
                    self.assertEqual(response.chat_message.content, '42')
                    await executor.restart()
                    response = await agent.on_messages(
                        [TextMessage(content="```python\nprint(x)\n```", source='user')], CancellationToken())
                    self.assertIn('NameError', response.chat_message.content)
        asyncio.run(run())

    def test_stateless_utf8_return_budget_includes_replacement_expansion(self):
        for count in (32768, 65536):
            result = execute_sandbox_command(self.root, ['python3', '-c',
                "import os; os.write(1,b'\\xff'*%d)" % count], image_id='python:3.14-slim')
            self.assertNotEqual(result['exit_code'], 0)
            self.assertTrue(result['output_truncated'])
            self.assertLessEqual(len(result['output'].encode('utf-8')), 65536)
        valid = execute_sandbox_command(self.root, ['python3', '-c',
            "import os; os.write(1,('é'*32768).encode())"], image_id='python:3.14-slim')
        self.assertEqual(valid['exit_code'], 0)
        self.assertFalse(valid['output_truncated'])
        self.assertEqual(len(valid['output'].encode()), 65536)

    def test_native_async_cancellation_destroys_the_running_container(self):
        import asyncio
        import subprocess

        async def run():
            with CrewloomAutoGenExecutor(self.root, image_id='python:3.14-slim',
                                         writable=['out'], stateful=True) as executor:
                code = "from pathlib import Path; import time; Path('out/started').touch(); time.sleep(20)"
                task = asyncio.create_task(executor.a_execute_code_blocks([CodeBlock('python', code)]))
                try:
                    for _ in range(100):
                        if (self.root / 'out/started').exists():
                            break
                        await asyncio.sleep(0.05)
                    self.assertTrue((self.root / 'out/started').exists())
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(task, 5)
                    info = subprocess.run(['docker', 'inspect', executor._session.name], capture_output=True, timeout=5)
                    self.assertNotEqual(info.returncode, 0)
                finally:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
        asyncio.run(run())

    def test_named_cli_session_persists_and_reset_removes_it(self):
        import subprocess
        command = [sys.executable, '-m', 'adapters.interop.autogen_sandbox', '--workspace', str(self.root),
                   '--image', 'python:3.14-slim', '--session', 'acceptance', '--json']
        def invoke(*args):
            result = subprocess.run(command + list(args), cwd=_REPO_ROOT, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertNotIn('RuntimeWarning', result.stderr)
            return json.loads(result.stdout)
        try:
            invoke('--stateful', '--code', 'x=42')
            self.assertEqual(invoke('--stateful', '--code', 'print(x)')['output'], '42')
        finally:
            invoke('--reset')


if __name__ == "__main__":
    unittest.main()
