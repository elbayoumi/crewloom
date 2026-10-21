"""Standard-library framework adapters with read-only workspace defaults.

Import implementations lazily so module CLIs execute only once under ``python -m``.
Docker and an explicitly selected local image are required for code execution.
"""
from importlib import import_module

_EXPORTS = {
    "ISOLATION_FLAGS": "crewai_sandbox",
    "CrewloomSandboxTool": "crewai_sandbox",
    "build_sandbox_command": "crewai_sandbox",
    "execute_in_sandbox": "crewai_sandbox",
    "execute_sandbox_command": "crewai_sandbox",
    "CodeBlock": "autogen_sandbox",
    "CommandLineCodeResult": "autogen_sandbox",
    "CrewloomAsyncAutoGenExecutor": "autogen_sandbox",
    "CrewloomAutoGenExecutor": "autogen_sandbox",
    "extract_code_blocks": "autogen_sandbox",
    "CrewloomLangGraphNode": "langgraph_sandbox",
    "create_crewloom_sandbox_node": "langgraph_sandbox",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    """Resolve the established public import names without eager CLI imports."""
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module('.' + _EXPORTS[name], __name__), name)
    globals()[name] = value
    return value
