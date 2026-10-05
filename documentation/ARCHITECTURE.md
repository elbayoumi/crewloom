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

Workflow model steps use `scripts/provider_gateway.py` for tool-free RPC and `scripts/execution_policy.py` for declared artifact publication. One declared output group is published as one recoverable transaction: the whole group and its input fingerprints are validated, staged and journalled under protected `.crewloom`, and applied under the project lock with the lock held through recovery. A failed group is rolled back only after every journal record is proven restorable, and an interrupted group is reconciled by the next managed publication, project entry or workflow run before any state is read, context frozen, gate evaluated or acceptance recorded. This is recoverable grouped publication, not an instant multi-file atomic change. Docker commands receive a read-only declared-input snapshot and writable declared output files. Native CLI generation is an explicit operator compatibility exception outside this boundary. See [enforcement](ENFORCEMENT.md).

The repeated-trial coordinator (`scripts/evaluate_hosts.py`) freezes task/scorer hashes, collects new with/without-role submissions and calls the deterministic grader without provider labels. Provider mapping is written separately and joined in the final report. This provides automatic contract scoring, not independent human coordination or universal role-performance evidence.

## Concurrent task coordination

`scripts/task_coordinator.py` is one coordinator over the same managed executor, not a second runtime. A project-local manifest names a dependency graph of ordinary workflow plans; every task runs `workflow.run` inside its own Git worktree, so isolation, the declared-artifact broker, the attempt ledger and the image policy are shared with a plain workflow. Batch ownership is a kernel-held advisory lock, and the project root is held with the same reservation a managed workflow writes, so ordinary workflow and native-context writers refuse it in both directions. The project lock covers only short controller state and Git mutations; each worktree takes its own root lock while it runs.

A task commit carries only its verified declared outputs, which is what lets the integration worktree combine task commits once and carry artifact diffs. The checked-out root is unchanged until an explicit reviewed decision, revalidated against the manifest, every task, the integration head, the recomputed diff digest and the reviewer credential, moves it by one recorded `--ff-only` fast-forward. Conflicts, failures and cancellations keep every branch, worktree and evidence file rather than resetting or cleaning anything. This is concurrency with reviewed integration, not a task scheduler: there is no provider client, no priority queue, and no way to publish a batch whose combined acceptance did not actually run. See [the coordinator](COORDINATOR.md).

Managed execution now rejects native model CLI steps by default. See [enforcement and compatibility](ENFORCEMENT.md) before running an existing model plan.
