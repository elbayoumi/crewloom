"""Crewloom Interoperability Adapter for LangChain / LangGraph.

Provides a drop-in state graph node for isolated code execution in LangGraph workflows.
Runs agent code inside Crewloom's airgapped container sandbox without network access or root privileges.

Zero external pip dependencies required; operates entirely using Python 3.9+ standard library.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Union

from .crewai_sandbox import execute_sandbox_command


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
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.image_id = image_id
        self.timeout = timeout
        self.writable = tuple(writable) if writable else None
        self.input_key = input_key
        self.language_key = language_key
        self.output_key = output_key

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute code from graph state and return state delta."""
        code = state.get(self.input_key, "")
        if not code and "messages" in state:
            # Fallback: inspect the last message for tool_calls or code
            messages = state["messages"]
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "content"):
                    code = str(last_msg.content)
                elif isinstance(last_msg, dict):
                    code = str(last_msg.get("content", ""))

        if not code:
            return {
                self.output_key: {
                    "exit_code": 0,
                    "output": "No code provided in state.",
                    "timed_out": False,
                    "duration_ms": 0,
                    "isolation": "crewloom-airgap",
                }
            }

        language = state.get(self.language_key, "python")
        if language in ("python", "python3", "py"):
            argv = ["python3", "-c", str(code)]
        elif language in ("bash", "sh", "shell"):
            argv = ["/bin/sh", "-c", str(code)]
        else:
            argv = ["python3", "-c", str(code)]

        result = execute_sandbox_command(
            root=self.workspace_root,
            argv=argv,
            image_id=self.image_id,
            timeout=self.timeout,
            writable=self.writable,
        )

        return {
            self.output_key: {
                "exit_code": result["exit_code"],
                "output": result["output"],
                "timed_out": result["timed_out"],
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
) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Factory creating a LangGraph node function for isolated container execution."""
    node = CrewloomLangGraphNode(
        workspace_root=workspace_root,
        image_id=image_id,
        timeout=timeout,
        writable=writable,
        input_key=input_key,
        output_key=output_key,
    )
    return node
