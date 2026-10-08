# Getting started

1. Clone the repository and open it in a local agent host with file access.
2. Read [the constitution](../AGENTS.md) and choose a role from [the catalog](SKILLS.md).
3. Confirm the project inputs, requested language, external tools, and permissions.
4. Ask the agent to read the role procedure and relevant memory before execution.
5. Verify the output and update the relevant memory.

The `.agents/skills` layout contains ordinary Markdown role instructions. Hosts may support this directory natively or require their own skill configuration. The CLI does not install host adapters or claim automatic discovery across every agent application.

## Local commands

From the checkout root:

```bash
python3 scripts/crewloom.py list
python3 scripts/crewloom.py show qa-test-automation-engineer
python3 scripts/crewloom.py validate --skill qa-test-automation-engineer
python3 scripts/crewloom.py context qa-test-automation-engineer --out /tmp/crewloom-qa.md --language en
python3 scripts/check_repository.py
```

A context pack includes whole source documents when they fit. Otherwise it refers to the source explicitly. Read any referred source before execution. Context packs contain paths into the local checkout and are not portable standalone instructions.

## Small first task

Ask the context-guardian role to inspect a local document and report missing acceptance criteria. Select English or Arabic explicitly. Avoid assigning external platform work until the host tools and account permissions have been configured.

## Resource checker

```bash
python3 .agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py --project-dir /path/to/your/project
```

Use your actual project directory. This is a heuristic source scanner, not a database profiler or general correctness check. Exit 0 means no hard pattern findings, 1 means hard findings, and 2 means no scannable source was found. Inspect false positives and document any exceptions.

## Isolated feature execution

Start with [the six-stage feature example](../examples/software-workflow/README.md). Use [execution](EXECUTION.md) for readiness, task acceptance, Docker boundaries and resume; use [host setup](HOSTS.md) for project-local agent handoffs.

## Prepare and monitor multiple projects

Use [the project catalog guide](PROJECT_CATALOG.md) for project setup, disjoint-root registration, dashboard monitoring and preserved task cancellation. Use [the coordinator](COORDINATOR.md) for parallel tasks within one Git project.
