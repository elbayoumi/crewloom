"""Crewloom Interoperability Adapter for Microsoft AutoGen.

Provides an isolated synchronous code executor and an explicit async adapter.
AutoGen 0.4 CodeExecutorAgent requires executor.as_async_executor().

Supports:
- Stateless and stateful session code execution across blocks
- Cancellation token inspection (AutoGen 0.4 and threading/asyncio events)
- Safe isolation with zero external dependencies (Python 3.9+ standard library only)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import atexit
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import uuid
import re
import sys
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Union

from .crewai_sandbox import (build_sandbox_command, execute_sandbox_command,
                             _execute_container_command, _is_cancelled, _normalize_writable)


class CommandLineCodeResult(NamedTuple):
    """Result of code execution matching AutoGen's CommandLineCodeResult specification."""

    exit_code: int
    output: str


@dataclass(frozen=True)
class CodeBlock:
    """Represents a single executable code block."""

    language: str
    code: str


_CODE_BLOCK_PATTERN = re.compile(r"```(?P<lang>[a-zA-Z0-9_\-\+]*)\n(?P<code>.*?)```", re.DOTALL)


def extract_code_blocks(content: str) -> List[CodeBlock]:
    """Extract code blocks from markdown text with fallback for plain text."""
    matches = list(_CODE_BLOCK_PATTERN.finditer(content))
    if not matches:
        return []
    blocks: List[CodeBlock] = []
    for match in matches:
        lang = (match.group("lang") or "python").strip().lower()
        code = match.group("code").strip()
        if code:
            blocks.append(CodeBlock(language=lang, code=code))
    return blocks


_SESSION_SERVER = r'''
import contextlib, io, json, os, select, socket, sys, threading, time, traceback

class Output:
    """Capture file descriptors as well as Python streams, retaining at most 32 KiB."""
    def __init__(self):
        self.data = bytearray()
        self.overflow = False
        self.finished = threading.Event()
    def drain(self):
        deadline = None
        try:
            while True:
                if self.finished.is_set():
                    deadline = deadline or time.monotonic() + 0.1
                    if time.monotonic() >= deadline:
                        break
                if select.select([self.reader], [], [], 0.02)[0]:
                    raw = os.read(self.reader, 8192)
                    if not raw:
                        break
                    left = 32768 - len(self.data)
                    self.data.extend(raw[:left])
                    if len(raw) > left:
                        self.overflow = True
        finally:
            os.close(self.reader)
    def __enter__(self):
        sys.stdout.flush()
        sys.stderr.flush()
        self.saved = [os.dup(1), os.dup(2)]
        self.reader, writer = os.pipe()
        os.dup2(writer, 1)
        os.dup2(writer, 2)
        os.close(writer)
        self.stream = io.TextIOWrapper(os.fdopen(os.dup(1), 'wb', buffering=0),
                                       encoding='utf-8', errors='replace', write_through=True)
        self.thread = threading.Thread(target=self.drain, daemon=True)
        self.thread.start()
        return self.stream
    def __exit__(self, *exc):
        try:
            self.stream.close()
        finally:
            for fd, saved in zip((1, 2), self.saved):
                os.dup2(saved, fd)
                os.close(saved)
            self.finished.set()
            self.thread.join()

namespace = {'__name__': '__main__'}
server = socket.socket(socket.AF_UNIX)
server.bind('/tmp/crewloom-session.sock')
server.listen(8)
while True:
    connection, _ = server.accept()
    with connection:
        reader = connection.makefile('rb')
        line = reader.readline(524289)
        if len(line) > 524288:
            continue
        request = json.loads(line)
        output = Output()
        code = 0
        with output as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            try:
                exec(compile(request['code'], '<autogen-session>', 'exec'), namespace)
            except BaseException as exc:
                code = 0 if isinstance(exc, SystemExit) and exc.code in (0, None) else 1
                if code:
                    traceback.print_exc()
        encoded = output.data.decode('utf-8', 'replace').encode('utf-8')
        output.overflow = output.overflow or len(encoded) > 32768
        output.data = encoded[:32768].decode('utf-8', 'ignore').encode('utf-8')
        if output.overflow:
            code = 1
            message = b'\n[Session output limit exceeded (32768 bytes)]'
            output.data = output.data[:32768 - len(message)].decode('utf-8', 'ignore').encode('utf-8') + message
        result = {'exit_code': code, 'output': output.data.decode('utf-8', 'replace')}
        connection.sendall(json.dumps(result, ensure_ascii=False).encode() + b'\n')
'''

