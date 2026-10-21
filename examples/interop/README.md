# Adapter examples

These standard-library examples preview Crewloom adapter objects and their inputs.
They do not construct CrewAI, AutoGen or LangGraph SDK agents, graphs or models.
Default execution prints `[SKIP]` for container execution and SDK integration; an
exit code of zero means the preview completed.

```bash
python3 examples/interop/demo_crewai.py
python3 examples/interop/demo_autogen.py
python3 examples/interop/demo_langgraph.py
```

To require actual code execution through the adapters, start Docker and explicitly
pull the local image before running:

```bash
docker pull python:3.14-slim
python3 examples/interop/demo_crewai.py --require-execution
python3 examples/interop/demo_autogen.py --require-execution
python3 examples/interop/demo_langgraph.py --require-execution
```

Missing Docker, an unavailable daemon or missing image returns exit code 2 in this
mode. Execution failures propagate a nonzero exit code. Each example uses a temporary
workspace and supplied code, with read-only defaults and explicit output grants
where needed. Docker resource, UID, mount and network restrictions apply; the host,
daemon and image remain trusted.

| Example | Adapter behavior shown |
| --- | --- |
| `demo_crewai.py` | Construct a tool and Docker arguments; optionally run a factorial calculation |
| `demo_autogen.py` | Extract code fences; optionally run them with the synchronous executor |
| `demo_langgraph.py` | Construct a state callable; optionally return its execution result delta |

The [interop contract](../../documentation/INTEROP.md) documents the actual pinned
AutoGen 0.4.9 agent acceptance and async wrapper. These examples provide no evidence
of native CrewAI or StateGraph SDK integration.
