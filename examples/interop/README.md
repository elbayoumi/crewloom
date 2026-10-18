# Crewloom Cross-Framework Interop Demos

Zero-dependency executable examples demonstrating how to use Crewloom's **Zero-Trust Container Sandboxes** with **CrewAI**, **Microsoft AutoGen**, and **LangChain / LangGraph**.

---

## Runnable Demos

Each demo script runs out-of-the-box using the Python standard library without requiring external pip packages to be pre-installed:

```bash
# 1. CrewAI Sandbox Tool Demo
python3 examples/interop/demo_crewai.py

# 2. AutoGen CodeExecutor Demo
python3 examples/interop/demo_autogen.py

# 3. LangGraph State Node Demo
python3 examples/interop/demo_langgraph.py
```

---

## What Each Demo Demonstrates

| Demo | Framework Target | Key Feature |
|---|---|---|
| `demo_crewai.py` | CrewAI | Drop-in `CrewloomSandboxTool` with `func` protocol and non-root execution |
| `demo_autogen.py` | AutoGen | `CrewloomAutoGenExecutor` parsing markdown code blocks and returning `CommandLineCodeResult` |
| `demo_langgraph.py` | LangGraph | `create_crewloom_sandbox_node` executing inside state graph workflows |

---

## Security Guarantees in Action

All three demos enforce:
- `--network none` (complete airgap)
- Non-root UID (`docker_user()`)
- `--read-only` root filesystem
- `--cap-drop ALL`, `no-new-privileges`
- Quotas: `1g` RAM, `2` CPUs, `128` PIDs, `4MB` max file size
