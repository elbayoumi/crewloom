"""Crewloom Interoperability Adapter for Microsoft AutoGen.

Provides a drop-in rootless container CodeExecutor for AutoGen agents.
Safely executes LLM-generated code blocks without host compromise or network leaks.
Compatible with both AutoGen v0.2 and v0.4 protocols.

Zero external pip dependencies required; operates entirely using Python 3.9+ standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Any, List, NamedTuple, Optional, Sequence, Union

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


class CrewloomAutoGenExecutor:
    """Microsoft AutoGen-compatible CodeExecutor backed by Crewloom's isolated container runtime.

    Usage:
        from adapters.interop.autogen_sandbox import CrewloomAutoGenExecutor, CodeBlock

        executor = CrewloomAutoGenExecutor(workspace_root="./project")
        result = executor.execute_code_blocks([CodeBlock(language="python", code="print(2 + 2)")])
        print(result.exit_code, result.output)
    """

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
        self.writable = tuple(writable) if writable else None

    def execute_code_blocks(self, code_blocks: Sequence[Any]) -> CommandLineCodeResult:
        """Execute a sequence of code blocks and return aggregated result.

        Accepts:
            - Sequence of CodeBlock instances
            - Sequence of objects with `.code` and `.language` attributes
            - Sequence of tuples `(language, code)`
            - Raw markdown string containing code fences
        """
        blocks: List[CodeBlock] = []

        if isinstance(code_blocks, str):
            blocks = extract_code_blocks(code_blocks)
            if not blocks:
                # If it's a raw string without code fences, treat as python
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

        for block in blocks:
            lang = block.language.lower()
            if lang in ("python", "python3", "py"):
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
        """Reset executor state (implements AutoGen CodeExecutor protocol)."""
        pass
