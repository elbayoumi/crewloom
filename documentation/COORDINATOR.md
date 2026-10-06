# Concurrent task coordinator

`crewloom coordinator` runs a project-local dependency graph of tasks as a real batch: independent
tasks execute concurrently in separate Git worktrees, a dependent task actually reads its
ancestors' committed output, and the checked-out tree changes only after an explicit reviewed
decision. It replaces the manual "make a worktree per task and merge by hand" routine; it is not a
task scheduler, and it makes no provider call of its own — a `model` step runs inside the ordinary
managed executor, and only what a real command acceptance executed may become a task commit.

Every task runs the existing managed executor, `workflow.run`, so the isolation boundary, the
declared-artifact broker, the Docker image policy and the failure ledger are exactly the ones an
ordinary workflow already uses. Read [execution and failure handling](EXECUTION.md) and
[managed enforcement](ENFORCEMENT.md) first. Arabic companion: [COORDINATOR.ar.md](COORDINATOR.ar.md).

## Requirements

Python 3.9+ on Linux, macOS or WSL, Git, Docker with a working daemon, a locally available
execution image, and a project that is already bound:

```bash
docker pull python:3.14-slim
crewloom project enter --project /path/to/project --project-id my-project --task-id bind-root --role context-guardian
```

A bound project needs `crewloom.project.json` and `.crewloom/binding.json`. Without that binding the
coordinator refuses; it never infers a project from the working directory or a previous client.

## Manifest contract

`coordinator.json` is project-local JSON. Paths are relative to the canonical project root.

```json
{"schema_version":1,"id":"feature-batch","project_id":"my-project","base":"HEAD","workers":2,
 "tasks":[{"id":"left","workflow":"workflows/left.json","depends_on":[]},
          {"id":"right","workflow":"workflows/right.json","depends_on":[]},
          {"id":"combine","workflow":"workflows/combine.json","depends_on":["left","right"]}],
 "integration":{"workflow":"workflows/integration.json"}}
```

| Field | Meaning |
| --- | --- |
| `schema_version` | Exactly `1`. |
| `id` | Stable kebab-case batch ID; it names the runtime folder, the branches and the runtime reservation. |
| `project_id` | The project's portable identity; it must equal `--project-id` and the local binding. |
| `base` | The exact commit every task starts from. It must resolve in this repository and must be the checked-out `HEAD`. |
| `workers` | Concurrent tasks, 1 to 4. Default 2. |
| `language` | Optional `en` or `ar`; default `en`. |
| `tasks` | 1 to 32 tasks. Each needs `id`, `workflow`, optional `depends_on` and optional `native_host_cli`. |
| `integration` | The workflow that accepts the combined result. It accepts the same optional `native_host_cli`. |
| `native_host_cli` | `true` only when this task's workflow may reach a model host through an installed CLI. Defaults to `false`, and one more explicit operator flag is still required at run time. See [Model steps](#model-steps-in-a-batch). |

