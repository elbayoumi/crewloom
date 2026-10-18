# Crewloom Cross-Framework Interoperability Adapters

Enterprise-grade, zero-trust container execution sandboxes for **CrewAI**, **Microsoft AutoGen**, and **LangChain / LangGraph**.

---

## The Security Problem in Modern Agent Frameworks

Most popular multi-agent frameworks execute code either **directly on the host operating system** or inside **unhardened Docker containers running as `root` with open internet access**:

| Risk | Default Framework Behavior | Danger |
|---|---|---|
| **Network Exfiltration** | Outbound access enabled | Prompt injections exfiltrate `.env` files, API keys, and source code. |
| **Root Privilege** | Runs as UID 0 (`root`) | Container breakout vulnerabilities grant full host root access. |
| **Filesystem Mutation** | Writable root filesystem | Malware or corrupted scripts overwrite OS binaries and dependencies. |
| **Resource Exhaustion** | Unbounded RAM / PIDs | Fork bombs and infinite loops crash the host development machine. |

**Crewloom solves this** by providing standard-library, drop-in sandbox adapters that enforce a strict **Zero-Trust Security Contract** across any agent framework.

---

## Zero-Trust Security Guarantees

Every command executed through Crewloom interop adapters runs under these non-negotiable isolation flags:

1. **Airgapped Network (`--network none`)**: Outbound and inbound networking is completely disabled at the kernel namespace level.
2. **Rootless UID Enforcement**: Execution refuses to run as `root` (UID 0) and matches the unprivileged host user (`uid:gid`).
3. **Immutable Root Filesystem (`--read-only`)**: The container root filesystem cannot be written to or modified.
4. **Complete Capability Shedding (`--cap-drop ALL`, `--security-opt no-new-privileges`)**: All Linux capabilities are dropped; privilege escalation is strictly blocked.
5. **Strict Resource Bounding**: Hard limits of `1g` RAM, `2` CPUs, `128` PIDs, and `4MB` max file size (`fsize=4194304:4194304`).
6. **Narrow Workspace Bind Mount**: Only the declared project directory is mounted at `/workspace`; runtime state (`.crewloom`) is masked with a `1m` read-only tmpfs.

---

## 1. CrewAI Integration

Use `CrewloomSandboxTool` directly as a custom tool in your CrewAI agents or tasks:

```python
from crewai import Agent, Task, Crew
from adapters.interop.crewai_sandbox import CrewloomSandboxTool

# Initialize Crewloom isolated sandbox tool
sandbox_tool = CrewloomSandboxTool(
    workspace_root="./my-project",
    image_id="python:3.11-slim",
    timeout=30,
    writable=["output/"]  # Only output/ is writable; rest of workspace is read-only
)

# Assign tool to CrewAI agent
coder = Agent(
    role="Backend Engineer",
    goal="Write and verify data processing algorithms",
    backstory="You write clean Python code and test it inside the sandbox.",
    tools=[sandbox_tool]
)

task = Task(
    description="Calculate prime factors of 104729 and save report to output/primes.txt",
    expected_output="Verification summary",
    agent=coder
)

crew = Crew(agents=[coder], tasks=[task])
crew.kickoff()
```

---

## 2. Microsoft AutoGen Integration

Use `CrewloomAutoGenExecutor` as the `code_execution_config` executor for AutoGen agents:

```python
from autogen import ConversableAgent
from adapters.interop.autogen_sandbox import CrewloomAutoGenExecutor

# Initialize Crewloom rootless executor
executor = CrewloomAutoGenExecutor(
    workspace_root="./my-project",
    image_id="python:3.11-slim",
    timeout=30,
    writable=["artifacts/"]
)

# Assign executor to AutoGen Assistant / UserProxyAgent
user_proxy = ConversableAgent(
    name="UserProxy",
    human_input_mode="NEVER",
    code_execution_config={"executor": executor}
)

assistant = ConversableAgent(
    name="Assistant",
    system_message="Write Python code blocks in markdown fences to solve tasks."
)

user_proxy.initiate_chat(
    assistant,
    message="Write a script to compute the SHA-256 of 'crewloom' and print it."
)
```

---

## 3. LangChain / LangGraph Integration

Use `CrewloomLangGraphNode` or `create_crewloom_sandbox_node` as a state graph node:

```python
from typing import TypedDict
from langgraph.graph import StateGraph, END
from adapters.interop.langgraph_sandbox import create_crewloom_sandbox_node

class AgentState(TypedDict):
    code: str
    language: str
    sandbox_result: dict

# Create sandbox execution node
sandbox_node = create_crewloom_sandbox_node(
    workspace_root="./my-project",
    image_id="python:3.11-slim",
    timeout=30
)

# Build LangGraph workflow
workflow = StateGraph(AgentState)
workflow.add_node("execute_code", sandbox_node)
workflow.set_entry_point("execute_code")
workflow.add_edge("execute_code", END)

app = workflow.compile()
output = app.invoke({"code": "import sys; print(f'Python {sys.version}')", "language": "python"})
print(output["sandbox_result"]["output"])
```

---

## Architecture & Zero Dependencies

The adapters in `adapters/interop/` have **zero external pip dependencies**. They require only Python 3.9+ standard library modules (`os`, `subprocess`, `pathlib`, `typing`, `time`, `re`).

Whether you are using CrewAI, AutoGen, or LangGraph, your development environment remains clean, lightweight, and completely protected from malicious code execution.
