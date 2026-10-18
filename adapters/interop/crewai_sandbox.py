"""Crewloom Interoperability Adapter for CrewAI.

Provides a drop-in zero-trust execution sandbox tool for CrewAI agents.
Runs all agent-generated code inside Crewloom's isolated container runtime:
- Non-root UID enforcement (refuses root execution)
- Airgapped network (--network none)
- Immutable read-only root filesystem (--read-only)
- Strict capability shedding (--cap-drop ALL, no-new-privileges)
- Bounded CPU, memory, PID, and file-size quotas
- Narrow project workspace bind mount with hidden runtime state

Zero external pip dependencies required; operates entirely using Python 3.9+ standard library.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import uuid

# Dynamically resolve scripts/ directory if workflow is not on sys.path
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if _SCRIPTS_DIR.is_dir() and str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    import workflow as _workflow
except ImportError:
    _workflow = None

ISOLATION_FLAGS: Tuple[str, ...] = (
    "--network", "none",
    "--read-only",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--pids-limit", "128",
    "--memory", "1g",
    "--cpus", "2",
    "--ulimit", "fsize=4194304:4194304",
)


def _docker_user() -> str:
    """Ensure workflow containers never run as root."""
    if _workflow is not None:
        return _workflow.docker_user()
    if not hasattr(os, "getuid") or not hasattr(os, "getgid"):
        raise ValueError("Workflow containers require Linux, macOS or WSL; native Windows is not supported")
    uid = os.getuid()
    gid = os.getgid()
    if uid == 0:
        override = os.environ.get("CREWLOOM_CONTAINER_USER", "").strip()
        if override:
            if not re.fullmatch(r"[0-9]+:[0-9]+", override) or override.startswith("0:"):
                raise ValueError("CREWLOOM_CONTAINER_USER must specify unprivileged uid:gid (e.g. 10001:10001)")
            return override
        if os.environ.get("CREWLOOM_ALLOW_CONTAINER_ROOT") == "1":
            return "10001:10001"
        raise ValueError("Workflow containers refuse to run as root; execute as an unprivileged user or configure CREWLOOM_CONTAINER_USER / CREWLOOM_ALLOW_CONTAINER_ROOT")
    return f"{uid}:{gid}"


def _bind_mount(source: Union[str, Path], destination: str, readonly: bool = False) -> List[str]:
    """Build one --mount argument pair, rejecting comma-injection."""
    if _workflow is not None:
        return _workflow.bind_mount(source, destination, readonly=readonly)
    if "," in str(source) or "," in str(destination):
        raise ValueError("Docker mount paths cannot contain commas")
    return ["--mount", f"type=bind,src={source},dst={destination}" + (",readonly" if readonly else "")]


def build_sandbox_command(
    root: Union[str, Path],
    argv: Sequence[str],
    image_id: str = "python:3.11-slim",
    name: Optional[str] = None,
    writable: Optional[Sequence[str]] = None,
) -> List[str]:
    """Construct the complete hardened `docker run` argv."""
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"Workspace root must be an existing directory: {root}")
    if "," in str(root_path):
        raise ValueError("Workspace root path cannot contain commas")

    container_name = name or ("crewloom-crewai-" + uuid.uuid4().hex[:12])
    crewloom_dir = root_path / ".crewloom"
    if not crewloom_dir.exists():
        try:
            crewloom_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    mounts = _bind_mount(root_path, "/workspace", readonly=writable is not None)

    for relative in writable or ():
        rel_path = Path(relative)
        if rel_path.is_absolute():
            raise ValueError(f"Expected workspace-relative writable path: {relative}")
        target = (root_path / rel_path).resolve()
        if not target.is_relative_to(root_path) or target == root_path:
            raise ValueError(f"Writable path escapes workspace: {relative}")
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
        mounts += _bind_mount(target, f"/workspace/{target.relative_to(root_path)}")

    return [
        "docker", "run", "--rm", "--name", container_name,
        *ISOLATION_FLAGS,
        "--user", _docker_user(),
        "--tmpfs", "/tmp:rw,nosuid,size=128m",
        "--tmpfs", "/workspace/.crewloom:ro,noexec,nosuid,size=1m",
        *mounts,
        "--workdir", "/workspace",
        "--env", "HOME=/tmp",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--env", "PYTHONUNBUFFERED=1",
        image_id,
        *argv,
    ]


def _is_cancelled(cancellation_token: Any) -> bool:
    """Inspect whether a cancellation token or event has been triggered."""
    if cancellation_token is None:
        return False
    if hasattr(cancellation_token, "is_cancelled"):
        val = cancellation_token.is_cancelled
        return bool(val() if callable(val) else val)
    if hasattr(cancellation_token, "is_set"):
        val = cancellation_token.is_set
        return bool(val() if callable(val) else val)
    if callable(cancellation_token):
        try:
            return bool(cancellation_token())
        except Exception:
            return False
    if isinstance(cancellation_token, bool):
        return cancellation_token
    return False


def execute_sandbox_command(
    root: Union[str, Path],
    argv: Sequence[str],
    image_id: str = "python:3.11-slim",
    timeout: int = 30,
    writable: Optional[Sequence[str]] = None,
    cancellation_token: Any = None,
) -> Dict[str, Any]:
    """Execute command in sandbox with timeout, active cancellation monitoring, and output capture."""
    root_path = Path(root).resolve()
    container_name = "crewloom-crewai-" + uuid.uuid4().hex[:12]
    cmd = build_sandbox_command(root_path, argv, image_id=image_id, name=container_name, writable=writable)

    started = time.monotonic()
    captured = bytearray()
    discarded = [False]
    timed_out = False
    cancelled = False
    exit_code = 1

    try:
        import threading
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        return {
            "exit_code": 127,
            "output": "Docker binary not found on PATH; container sandbox unavailable",
            "timed_out": False,
            "cancelled": False,
            "duration_ms": round((time.monotonic() - started) * 1000),
            "output_truncated": False,
            "isolation": "crewloom-airgap",
            "image_id": image_id,
        }

    def collect():
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                return
            available = max(0, 65536 - len(captured))
            captured.extend(chunk[:available])
            if len(chunk) > available:
                discarded[0] = True
                try:
                    subprocess.run(["docker", "kill", container_name], capture_output=True, check=False)
                except Exception:
                    pass

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()

    try:
        deadline = started + timeout
        while True:
            if _is_cancelled(cancellation_token):
                cancelled = True
                exit_code = 130
                try:
                    subprocess.run(["docker", "kill", container_name], capture_output=True, check=False)
                except Exception:
                    pass
                process.kill()
                process.wait()
                break
            try:
                remaining = max(0.01, deadline - time.monotonic())
                exit_code = process.wait(timeout=min(0.2, remaining))
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    exit_code = 124
                    timed_out = True
                    break
    finally:
        subprocess.run(["docker", "rm", "--force", container_name], capture_output=True, check=False)
        if process.poll() is None:
            process.kill()
            process.wait()
        reader.join(timeout=5)
        if process.stdout:
            process.stdout.close()

    duration_ms = round((time.monotonic() - started) * 1000)
    output = captured.decode("utf-8", errors="replace")
    if timed_out:
        output = (output + f"\n[Command timed out after {timeout} seconds]").strip()
    elif cancelled:
        output = (output + "\n[Execution cancelled by user]").strip()

    return {
        "exit_code": exit_code,
        "output": output,
        "timed_out": timed_out,
        "cancelled": cancelled,
        "duration_ms": duration_ms,
        "output_truncated": discarded[0],
        "isolation": "crewloom-airgap",
        "image_id": image_id,
    }


class CrewloomSandboxTool:
    """CrewAI-compatible tool for executing code inside Crewloom's zero-trust sandbox.

    Usage:
        sandbox = CrewloomSandboxTool(workspace_root="./my-project")
        result = sandbox.run("print('Hello from airgapped container!')")
    """

    name: str = "crewloom_sandbox"
    description: str = (
        "Execute Python scripts or shell commands safely inside Crewloom's isolated container "
        "sandbox with no network access, non-root permissions, and read-only filesystem."
    )

    def __init__(
        self,
        workspace_root: Union[str, Path] = ".",
        image_id: str = "python:3.11-slim",
        timeout: int = 30,
        writable: Optional[Sequence[str]] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.image_id = image_id
        self.timeout = timeout
        self.writable = tuple(writable) if writable is not None else None
        self.func = self.run  # Direct CrewAI agent tool protocol compatibility

    @property
    def func(self) -> Callable[[str], str]:
        """CrewAI agent builder validator compatibility."""
        return getattr(self, "_func", self.run)

    @func.setter
    def func(self, value: Callable[[str], str]) -> None:
        self._func = value

    def execute(
        self,
        code: str,
        language: str = "python",
        writable: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Execute code string and return structured execution metadata."""
        effective_writable = writable if writable is not None else self.writable
        if language in ("python", "python3", "py"):
            argv = ["python3", "-c", code]
        elif language in ("sh", "bash", "shell"):
            argv = ["/bin/sh", "-c", code]
        else:
            raise ValueError(f"Unsupported language: {language}. Supported: python, bash, sh")

        return execute_sandbox_command(
            root=self.workspace_root,
            argv=argv,
            image_id=self.image_id,
            timeout=self.timeout,
            writable=effective_writable,
        )

    def run(self, code: str, language: str = "python") -> str:
        """CrewAI tool entry point returning string output."""
        result = self.execute(code, language=language)
        if result["exit_code"] != 0:
            return f"[Execution failed (code {result['exit_code']})]:\n{result['output']}"
        return result["output"]

    def _run(self, code: str, language: str = "python") -> str:
        """Alias for CrewAI BaseTool interface."""
        return self.run(code, language=language)

    def __call__(self, code: str, language: str = "python") -> str:
        return self.run(code, language=language)

    def to_crewai_tool(self) -> Any:
        """Convert into a native CrewAI BaseTool instance if crewai is installed."""
        try:
            from crewai.tools import BaseTool
            from pydantic import Field
        except ImportError as exc:
            raise ImportError(
                "crewai is not installed. CrewloomSandboxTool can be used directly as a callable tool, "
                "or install crewai via `pip install crewai` to use native BaseTool wrapping."
            ) from exc

        parent_self = self

        class _NativeCrewAITool(BaseTool):
            name: str = parent_self.name
            description: str = parent_self.description

            def _run(self, code: str, language: str = "python") -> str:
                return parent_self.run(code, language=language)

        return _NativeCrewAITool()


def execute_in_sandbox(
    workspace_root: Union[str, Path],
    code: str,
    language: str = "python",
    writable: Optional[Sequence[str]] = None,
    timeout: int = 30,
    image_id: str = "python:3.11-slim",
) -> Dict[str, Any]:
    """Convenience helper to run code in the Crewloom container sandbox."""
    tool = CrewloomSandboxTool(
        workspace_root=workspace_root,
        image_id=image_id,
        timeout=timeout,
        writable=writable,
    )
    return tool.execute(code, language=language)
