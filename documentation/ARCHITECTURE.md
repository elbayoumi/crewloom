# Architecture

Crewloom has four repository layers:

| Layer | Location | Responsibility |
| --- | --- | --- |
| Agent policy | [AGENTS.md](../AGENTS.md) | Language, authorization, reuse, evidence, and memory lifecycle |
| Role instructions | `.agents/skills/<id>/SKILL.md` | English procedures for a specialist task |
| Working memory | `Brain/` and role `brain/` directories | User-maintained experience and project decisions |
| Local tools | [Code registry](../.agents/CODE_REGISTRY.md) | Discovery, context packaging, structural and source checks |

Managed model steps call fixed provider APIs without tools; manual tasks use the host’s permissions. The toolkit does not start autonomous agents. The Python core uses the standard library.

Each public role has five initial memory documents. They contain no agency operational history. Users update them after real work and should keep private records out of public forks.

The core context builder keeps complete source files or explicit reading obligations; it never silently removes the tail of a procedure. English and Arabic change human-facing context labels, while paths and role identifiers remain stable.

The validator checks file structure and required section markers. The repository checker also checks Python syntax and local Markdown links, then runs the core suites. These checks do not establish the quality of every role or constrain arbitrary host actions.

Project selection and isolation: [project guide](PROJECTS.md).

## Execution and evidence layer

`scripts/workflow.py` is the single workflow state/execution implementation. The CLI delegates to it. The project owns a validated ordered plan; commands execute in Docker and tasks pause for reviewed artifacts. Runtime state is project-local and hidden from commands. Fingerprints prevent stale resume and project/plan substitution; attempts and locks survive handoffs. The objective feature evaluator reuses the same Docker executor and keeps expected answers outside candidate containers. See [execution](EXECUTION.md).

## Bounded model generation

Workflow model steps use `scripts/provider_gateway.py` for tool-free RPC and `scripts/execution_policy.py` for declared artifact publication. Docker commands receive a read-only declared-input snapshot and writable declared output files. Native CLI generation is an explicit operator compatibility exception outside this boundary. See [enforcement](ENFORCEMENT.md).

The repeated-trial coordinator (`scripts/evaluate_hosts.py`) freezes task/scorer hashes, collects new with/without-role submissions and calls the deterministic grader without provider labels. Provider mapping is written separately and joined in the final report. This provides automatic contract scoring, not independent human coordination or universal role-performance evidence.

Managed execution now rejects native model CLI steps by default. See [enforcement and compatibility](ENFORCEMENT.md) before running an existing model plan.
