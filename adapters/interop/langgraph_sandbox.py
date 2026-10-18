"""Crewloom Interoperability Adapter for LangChain / LangGraph.

Provides a drop-in state graph node for isolated code execution in LangGraph workflows.
Runs agent code inside Crewloom's airgapped container sandbox without network access or root privileges.

Zero external pip dependencies required; operates entirely using Python 3.9+ standard library.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from .autogen_sandbox import CodeBlock, extract_code_blocks
from .crewai_sandbox import _is_cancelled, execute_sandbox_command


class CrewloomLangGraphNode:
    """LangGraph-compatible execution node for StateGraph workflows.

    Usage:
        from adapters.interop.langgraph_sandbox import CrewloomLangGraphNode

        sandbox_node = CrewloomLangGraphNode(workspace_root="./project")

        # In your LangGraph StateGraph:
        # workflow.add_node("sandbox", sandbox_node)
        # result = sandbox_node({"code": "print('hello from langgraph!')", "language": "python"})
    """

    def __init__(
        self,
        workspace_root: Union[str, Path] = ".",
        image_id: str = "python:3.11-slim",
        timeout: int = 30,
        writable: Optional[Sequence[str]] = None,
        input_key: str = "code",
        language_key: str = "language",
        output_key: str = "sandbox_result",
        cancellation_token: Any = None,
    ) -> None:
        """Initialize the LangGraph sandbox execution node.

        Args:
            workspace_root: Host directory mounted into container sandbox.
            image_id: Container image name (e.g. python:3.11-slim).
            timeout: Maximum execution duration in seconds before SIGKILL.
            writable: Specific workspace-relative subpaths permitted write access.
            input_key: State dictionary key containing code string or message.
            language_key: State dictionary key containing code language.
            output_key: State dictionary key under which result delta is stored.
            cancellation_token: Optional token or event checked for preemption.
        """
        self.workspace_root: Path = Path(workspace_root).resolve()
        self.image_id: str = image_id
        self.timeout: int = timeout
        self.writable: Optional[tuple[str, ...]] = tuple(writable) if writable is not None else None
        self.input_key: str = input_key
        self.language_key: str = language_key
        self.output_key: str = output_key
        self.cancellation_token: Any = cancellation_token

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute code from graph state and return state delta dictionary.

        Args:
            state: Current LangGraph workflow state dictionary.

        Returns:
            Dictionary containing state delta under `self.output_key`.
        """
        token = state.get("cancellation_token", self.cancellation_token)
        if _is_cancelled(token):
            return {
                self.output_key: {
                    "exit_code": 130,
                    "output": "[Execution cancelled by user]",
                    "timed_out": False,
                    "cancelled": True,
                    "duration_ms": 0,
                    "output_truncated": False,
                    "isolation": "crewloom-airgap",
                    "image_id": self.image_id,
                }
            }

        code = state.get(self.input_key, "")
        from_message = False
        if not code and "messages" in state:
            # Fallback: inspect the last message for tool_calls or code
            messages = state["messages"]
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content"):
                    code = str(last_msg.content)
                    from_message = True
                elif isinstance(last_msg, dict):
                    code = str(last_msg.get("content", ""))
                    from_message = True

        if not code:
            return {
                self.output_key: {
                    "exit_code": 0,
                    "output": "No code provided in state.",
                    "timed_out": False,
                    "cancelled": False,
                    "duration_ms": 0,
                    "output_truncated": False,
                    "isolation": "crewloom-airgap",
                    "image_id": self.image_id,
                }
            }

        language = state.get(self.language_key, "python")
        code_str = str(code)

        extracted_blocks: List[CodeBlock] = extract_code_blocks(code_str)
        if extracted_blocks:
            is_valid_syntax = False
            if language in ("python", "python3", "py"):
                try:
                    import ast
                    ast.parse(code_str)
                    is_valid_syntax = True
                except (SyntaxError, ValueError):
                    is_valid_syntax = False

            # Extract blocks if from message, or if not valid syntax as a raw script
            if from_message or not is_valid_syntax:
                matched = [
                    b for b in extracted_blocks
                    if b.language == language or (language in ("python", "python3", "py") and b.language in ("python", "python3", "py"))
                ]
                target_block = matched[0] if matched else extracted_blocks[0]
                code = target_block.code
                if not state.get(self.language_key):
                    language = target_block.language

        if language in ("python", "python3", "py"):
            argv = ["python3", "-c", str(code)]
        elif language in ("bash", "sh", "shell"):
            argv = ["/bin/sh", "-c", str(code)]
        elif language in ("node", "javascript", "js"):
            argv = ["node", "-e", str(code)]
        else:
            argv = ["python3", "-c", str(code)]

        result = execute_sandbox_command(
            root=self.workspace_root,
            argv=argv,
            image_id=self.image_id,
            timeout=self.timeout,
            writable=self.writable,
            cancellation_token=token,
        )

        return {
            self.output_key: {
                "exit_code": result["exit_code"],
                "output": result["output"],
                "timed_out": result["timed_out"],
                "cancelled": result.get("cancelled", False),
                "duration_ms": result["duration_ms"],
                "output_truncated": result["output_truncated"],
                "isolation": result["isolation"],
                "image_id": result["image_id"],
            }
        }


