"""Crewloom Interoperability Bridges for External Agent Frameworks.

Provides zero-dependency, enterprise-grade execution sandboxes for:
- CrewAI (CrewloomSandboxTool)
- Microsoft AutoGen (CrewloomAutoGenExecutor)
- LangChain / LangGraph (CrewloomLangGraphNode)

All adapters enforce Crewloom's zero-trust container security model:
- Airgapped execution (--network none)
- Non-root UID enforcement (refuses root)
- Immutable read-only filesystem (--read-only)
- Strict capability shedding (--cap-drop ALL, no-new-privileges)
- Bounded memory, CPU, PID, and file-size quotas
"""

from .autogen_sandbox import (
    CodeBlock,
    CommandLineCodeResult,
    CrewloomAutoGenExecutor,
    extract_code_blocks,
)
from .crewai_sandbox import (
    ISOLATION_FLAGS,
    CrewloomSandboxTool,
    build_sandbox_command,
    execute_in_sandbox,
    execute_sandbox_command,
)
from .langgraph_sandbox import (
    CrewloomLangGraphNode,
    create_crewloom_sandbox_node,
)

__all__ = [
    "ISOLATION_FLAGS",
    "CrewloomSandboxTool",
    "build_sandbox_command",
    "execute_in_sandbox",
    "execute_sandbox_command",
    "CodeBlock",
    "CommandLineCodeResult",
    "CrewloomAutoGenExecutor",
    "extract_code_blocks",
    "CrewloomLangGraphNode",
    "create_crewloom_sandbox_node",
]