_SESSION_CLIENT = r'''
import base64, json, socket, sys, time
connection = socket.socket(socket.AF_UNIX)
for attempt in range(100):
    try:
        connection.connect('/tmp/crewloom-session.sock')
        break
    except (FileNotFoundError, ConnectionRefusedError):
        time.sleep(0.05)
else:
    raise RuntimeError('Python session is unavailable; reset the session')
code = base64.b64decode(sys.argv[1]).decode('utf-8')
connection.sendall(json.dumps({'code': code}, ensure_ascii=False).encode() + b'\n')
line = connection.makefile('rb').readline(524289)
if not line or len(line) > 524288:
    raise RuntimeError('Python session ended unexpectedly; reset the session')
result = json.loads(line)
sys.stdout.write(result['output'])
sys.exit(result['exit_code'])
'''


class _PythonSession:
    """Keep Python state inside one isolated container, never by replaying commands."""

    def __init__(self, root, image, timeout, writable, session_id=None):
        if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 3600:
            raise ValueError('Execution timeout must be between 1 and 3600 seconds')
        if session_id is not None and (not isinstance(session_id, str) or not session_id or len(session_id) > 128):
            raise ValueError('Session ID must contain 1 to 128 characters')
        self.root = root
        self.image = image
        self.timeout = timeout
        self.writable = writable
        self.persistent = session_id is not None
        key = json.dumps([str(root), os.getuid(), session_id or uuid.uuid4().hex])
        self.identity = hashlib.sha256(key.encode()).hexdigest()
        self.name = 'crewloom-autogen-' + self.identity[:24]
        self.started = False
        self._lock = threading.Lock()
        if not self.persistent:
            atexit.register(self._cleanup)

    @property
    def policy(self):
        """Bind persistent mounts to their actual filesystem objects as well as path names."""
        if not self.root.is_dir():
            raise ValueError('Session workspace is unavailable; reset the session')
        bindings = []
        for path in [self.root, *[self.root / item for item in self.writable or ()]]:
            stat = path.stat() if path.exists() else None
            bindings.append([str(path), [stat.st_dev, stat.st_ino] if stat else None])
        value = json.dumps([self.image, list(self.writable or ()), bindings, _SESSION_SERVER])
        return hashlib.sha256(value.encode()).hexdigest()

    def _inspect(self):
        """Inspect only bounded identity metadata, never trust a matching container name."""
        result = subprocess.run(
            ['docker', 'inspect', '--format',
             '{"labels":{{json .Config.Labels}},"running":{{json .State.Running}}}', self.name],
            capture_output=True, text=True, timeout=10)
        if result.returncode:
            if 'no such object' in result.stderr.casefold() or 'no such container' in result.stderr.casefold():
                return None
            raise ValueError('Cannot inspect Python session: ' + result.stderr[-1000:])
        info = json.loads(result.stdout)
        labels = info.get('labels') or {}
        if labels.get('crewloom.interop-session') != self.identity:
            raise ValueError('Session container is not owned by this executor')
        return info

    def _ensure(self):
        """Start lazily, or validate an explicitly named CLI session before reuse."""
        # Revalidate write boundaries even when a named container already exists.
        from .crewai_sandbox import _writable_paths
        _writable_paths(self.root, self.writable)
        info = self._inspect()
        if info is not None:
            if (not info['running'] or
                    info['labels'].get('crewloom.interop-policy') != self.policy):
                raise ValueError('Session policy changed or interpreter stopped; reset the session')
            self.started = True
            return
        if self.started:
            raise ValueError('Python session was lost; reset it before continuing')
        cmd = build_sandbox_command(self.root, ['python3', '-u', '-c', _SESSION_SERVER],
                                    image_id=self.image, name=self.name, writable=self.writable)
        cmd[2:2] = ['--detach', '--log-driver', 'none', '--label', 'crewloom.interop-session=' + self.identity,
                     '--label', 'crewloom.interop-policy=' + self.policy]
        started = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if started.returncode:
            raise ValueError('Cannot start Python session: ' + started.stderr[-2000:])
        self.started = True

    def execute(self, code, cancellation_token=None):
        """Execute one block once; timeout/cancellation destroys the interpreter."""
        import base64
        if len(code.encode('utf-8')) > 65536:
            raise ValueError('Stateful Python blocks are limited to 65536 UTF-8 bytes')
        while not self._lock.acquire(timeout=0.1):
            if _is_cancelled(cancellation_token):
                return {'exit_code': 130, 'output': 'Execution cancelled before session admission',
                        'cancelled': True}
        try:
            if _is_cancelled(cancellation_token):
                return {'exit_code': 130, 'output': 'Execution cancelled before session admission',
                        'cancelled': True}
            self._ensure()
            encoded = base64.b64encode(code.encode()).decode('ascii')
            cmd = ['docker', 'exec', self.name, 'python3', '-c', _SESSION_CLIENT, encoded]
            return _execute_container_command(cmd, self.name, self.image, self.timeout,
                                              cancellation_token, remove=False)
        finally:
            self._lock.release()

    def close(self):
        """Remove only this executor's verified container; never deserialize host history."""
        with self._lock:
            if self.started or self.persistent:
                info = self._inspect()
                if info is not None:
                    result = subprocess.run(['docker', 'rm', '--force', self.name],
                                            capture_output=True, text=True, timeout=10)
                    if result.returncode:
                        error = result.stderr.casefold()
                        removal_race = ('removal' in error and 'already in progress' in error)
                        missing = 'no such container' in error or 'no such object' in error
                        if not (removal_race or missing):
                            raise ValueError('Cannot close Python session: ' + result.stderr[-1000:])
                        # --rm and explicit teardown can overlap after interruption.
                        # Re-inspection still verifies ownership; never hide daemon errors
                        # or report a successful close while the container remains.
                        import time
                        for _ in range(20):
                            if self._inspect() is None:
                                break
                            time.sleep(0.1)
                        else:
                            raise ValueError('Python session removal is still in progress; retry close')
            self.started = False

    def _cleanup(self):
        """Best-effort process-exit cleanup for object-scoped sessions only."""
        try:
            self.close()
        except (OSError, ValueError, subprocess.SubprocessError):
            pass


