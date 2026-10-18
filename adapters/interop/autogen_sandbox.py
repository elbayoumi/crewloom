"""Crewloom Interoperability Adapter for Microsoft AutoGen.

Provides a drop-in rootless container CodeExecutor for AutoGen agents.
Safely executes LLM-generated code blocks without host compromise or network leaks.
Compatible with both AutoGen v0.2 and v0.4 protocols.

Supports:
- Stateless and stateful session code execution across blocks
- Cancellation token inspection (AutoGen 0.4 and threading/asyncio events)
- Safe isolation with zero external dependencies (Python 3.9+ standard library only)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import json
import os
from pathlib import Path
import pickle
import re
import sys
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Union

from .crewai_sandbox import build_sandbox_command, execute_sandbox_command


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


def _is_cancelled(cancellation_token: Any) -> bool:
    """Inspect whether an AutoGen or standard cancellation token has been triggered."""
    if cancellation_token is None:
        return False
    if callable(getattr(cancellation_token, "is_cancelled", None)):
        return bool(cancellation_token.is_cancelled())
    if callable(getattr(cancellation_token, "is_set", None)):
        return bool(cancellation_token.is_set())
    if callable(cancellation_token):
        try:
            return bool(cancellation_token())
        except Exception:
            return False
    if isinstance(cancellation_token, bool):
        return cancellation_token
    return False


def _build_stateful_python_wrapper(current_code: str, previous_blocks: Sequence[str]) -> str:
    """Generate isolated Python runner that replays previous blocks with suppressed stdout/stderr."""
    return f'''
import os
import sys

_REPLAY_BLOCKS = {repr(list(previous_blocks))}
_CURRENT_CODE = {repr(current_code)}

if _REPLAY_BLOCKS:
    _saved_stdout, _saved_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")
        for _block in _REPLAY_BLOCKS:
            try:
                exec(compile(_block, "<autogen-replay>", "exec"), globals())
            except Exception:
                pass
    finally:
        try:
            sys.stdout.close()
            sys.stderr.close()
        except Exception:
            pass
        sys.stdout, sys.stderr = _saved_stdout, _saved_stderr

exec(compile(_CURRENT_CODE, "<autogen-session>", "exec"), globals())
'''


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
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.image_id = image_id
        self.timeout = timeout
        self.writable = tuple(writable) if writable is not None else None
        self.stateful = stateful
        self._session_dir = self.workspace_root / ".crewloom" / "autogen_session"
        self._history_file = self._session_dir / "session_history.json"
        self._session_blocks: List[str] = self._load_session_history() if stateful else []

    def _load_session_history(self) -> List[str]:
        """Load session block history from workspace on host."""
        if self._history_file.exists():
            try:
                return json.loads(self._history_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_session_history(self) -> None:
        """Persist session block history to workspace on host."""
        if not self.stateful:
            return
        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            self._history_file.write_text(json.dumps(self._session_blocks), encoding="utf-8")
        except OSError:
            pass

    def execute_code_blocks(
        self,
        code_blocks: Sequence[Any],
        cancellation_token: Any = None,
    ) -> CommandLineCodeResult:
        """Execute a sequence of code blocks and return aggregated result.

        Compatible with both AutoGen 0.2 and 0.4 execution specifications.
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
                if self.stateful:
                    wrapper_code = _build_stateful_python_wrapper(block.code, self._session_blocks)
                    argv = ["python3", "-c", wrapper_code]
                else:
                    argv = ["python3", "-c", block.code]
            elif lang in ("bash", "sh", "shell"):
                argv = ["/bin/sh", "-c", block.code]
            else:
                combined_outputs.append(f"[Skipped unsupported language: {block.language}]")
                continue

            result = execute_sandbox_command(
                root=self.workspace_root,
                argv=argv,
                image_id=self.image_id,
                timeout=self.timeout,
                writable=self.writable,
                cancellation_token=cancellation_token,
            )

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

            # Record successful python execution for session continuity
            if self.stateful and lang in ("python", "python3", "py"):
                self._session_blocks.append(block.code)
                self._save_session_history()

        return CommandLineCodeResult(exit_code=0, output="\n".join(combined_outputs))

    def restart(self) -> None:
        """Reset persistent executor state and session history."""
        self._session_blocks.clear()
        if self._history_file.exists():
            try:
                self._history_file.unlink()
            except OSError:
                pass

    async def a_execute_code_blocks(
        self,
        code_blocks: Sequence[Any],
        cancellation_token: Any = None,
    ) -> CommandLineCodeResult:
        """Execute code blocks asynchronously matching AutoGen 0.4 CodeExecutor protocol."""
        import asyncio
        if _is_cancelled(cancellation_token):
            return CommandLineCodeResult(exit_code=130, output="Execution cancelled by user")
        return await asyncio.to_thread(self.execute_code_blocks, code_blocks, cancellation_token)


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
    parser.add_argument("--stateful", action="store_true", help="Preserve state and variables across runs")
    parser.add_argument("--reset", action="store_true", help="Reset persistent session state")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Execution timeout in seconds")
    parser.add_argument("--image", default="python:3.11-slim", help="Docker container image")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    args = parser.parse_args(argv)

    executor = CrewloomAutoGenExecutor(
        workspace_root=args.workspace,
        image_id=args.image,
        timeout=args.timeout,
        stateful=args.stateful,
    )

    if args.reset:
        executor.restart()
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

