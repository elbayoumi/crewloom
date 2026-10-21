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
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union
import uuid
import unicodedata

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
    if not hasattr(os, "getuid") or not hasattr(os, "getgid"):
        raise ValueError("Workflow containers require Linux, macOS or WSL; native Windows is not supported")
    uid = os.getuid()
    gid = os.getgid()
    if uid == 0:
        override = os.environ.get("CREWLOOM_CONTAINER_USER", "").strip()
        if override:
            if not re.fullmatch(r"[0-9]+:[0-9]+", override) or int(override.split(":")[0]) == 0:
                raise ValueError("CREWLOOM_CONTAINER_USER must specify unprivileged uid:gid (e.g. 10001:10001)")
            return override
        if os.environ.get("CREWLOOM_ALLOW_CONTAINER_ROOT") == "1":
            return "10001:10001"
        raise ValueError("Workflow containers refuse to run as root; execute as an unprivileged user or configure CREWLOOM_CONTAINER_USER / CREWLOOM_ALLOW_CONTAINER_ROOT")
    return f"{uid}:{gid}"


def _bind_mount(source: Union[str, Path], destination: str, readonly: bool = False) -> List[str]:
    """Build one --mount argument pair, rejecting comma-injection."""
    if "," in str(source) or "," in str(destination):
        raise ValueError("Docker mount paths cannot contain commas")
    return ["--mount", f"type=bind,src={source},dst={destination}" + (",readonly" if readonly else "")]


def _normalize_writable(writable: Optional[Sequence[str]]) -> Optional[Tuple[str, ...]]:
    """Freeze explicit path sequences without interpreting strings as individual grants."""
    if writable is None:
        return None
    if isinstance(writable, (str, bytes)) or not isinstance(writable, Sequence) or len(writable) > 128:
        raise ValueError("Writable paths must be a sequence of at most 128 relative paths")
    if any(not isinstance(path, str) or not path or "\0" in path for path in writable):
        raise ValueError("Expected workspace-relative writable path")
    return tuple(writable)