`workflow` refers to an ordinary [workflow plan](EXECUTION.md#plan-contract) inside the project.
Unknown fields, duplicate task IDs, unknown keys, cycles, self-dependencies, missing dependencies,
a shared workflow ID and a manual `task` step are refused before anything is created. A `model` step
is accepted only where a real command acceptance can consume what it generates.

The integration workflow must declare **every task output as one of its declared inputs**. That is
what makes its acceptance a combined acceptance rather than a self-reported pass, and it is checked
statically before any worktree exists.

## Commands

`--project` and `--project-id` are required for every action, and `--manifest` is relative to the
project. The JSON report is authoritative.

```bash
crewloom coordinator validate --project /path/to/project --project-id my-project --manifest coordinator.json
crewloom coordinator run      --project /path/to/project --project-id my-project --manifest coordinator.json
crewloom coordinator status   --project /path/to/project --project-id my-project --manifest coordinator.json
crewloom coordinator prepare  --project /path/to/project --project-id my-project --manifest coordinator.json
crewloom coordinator review   --project /path/to/project --project-id my-project --manifest coordinator.json \
  --principal reviewer-alex --expected-base <base> --candidate-head <head> --diff-sha256 <digest>
crewloom coordinator publish  --project /path/to/project --project-id my-project --manifest coordinator.json \
  --expected-base <base> --candidate-head <head> --diff-sha256 <digest>
crewloom coordinator cancel   --project /path/to/project --project-id my-project --manifest coordinator.json
```

| Action | What it does |
| --- | --- |
| `validate` | Read-only preflight of the manifest, identity, Git base, workflows and DAG. Writes nothing, including no Git index refresh. |
| `run` | Starts or resumes the batch: binds every task worktree, then executes ready tasks with at most `workers` concurrent managed runs. |
| `status` | Reads the recorded batch, its worktrees, evidence references and recorded limits. |
| `prepare` | Creates the integration worktree, combines every verified task commit once, then runs the actual combined acceptance. |
| `review` | Records one reviewed decision over the exact base, candidate head and diff digest. |
| `publish` | Revalidates everything and fast-forwards the root onto the reviewed candidate exactly once. |
| `cancel` | Stops future dispatch and preserves verified evidence for resume. |

Exit 0 means the action succeeded; exit 2 means it was blocked or refused, with `error` in the
report.

`--image` selects the execution image (default `python:3.14-slim`), `--workers` overrides the
manifest value, and `--reason` records a cancellation cause. `--allow-host-cli` is this run's
explicit operator opt-in for installed CLI model hosts; it is only meaningful together with
`native_host_cli` on the task. In verified-review projects the credential comes from
`CREWLOOM_REVIEWER_TOKEN` or `--reviewer-token-stdin`, never from an argument.

The same actions are importable from Python as `validate(root, manifest, project_id)`,
`start(root, manifest, project_id, workers=None, image=...)`,
`run(root, manifest, project_id, workers=None, image=..., allow_host_cli=False)`,
`status(...)`, `cancel(root, manifest, project_id, reason=...)`,
`prepare(root, manifest, project_id, image=None, allow_host_cli=False)`,
`review(root, manifest, project_id, principal=None, expected_base=None, candidate_head=None,
diff_sha256=None, role=None, token=None)` and `publish(root, manifest, project_id, expected_base,
candidate_head, diff_sha256)`. Each returns the same JSON-shaped dictionary the CLI prints and
raises `ValueError` with the refusal reason. `start` takes batch ownership and binds every worktree
without running a workflow; `run` does both.

## Model steps in a batch

A task may be real AI development rather than a shell builder. A workflow can declare `model` steps
that run through the ordinary managed executor in that task's own worktree, and the batch verifies
what they produced instead of trusting them:

- **A generation is never a result on its own.** The workflow must declare at least one command step,
  and every artifact a `model` step declares must be a declared input of a *later* command step in
  the same workflow. A model-only workflow, or a generated artifact that no command acceptance
  reads, is refused at preflight — before a worktree, a provider call or a file exists.
- **The commit needs both evidences.** A task becomes `verified` only when the generation has a
  succeeded attempt in the executor ledger *and* the consuming command step completed with the
  generated digest recorded as one of its own input digests at execution time. That is a digest
  comparison against recorded evidence: it proves the acceptance ran the generated bytes, not that
  the code is any good. An unconsumed artifact stays in the worktree, uncommitted.
- **The combined acceptance still rules.** The integration workflow must declare every task output,
  generated modules included, so the candidate review is over code that was executed together.
- **The coordinator makes no provider call.** Generation happens inside `workflow.run`, under that
  module's host policy, per-checkout request budget, prompt/response digests and artifact broker.
  Each isolated worktree has its own attempt ledger; this is not an account-wide or aggregate
  project billing cap.
- **Installed CLIs need two explicit decisions.** A host reached through an installed CLI — `codex`,
  `claude`, `opencode`, as named by `model_host.CLI_HOSTS` — is refused unless the manifest task
  declares `native_host_cli: true` *and* the executing call passes `--allow-host-cli` /
  `allow_host_cli=True`. Either one alone is refused before the provider is contacted. A
  tool-free RPC host (`openai`, `anthropic`) needs neither.
- **A manual `task` step still cannot run here.** It waits for a human decision with its own
  reviewer credential, which is `workflow accept` outside the batch.
- Resume re-proves the same generation and consumption evidence before it skips a verified task, so
  a verified model task is never generated twice.

## What each task actually does

1. The worktree `.crewloom/worktrees/<batch>/<task>` is created on branch
   `crewloom/<batch>/<task>` at the fixed base. Its local checkout binding is new; the portable
   project identity is the project's.
2. Verified ancestor commits are merged into the worktree first, in dependency order, so a dependent
   task reads its ancestors' files rather than the untouched base.
3. The task's real workflow runs. Docker isolation, declared inputs and outputs, the attempt ledger
   and the failure budget are the ordinary ones.
4. Only the verified declared outputs are committed. If the index also holds anything else, the
   commit is refused. Generated `AGENTS.md` context, `.gitignore` edits, role memory, user files and
   `.crewloom` are never staged, and Git hooks still run — a hook failure leaves the worktree and the
   artifact in place for inspection and the batch resumable.
5. A task becomes `verified` only with a complete managed run, unchanged input/output/criteria
   hashes, a succeeded executor attempt per command step, the same evidence for every `model` step
   plus the command acceptance that consumed its bytes, and a distinct local checkout binding.

State lives in `.crewloom/coordinators/<batch>/state.json` with an owner-only bounded event log
beside it. Records are owner-only, atomically replaced, and bounded; the log stops appending rather
than growing without limit. `status` prints the exact worktree paths, branches, commits, evidence
files and recorded limits.

## Failure, blocking, resume and cancellation

- A failed or blocked task blocks every task that depends on it, with the blocking IDs recorded.
  There is no partial acceptance.
- Resume re-proves each verified task — executor ledger, output hashes, worktree head, workflow
  plan, criteria and the manifest itself — before skipping it. A verified task is never executed
  twice; changing the cause is required to make a failed task run again.
- Batch ownership is a kernel-held advisory lock. A second controller is refused, and an interrupted
  controller is provably gone because the kernel released the lock. Ownership is never taken over
  from a recorded PID, so an unknown or recycled PID is never treated as dead.
- `cancel` against a live controller writes a durable request: that controller stops dispatching,
  lets in-flight managed work drain, releases the root and records the verified tasks. Verified
  results are kept, and `run` resumes without new executor attempts. A cancelled batch is never
  integrated or published without a fresh `run`, `prepare` and `review`.
- The coordinator terminates nothing it does not own. A container or command that outlived its
  controller is not stopped by any lock this toolkit holds.

## Integration and reviewed publication

`prepare` creates `.crewloom/worktrees/<batch>/integration` at the expected base and merges the
verified task commits once, in dependency order with ties broken by task ID. Task commits contain
only declared artifacts, so integration carries artifact diffs. A conflict is recorded with its
paths; every branch, worktree, index and evidence file is kept, and nothing is reset, forced or
cleaned. The combined acceptance then runs in that worktree through the same isolated executor. Its
acceptance artifacts are committed deliberately as part of the candidate.

`review` needs the exact base, candidate head and diff digest, and records either a declared
reviewer identifier or a credential-signed proof. In verified mode the project's reviewer registry
is the issuance authority: the HMAC signature, the issuance epoch and revocation are all rechecked.
In declared-label mode nothing is signed, and the report says so. The proof covers the reviewed
artifact set and the acceptance criteria, and a consumed decision cannot be replayed.

`publish` revalidates before the first byte moves: manifest, project and checkout binding, every task
commit, output hashes, criteria, worktree identity, the integration head, the recomputed diff digest,
the proof and its revocation, the root `HEAD`, a clean tracked tree, and untracked collisions
compared by canonical path. Only then does it run one `--ff-only` fast-forward under the project
lock, record the consumed nonce, and release the root reservation. It is not a reset, an arbitrary
checkout, a history rewrite, a push, or a GitHub merge, and untracked files are never cleaned up.

## Ownership of the project root

A batch takes the root for its whole lifetime using the same reservation a managed workflow writes,
so `workflow run` and `crewloom project enter` refuse the root while it is held, and vice versa. The
project lock is held only around short controller state and Git mutations, never around the whole
threaded batch, because each worktree takes its own root lock while it runs.

## Limits, honestly

- One batch per root at a time, at most 4 workers, at most 32 tasks, all against one fixed base.
- A `task` step needs a human review decision that the coordinator deliberately does not grant; use
  `workflow accept` directly for it. A `model` step needs a real command acceptance in the same
  workflow; a model-only task is refused.
- The generation evidence is a recorded digest match, not a quality verdict. Whether generated code
  is good enough is the acceptance command's answer and a reviewer's, and a passing acceptance
  proves only that those commands succeeded on those bytes.
- Project control files — `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `crewloom.project.json` — are never
  committed as task output.
- Batch ownership needs POSIX advisory locking; without it the coordinator refuses rather than guess.
  Git's own fast-forward still has the atomicity limits Git documents, and a crash between the
  recorded publication and the final report leaves the candidate commit in place for inspection.
- A declared-label review names a reviewer. A credential proves possession of a registered
  principal's secret. Neither proves that a distinct human reviewed the work, and neither is an OS
  sandbox against the project owner.
- Managed coordination is not a boundary for arbitrary host tools; a user or agent that writes
  outside these guards is still outside them.

## Evidence

[COORDINATOR_ACCEPTANCE.json](COORDINATOR_ACCEPTANCE.json) records one real three-task batch run
against `python:3.14-slim`: two overlapping workers, a dependent task reading integrated ancestors,
a combined acceptance over the integrated tree, a reviewed decision, and a root fast-forward to the
candidate. The fixture scripts supply the artifacts, so it proves orchestration, isolation,
integration and publication rather than model-generated code.

The model-task cases in `scripts/test_task_coordinator.py` run the same machinery with real `model`
steps against a fixture stand-in provider — no network, CLI or credential — and real container
acceptances that import the generated modules and check their numeric behaviour. With
`CREWLOOM_DOCKER_TESTS=1` they prove two concurrent model tasks in isolated worktrees, per-task
generated modules that no other task can see, a combined acceptance that read the committed
generated bytes, the native CLI opt-in carried end to end, an integration quality failure blocking
review and publication, and an unchanged root until a reviewed fast-forward. They prove the
coordination and verification around generation, not any model's output quality; a live provider run
is a separate, credentialed operator action and is never part of CI.

```bash
python3 -m unittest discover -s scripts -p test_task_coordinator.py
CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p test_task_coordinator.py
```

## Aggregate budget, queueing and cancellation

A manifest may declare an optional `budget`: `max_model_requests`, `max_concurrent_requests`, `max_elapsed_seconds`, `max_input_bytes`, `max_output_tokens`. Each is a positive integer or `null`; a field left out is reported as unbounded. The limits apply to the whole batch across every task worktree, not to one checkout ledger.

Every managed model request is reserved in `admission.json` in the batch's coordinator folder before any attempt, ledger entry or provider call. Reservations are atomic across processes and idempotent by request id, so a resume neither charges again nor receives a replacement slot. A request over a limit is refused; one that only exceeds the concurrency limit is `queued` (it holds no budget) and waits within its own timeout. A resume may keep or tighten the limits, never loosen or reset them.

A request whose owner process ended before its outcome was recorded becomes `orphaned`: it stays charged, its side effects are treated as unknown, and it is never replayed automatically. Token and cost figures appear only when a provider reported them; estimates are reported separately and everything else stays `null`.

The batch records the process and container identities it starts. `crewloom coordinator cancel` and a restart reconcile stop exactly those recorded, after checking the process start time so a reused pid is never signalled, and leave every other process alone. Activity outside the managed controller (a native CLI used by hand) cannot be counted or capped by this ledger. Priority and fairness scheduling are not implemented.

