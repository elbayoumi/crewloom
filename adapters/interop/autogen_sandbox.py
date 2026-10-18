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


def _build_stateful_python_wrapper(user_code: str, state_path: str, history_path: str) -> str:
    """Generate isolated Python runner that persists state variables across executions."""
    # Escape triple quotes in user code if necessary
    user_code_escaped = user_code.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

    return f'''
import importlib
import os
import pickle
import sys

_STATE_FILE = {repr(state_path)}
_HISTORY_FILE = {repr(history_path)}

# 1. Restore previous session state (variables & imported modules)
_SESSION_DATA = {{"vars": {{}}, "modules": []}}
if os.path.isfile(_STATE_FILE):
    try:
        with open(_STATE_FILE, "rb") as _f:
            _SESSION_DATA = pickle.load(_f)
    except Exception:
        _SESSION_DATA = {{"vars": {{}}, "modules": []}}

for _mod in _SESSION_DATA.get("modules", []):
    try:
        globals()[_mod] = importlib.import_module(_mod)
    except Exception:
        pass

globals().update(_SESSION_DATA.get("vars", {{}}))

# 2. Append block to session history log
try:
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    with open(_HISTORY_FILE, "a", encoding="utf-8") as _hf:
        _hf.write("\\n# --- Block Execution ---\\n" + """{user_code_escaped}""" + "\\n")
except Exception:
    pass

# 3. Execute target user code within globals
_CODE_TO_EXEC = """{user_code_escaped}"""
exec(compile(_CODE_TO_EXEC, "<autogen-session>", "exec"), globals())

# 4. Snapshot picklable variables and new modules
_NEW_VARS = {{}}
_NEW_MODULES = []

for _k, _v in list(globals().items()):
    if _k.startswith("_") or _k in ("_STATE_FILE", "_HISTORY_FILE", "_SESSION_DATA", "_CODE_TO_EXEC", "_NEW_VARS", "_NEW_MODULES"):
        continue
    if type(_v).__name__ == "module":
        if hasattr(_v, "__name__") and _v.__name__ not in _NEW_MODULES:
            _NEW_MODULES.append(_v.__name__)
    else:
        try:
            pickle.dumps(_v)
            _NEW_VARS[_k] = _v
        except Exception:
            pass

try:
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    with open(_STATE_FILE, "wb") as _f:
        pickle.dump({{"vars": _NEW_VARS, "modules": _NEW_MODULES}}, _f)
except Exception:
    pass
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
        self._state_file = self._session_dir / "session_state.pkl"
        self._history_file = self._session_dir / "session_history.py"

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
                    # In container, workspace is mounted at /workspace
                    container_state = "/workspace/.crewloom/autogen_session/session_state.pkl"
                    container_hist = "/workspace/.crewloom/autogen_session/session_history.py"
                    wrapper_code = _build_stateful_python_wrapper(block.code, container_state, container_hist)
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
            )

            output = result["output"].strip()
            if output:
                combined_outputs.append(output)

            if result["exit_code"] != 0:
                combined_output = "\n".join(combined_outputs)
                return CommandLineCodeResult(
                    exit_code=result["exit_code"],
                    output=combined_output or f"Command failed with exit code {result['exit_code']}",
                )

        return CommandLineCodeResult(exit_code=0, output="\n".join(combined_outputs))

    def restart(self) -> None:
        """Reset persistent executor state and session history."""
        if self._state_file.exists():
            try:
                self._state_file.unlink()
            except OSError:
                pass
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

