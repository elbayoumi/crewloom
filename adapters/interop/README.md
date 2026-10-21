# Crewloom Cross-Framework Interoperability Adapters

Docker execution adapters for **CrewAI**, **Microsoft AutoGen**, and **LangChain / LangGraph**.

---

## The Security Problem in Modern Agent Frameworks

Most popular multi-agent frameworks execute code either **directly on the host operating system** or inside **unhardened Docker containers running as `root` with open internet access**:

| Risk | Default Framework Behavior | Danger |
|---|---|---|
| **Network Exfiltration** | Outbound access enabled | Prompt injections exfiltrate `.env` files, API keys, and source code. |
| **Root Privilege** | Runs as UID 0 (`root`) | Container breakout vulnerabilities grant full host root access. |
| **Filesystem Mutation** | Writable root filesystem | Malware or corrupted scripts overwrite OS binaries and dependencies. |
| **Resource Exhaustion** | Unbounded RAM / PIDs | Fork bombs and infinite loops crash the host development machine. |

Crewloom applies the container restrictions below. These differ from the managed workflow broker; see [execution and session limits](../../documentation/INTEROP.md).

---

## Container restrictions

Every command executed through Crewloom interop adapters runs under these non-negotiable isolation flags:

1. **Airgapped Network (`--network none`)**: Outbound and inbound networking is completely disabled at the kernel namespace level.
2. **Rootless UID Enforcement**: Execution refuses to run as `root` (UID 0) and matches the unprivileged host user (`uid:gid`).
3. **Immutable Root Filesystem (`--read-only`)**: The container root filesystem cannot be written to or modified.
4. **Complete Capability Shedding (`--cap-drop ALL`, `--security-opt no-new-privileges`)**: All Linux capabilities are dropped; privilege escalation is strictly blocked.
5. **Strict Resource Bounding**: Hard limits of `1g` RAM, `2` CPUs, `128` PIDs, and `4MB` max file size (`fsize=4194304:4194304`).
6. **Narrow Workspace Bind Mount**: The project is mounted read-only at `/workspace`. Omitted `writable`, `None` and `[]` all prohibit project writes. Only explicit grants are writable; controls, links and overlapping grants are refused. `.crewloom` is masked with read-only tmpfs.

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
    tools=[sandbox_tool.to_crewai_tool()]
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

`CrewloomAutoGenExecutor.execute_code_blocks()` is synchronous. Microsoft AutoGen
0.4 `CodeExecutorAgent` awaits that method, so pass `executor.as_async_executor()`:

```python
import asyncio
from autogen_agentchat.agents import CodeExecutorAgent
from autogen_agentchat.messages import TextMessage
from autogen_core import CancellationToken
from adapters.interop import CrewloomAutoGenExecutor

async def main():
    with CrewloomAutoGenExecutor(
        workspace_root="./my-project", image_id="python:3.11-slim",
        writable=["artifacts"], stateful=True,
    ) as executor:
        agent = CodeExecutorAgent("runner", code_executor=executor.as_async_executor())
        response = await agent.on_messages(
            [TextMessage(content="```python\nprint(42)\n```", source="user")],
            CancellationToken(),
        )
        print(response.chat_message.content)

asyncio.run(main())
```

The example executes supplied code without a model call. Actual agent acceptance is
pinned to `autogen-agentchat==0.4.9`; other versions require verification. The async
adapter supports `start()`, `stop()`, `restart()` and `async with`. Framework config
serialization is not implemented. `a_execute_code_blocks()` remains an async
convenience method for direct callers; passing the synchronous object to a 0.4
agent is incorrect. The synchronous API remains available for existing callers;
a native AutoGen 0.2 agent integration is not asserted by these tests.

Named CLI sessions retain their bounded container across invocations until reset:

```bash
python3 -m adapters.interop.autogen_sandbox --workspace ./project --stateful --session demo --code 'x=42' --json
python3 -m adapters.interop.autogen_sandbox --workspace ./project --stateful --session demo --code 'print(x)' --json
python3 -m adapters.interop.autogen_sandbox --workspace ./project --session demo --reset --json
```

Object sessions are independent by default and close at process exit. Prefer
`with CrewloomAutoGenExecutor(..., stateful=True) as executor:` for prompt cleanup.
Timeout/cancellation destroys state; a surviving object requires `restart()`.
Legacy `session_history.json` files are ignored and never executed or deserialized.

### AutoGen Features:
- **Stateful REPL Continuity**: When `stateful=True`, consecutive Python blocks share a live isolated interpreter; previous commands are never replayed. Use a context manager or `close()` for cleanup; `restart()` discards state.
- **Cancellation Token Support**: Compatible with AutoGen 0.4 `cancellation_token` objects and standard threading/asyncio events (returns exit code `130`).
- **Command Line Runner**: Run code blocks or reset sessions directly from the CLI:
  ```bash
  python3 -m adapters.interop.autogen_sandbox --workspace ./project --code "print(1 + 1)" --json
  python3 -m adapters.interop.autogen_sandbox --workspace ./project --reset --json
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

Docker and a locally available image are required. The whole project is readable except masked runtime state. Explicit output grants mutate the host directly without workflow publication/rollback. Docker and the host remain trusted.