def _bound_policy(root: Path) -> Optional[Path]:
    """Find an explicitly selected policy without importing the host's runtime modules."""
    state = root / '.crewloom'
    binding = state / 'binding.json'
    if state.is_symlink() or binding.is_symlink():
        raise ValueError("Project binding must not use symlinks")
    if not binding.exists():
        return None
    if not binding.is_file() or binding.stat().st_nlink != 1 or binding.stat().st_size > 65536:
        raise ValueError("Invalid project binding")
    try:
        data = json.loads(binding.read_text(encoding='utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid project binding") from exc
    if not isinstance(data, dict) or data.get('project_root') != str(root):
        raise ValueError("Project binding belongs to another workspace")
    relative = data.get('config_path') or 'crewloom.project.json'
    if not isinstance(relative, str) or '\0' in relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError("Invalid bound project policy path")
    policy = (root / relative).resolve()
    if policy == root or not policy.is_relative_to(root):
        raise ValueError("Bound project policy escapes workspace")
    return policy


def _writable_paths(root: Path, writable: Optional[Sequence[str]]) -> List[Path]:
    """Validate the complete write set before creating any mount directories."""
    writable = _normalize_writable(writable)
    policy = _bound_policy(root) if writable else None
    policy_key = ('/'.join(unicodedata.normalize('NFC', part).casefold() for part in policy.relative_to(root).parts)
                  if policy else None)
    protected = {".git", ".crewloom", ".crewloom-repairs", ".codex", ".claude", ".opencode",
                 "crewloom.project.json", "repository_scope.json", "opencode.json", "opencode.jsonc"}
    paths = []
    keys = []
    inspected = 0
    for relative in writable or ():
        if not isinstance(relative, str) or not relative or "\0" in relative:
            raise ValueError("Expected workspace-relative writable path")
        rel = Path(relative)
        target = root / rel
        if rel.is_absolute() or ".." in rel.parts or target.resolve() == root or not target.resolve().is_relative_to(root):
            raise ValueError("Writable path escapes workspace: " + relative)
        for part in rel.parts:
            if part.casefold() in protected:
                raise ValueError("Writable path uses project control state: " + relative)
        current = root
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Writable paths cannot use symlinks: " + relative)
        # A directory grant includes every descendant, so inspect controls and aliases there too.
        pending = [target]
        while pending:
            candidate = pending.pop()
            inspected += 1
            if inspected > 10000:
                raise ValueError("Writable tree inspection budget exceeded")
            if candidate.name.casefold() in protected or candidate.is_symlink():
                raise ValueError("Writable tree contains control state or symlinks: " + relative)
            if candidate.exists():
                if candidate.is_file():
                    if candidate.stat().st_nlink != 1:
                        raise ValueError("Writable files cannot use hardlinks: " + relative)
                elif candidate.is_dir():
                    pending.extend(candidate.iterdir())
                else:
                    raise ValueError("Writable paths must be regular files or directories")
        key = '/'.join(unicodedata.normalize('NFC', part).casefold() for part in rel.parts)
        if policy_key is not None and (key == policy_key or policy_key.startswith(key + '/') or key.startswith(policy_key + '/')):
            raise ValueError("Writable path includes the bound project control file: " + relative)
        if any(key == other or key.startswith(other + '/') or other.startswith(key + '/') for other in keys):
            raise ValueError("Writable paths cannot overlap")
        paths.append(target)
        keys.append(key)
    return paths


def build_sandbox_command(
    root: Union[str, Path],
    argv: Sequence[str],
    image_id: str = "python:3.11-slim",
    name: Optional[str] = None,
    writable: Optional[Sequence[str]] = None,
) -> List[str]:
    """Build a read-only workspace; only explicit validated output paths are writable."""
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise ValueError(f"Workspace root must be an existing directory: {root}")
    if "," in str(root_path):
        raise ValueError("Workspace root path cannot contain commas")
    if not isinstance(image_id, str) or not image_id or image_id.startswith("-") or any(c.isspace() for c in image_id):
        raise ValueError("Expected an explicit Docker image reference")
    paths = _writable_paths(root_path, writable)
    crewloom_dir = root_path / ".crewloom"
    if crewloom_dir.is_symlink() or (crewloom_dir.exists() and not crewloom_dir.is_dir()):
        raise ValueError("Runtime state must be a directory without symlinks")
    # Construct every argument (including comma checks) before making directories.
    mounts = _bind_mount(root_path, "/workspace", readonly=True)
    for target in paths:
        mounts += _bind_mount(target, f"/workspace/{target.relative_to(root_path)}")
    user = _docker_user()
    for target in paths:
        if not target.exists():
            target.mkdir(parents=True, exist_ok=True)
    crewloom_dir.mkdir(mode=0o700, exist_ok=True)
    return [
        "docker", "run", "--rm", "--name", name or ("crewloom-crewai-" + uuid.uuid4().hex[:12]),
        *ISOLATION_FLAGS,
        "--user", user,
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
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise ValueError("Execution timeout must be between 1 and 3600 seconds")
    root_path = Path(root).resolve()
    container_name = "crewloom-crewai-" + uuid.uuid4().hex[:12]
    cmd = build_sandbox_command(root_path, argv, image_id=image_id, name=container_name, writable=writable)

    return _execute_container_command(cmd, container_name, image_id, timeout, cancellation_token)


def _execute_container_command(
    cmd: Sequence[str], container_name: str, image_id: str, timeout: int,
    cancellation_token: Any = None, remove: bool = True,
) -> Dict[str, Any]:
    """Collect bounded container output and destroy interrupted or one-shot executions."""
    if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
        raise ValueError("Execution timeout must be between 1 and 3600 seconds")
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
                    subprocess.run(["docker", "kill", container_name], capture_output=True, check=False, timeout=10)
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
                    subprocess.run(["docker", "kill", container_name], capture_output=True, check=False, timeout=10)
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
        if remove or timed_out or cancelled or discarded[0]:
            try:
                subprocess.run(["docker", "rm", "--force", container_name], capture_output=True, check=False, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if process.poll() is None:
            process.kill()
            process.wait()
        reader.join(timeout=5)
        if process.stdout:
            process.stdout.close()

    if discarded[0] and exit_code == 0:
        exit_code = 1
    duration_ms = round((time.monotonic() - started) * 1000)
    output = captured.decode("utf-8", errors="replace")
    suffix = (f"\n[Command timed out after {timeout} seconds]" if timed_out else
              "\n[Execution cancelled by user]" if cancelled else "")
    budget = 65536 - len(suffix.encode("utf-8"))
    encoded = output.encode("utf-8")
    if len(encoded) > budget:
        discarded[0] = True
        if exit_code == 0:
            exit_code = 1
    output = encoded[:budget].decode("utf-8", errors="ignore") + suffix
    if suffix:
        output = output.strip()

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
        self.writable = _normalize_writable(writable)
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