class CrewloomAutoGenExecutor:
    """Microsoft AutoGen-compatible CodeExecutor backed by Crewloom's isolated container runtime.

    Features:
    - Stateless or stateful session execution preserving variables across code blocks
    - Cancellation token integration for graceful task interruption (exit code 130)
    - Zero external runtime dependencies

    Usage:
        from adapters.interop.autogen_sandbox import CrewloomAutoGenExecutor, CodeBlock

        executor = CrewloomAutoGenExecutor(workspace_root="./project", stateful=True)
        result = executor.execute_code_blocks([CodeBlock(language="python", code="x = 42")])
        result2 = executor.execute_code_blocks([CodeBlock(language="python", code="print(x * 2)")])
        print(result2.output)  # 84
    """

    def __init__(
        self,
        workspace_root: Union[str, Path] = ".",
        image_id: str = "python:3.11-slim",
        timeout: int = 30,
        writable: Optional[Sequence[str]] = None,
        stateful: bool = False,
        session_id: Optional[str] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.image_id = image_id
        self.timeout = timeout
        self.writable = _normalize_writable(writable)
        self.stateful = stateful
        self._session = (_PythonSession(self.workspace_root, image_id, timeout, self.writable, session_id)
                         if stateful else None)

    def execute_code_blocks(
        self,
        code_blocks: Sequence[Any],
        cancellation_token: Any = None,
    ) -> CommandLineCodeResult:
        """Execute a sequence of code blocks and return aggregated result.

        Synchronous interface. Use as_async_executor() for AutoGen 0.4 agents.
        """
        if _is_cancelled(cancellation_token):
            return CommandLineCodeResult(exit_code=130, output="Execution cancelled by user")

        blocks: List[CodeBlock] = []

        if isinstance(code_blocks, str):
            blocks = extract_code_blocks(code_blocks)
            if not blocks:
                # If raw string without code fences, treat as python
                blocks = [CodeBlock(language="python", code=code_blocks)]
        else:
            for item in code_blocks:
                if isinstance(item, CodeBlock):
                    blocks.append(item)
                elif hasattr(item, "code") and hasattr(item, "language"):
                    blocks.append(CodeBlock(language=str(item.language), code=str(item.code)))
                elif isinstance(item, (tuple, list)) and len(item) >= 2:
                    blocks.append(CodeBlock(language=str(item[0]), code=str(item[1])))
                elif isinstance(item, dict) and "code" in item:
                    blocks.append(CodeBlock(language=str(item.get("language", "python")), code=str(item["code"])))

        if not blocks:
            return CommandLineCodeResult(exit_code=0, output="No executable code blocks found.")

        # Refuse the whole request before executing any supported prefix.
        for block in blocks:
            if not isinstance(block.language, str) or block.language.lower() not in (
                    "python", "python3", "py", "bash", "sh", "shell"):
                return CommandLineCodeResult(2, f"Unsupported language: {block.language}")
        combined_outputs: List[str] = []

        for idx, block in enumerate(blocks):
            if _is_cancelled(cancellation_token):
                combined_output = "\n".join(combined_outputs)
                return CommandLineCodeResult(
                    exit_code=130,
                    output=f"{combined_output}\n[Execution cancelled before block {idx + 1}]".strip(),
                )

            lang = block.language.lower()
            if lang in ("python", "python3", "py"):
                argv = ["python3", "-c", block.code]
            elif lang in ("bash", "sh", "shell"):
                argv = ["/bin/sh", "-c", block.code]

            try:
                if self._session is not None and lang in ("python", "python3", "py"):
                    result = self._session.execute(block.code, cancellation_token)
                else:
                    result = execute_sandbox_command(
                        root=self.workspace_root, argv=argv, image_id=self.image_id,
                        timeout=self.timeout, writable=self.writable, cancellation_token=cancellation_token)
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                return CommandLineCodeResult(1, "\n".join(combined_outputs + [str(exc)]))

            output = result["output"].strip()
            if output:
                combined_outputs.append(output)

            if result.get("cancelled") or result["exit_code"] == 130:
                combined_output = "\n".join(combined_outputs)
                return CommandLineCodeResult(
                    exit_code=130,
                    output=combined_output or "Execution cancelled by user",
                )

            if result["exit_code"] != 0:
                combined_output = "\n".join(combined_outputs)
                return CommandLineCodeResult(
                    exit_code=result["exit_code"],
                    output=combined_output or f"Command failed with exit code {result['exit_code']}",
                )

        return CommandLineCodeResult(exit_code=0, output="\n".join(combined_outputs))

    def as_async_executor(self) -> "CrewloomAsyncAutoGenExecutor":
        """Expose AutoGen 0.4's awaited execute_code_blocks method explicitly."""
        return CrewloomAsyncAutoGenExecutor(self)

    def close(self) -> None:
        """Release this executor's Python container and its in-memory state."""
        if self._session is not None:
            self._session.close()

    def restart(self) -> None:
        """Discard interpreter state; the next block starts a new isolated session."""
        self.close()

    def __enter__(self):
        """Support explicit session ownership with a context manager."""
        return self

    def __exit__(self, *exc):
        """Always release an object-scoped container at the end of a with block."""
        self.close()

    async def a_execute_code_blocks(
        self,
        code_blocks: Sequence[Any],
        cancellation_token: Any = None,
    ) -> CommandLineCodeResult:
        """Async convenience method; AutoGen 0.4 agents use as_async_executor()."""
        import asyncio
        if _is_cancelled(cancellation_token):
            return CommandLineCodeResult(exit_code=130, output="Execution cancelled by user")
        # Shield the worker so cancelling the await does not detach a running container.
        interrupted = threading.Event()

        class Token:
            def is_cancelled(self):
                return interrupted.is_set() or _is_cancelled(cancellation_token)

        worker = asyncio.create_task(asyncio.to_thread(self.execute_code_blocks, code_blocks, Token()))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            interrupted.set()
            # Keep cleanup owned even if the caller cancels repeatedly while Docker exits.
            while not worker.done():
                try:
                    await asyncio.shield(worker)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            # Retrieve a worker exception without replacing the caller's cancellation.
            try:
                worker.result()
            except Exception:
                pass
            raise



class CrewloomAsyncAutoGenExecutor:
    """AutoGen 0.4 CodeExecutorAgent interface sharing one synchronous executor.

    Framework serialization is not provided. Lifecycle and state belong to the
    wrapped executor; use stop() or its context manager to release the container.
    """

    def __init__(self, executor: CrewloomAutoGenExecutor):
        self.executor = executor

    async def execute_code_blocks(self, code_blocks, cancellation_token=None):
        """Run the blocking Docker operation off the agent event loop."""
        return await self.executor.a_execute_code_blocks(code_blocks, cancellation_token)

    async def start(self):
        """Containers start lazily when the first code block is executed."""

    async def stop(self):
        """Release the wrapped executor's session off the event loop."""
        import asyncio
        await asyncio.to_thread(self.executor.close)

    async def restart(self):
        """Discard live interpreter state; next execution starts a fresh container."""
        await self.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()

def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for Crewloom AutoGen Sandbox Runner."""
    parser = argparse.ArgumentParser(
        prog="crewloom-autogen-sandbox",
        description="Crewloom isolated container code executor for AutoGen agent workflows.",
    )
    parser.add_argument("--workspace", "-w", default=".", help="Workspace root directory")
    parser.add_argument("--code", "-c", help="Inline code to execute")
    parser.add_argument("--file", "-f", help="Path to code file to execute")
    parser.add_argument("--lang", "-l", default="python", help="Language: python, sh, bash")
    parser.add_argument("--stateful", action="store_true", help="Reuse a named isolated Python interpreter until --reset")
    parser.add_argument("--session", default="cli", help="Named stateful session (default: cli)")
    parser.add_argument("--writable", action="append", help="Explicit writable workspace-relative path")
    parser.add_argument("--reset", action="store_true", help="Reset persistent session state")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Execution timeout in seconds")
    parser.add_argument("--image", default="python:3.11-slim", help="Docker container image")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    args = parser.parse_args(argv)

    try:
        executor = CrewloomAutoGenExecutor(
            workspace_root=args.workspace,
            image_id=args.image,
            timeout=args.timeout,
            stateful=args.stateful or args.reset,
            writable=args.writable,
            session_id=args.session,
        )
    except (ValueError, OSError) as exc:
        if args.json:
            sys.stdout.write(json.dumps({'status': 'error', 'error': str(exc), 'exit_code': 2}) + '\n')
        else:
            sys.stderr.write(str(exc) + '\n')
        return 2

    if args.reset:
        try:
            executor.restart()
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            if args.json:
                sys.stdout.write(json.dumps({'status': 'error', 'error': str(exc), 'exit_code': 2}) + '\n')
            else:
                sys.stderr.write(str(exc) + '\n')
            return 2
        if args.json:
            sys.stdout.write(json.dumps({"status": "success", "session_reset": True}) + "\n")
        else:
            sys.stdout.write("Session reset successfully.\n")
        return 0

    code = args.code
    if args.file:
        file_path = Path(args.file)
        if not file_path.is_file():
            err_msg = f"Code file not found: {args.file}"
            if args.json:
                sys.stdout.write(json.dumps({"status": "error", "error": err_msg, "exit_code": 2}) + "\n")
            else:
                sys.stderr.write(f"Error: {err_msg}\n")
            return 2
        code = file_path.read_text(encoding="utf-8")

    if not code:
        err_msg = "Must provide either --code, --file, or --reset"
        if args.json:
            sys.stdout.write(json.dumps({"status": "error", "error": err_msg, "exit_code": 2}) + "\n")
        else:
            sys.stderr.write(f"Error: {err_msg}\n")
        return 2

    block = CodeBlock(language=args.lang, code=code)
    result = executor.execute_code_blocks([block])

    if args.json:
        payload = {
            "status": "success" if result.exit_code == 0 else "error",
            "exit_code": result.exit_code,
            "output": result.output,
            "stateful": args.stateful,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
    else:
        if result.output:
            sys.stdout.write(result.output + "\n")

    return 0 if result.exit_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