def create_crewloom_sandbox_node(
    workspace_root: Union[str, Path] = ".",
    image_id: str = "python:3.11-slim",
    timeout: int = 30,
    writable: Optional[Sequence[str]] = None,
    input_key: str = "code",
    output_key: str = "sandbox_result",
    language_key: str = "language",
    cancellation_token: Any = None,
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Factory creating a LangGraph node function for isolated container execution."""
    return CrewloomLangGraphNode(
        workspace_root=workspace_root,
        image_id=image_id,
        timeout=timeout,
        writable=writable,
        input_key=input_key,
        language_key=language_key,
        output_key=output_key,
        cancellation_token=cancellation_token,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI runner for LangGraph sandbox node execution."""
    parser = argparse.ArgumentParser(
        prog="python3 -m adapters.interop.langgraph_sandbox",
        description="Execute code in Crewloom isolated sandbox using LangGraph node adapter.",
    )
    parser.add_argument("--code", type=str, help="Code snippet or markdown block to execute")
    parser.add_argument("--file", type=str, help="Path to code file to execute")
    parser.add_argument("--language", type=str, default="python", help="Execution language (default: python)")
    parser.add_argument("--workspace", type=str, default=".", help="Workspace root directory")
    parser.add_argument("--image", type=str, default="python:3.11-slim", help="Container image")
    parser.add_argument("--timeout", type=int, default=30, help="Execution timeout in seconds")
    parser.add_argument("--writable", action="append", help="Writable relative paths")
    parser.add_argument("--json", action="store_true", help="Output JSON response payload")

    args = parser.parse_args(argv)

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
        err_msg = "Must provide either --code or --file"
        if args.json:
            sys.stdout.write(json.dumps({"status": "error", "error": err_msg, "exit_code": 2}) + "\n")
        else:
            sys.stderr.write(f"Error: {err_msg}\n")
        return 2

    node = CrewloomLangGraphNode(
        workspace_root=args.workspace,
        image_id=args.image,
        timeout=args.timeout,
        writable=args.writable,
    )

    state = {"code": code, "language": args.language}
    delta = node(state)
    result = delta["sandbox_result"]

    if args.json:
        payload = {
            "status": "success" if result["exit_code"] == 0 else "error",
            **result,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
    else:
        if result.get("output"):
            sys.stdout.write(result["output"] + "\n")

    return 0 if result["exit_code"] == 0 else (130 if result.get("cancelled") else 1)


if __name__ == "__main__":
    sys.exit(main())
