# Isolated software workflows

Crewloom executes a project-owned plan, records evidence, and exports the next role's handoff. Model steps use the provider gateway described in [managed enforcement](ENFORCEMENT.md). A command step runs an actual argv array; a task step pauses for your agent or human to produce and review an artifact.

## Requirements and readiness

Python 3.9+ on Linux, macOS or WSL, Docker with a working daemon, and a locally available execution image. Pull the image explicitly, then inspect readiness:

```bash
docker pull python:3.14-slim
crewloom workflow doctor --image python:3.14-slim --project /path/to/project --host agents
```

The report identifies the image by content ID. Python and Git readiness, installed role folders, and Docker/image availability are separate facts. Host-model execution is not asserted by the layout check. Images need the tools your commands use; the sample Python image does not include Node, browser tooling, or your dependencies. Build those dependencies into your own image before offline execution.

## Run a real example

Copy [the example project](../examples/software-workflow/project) into a separate directory. It contains a concrete Unicode slug feature, English and Arabic acceptance cases, and six executable stages.

```bash
cp -R examples/software-workflow/project /tmp/crewloom-demo
crewloom workflow run --project /tmp/crewloom-demo
crewloom workflow status --project /tmp/crewloom-demo
crewloom workflow handoff --project /tmp/crewloom-demo
```

Use a new destination if it already exists. Without the installed CLI, replace `crewloom` with `python3 /path/to/crewloom/scripts/crewloom.py`.

The example copies a supplied implementation, parses it, runs five acceptance tests, and produces a hashed delivery report. The role labels identify stage ownership; they do not mean six AI agents participated. This proves workflow execution and bookkeeping, not model-generated feature quality or independent semantic review.

## Plan contract

`workflow.json` has `schema_version: 1`, a stable kebab-case `id`, optional `language` (`en` or `ar`), and an ordered `steps` array. Each step declares:

| Field | Meaning |
| --- | --- |
| `id`, `role`, `summary` | Stable step identity, installed catalog role ID, concrete intended result |
| `kind` | `command` (default), `model`, or `task` |
| `argv` | Nonempty command argument array; no shell expansion is performed |
| `inputs` | Nonempty files to fingerprint before execution; the list itself may be empty |
| `outputs` | Nonempty files expected from this step; one owner per artifact |
| `timeout_seconds` | Integer from 1 to 3600; default 60 |

Paths are relative to the canonical project root and may not escape it through `..` or symlinks. Artifacts cannot own `.git`, `.crewloom`, or the plan itself. Steps execute in declared order. List scripts, configuration, requirements, and dependencies as inputs when their changes should invalidate earlier evidence.

Use [the software task plan](../workflows/software-feature.json) for agent-produced artifacts. Copy it into your project as `workflow.json` and install its roles with `crewloom install --host agents --target /path/to/project`. Replace QA task steps with actual project test commands when available; do not substitute a successful placeholder command.

## Tasks and handoffs

A `task` step pauses with status `awaiting_task`. `handoff` returns the same project root, language, next owner, expected inputs/outputs, role setup, and completed artifact fingerprints. Read the selected installed role and project memory, produce the artifact, and have a distinct reviewer identifier acknowledge completion:

```bash
crewloom workflow accept --project /path/to/project --step requirements --reviewer reviewer-alex
crewloom workflow run --project /path/to/project
```

Only the next outstanding task can be accepted. Files must exist and be nonempty; upstream fingerprints must remain unchanged. Configure host permissions separately for manual agent tasks; they do not run inside the command container.

## Credential-verified reviewers

A bare `--reviewer NAME` is a recorded declaration: it names someone, it does not authenticate them. A project can opt in to verified review instead, and then a decision is refused unless an authenticated registered principal made it:

```json
{"policy": {"review": {"mode": "verified", "allow_self_review": false}}}
```

```bash
crewloom reviewer register --project /path/to/project --principal reviewer-alex
CREWLOOM_REVIEWER_TOKEN="$(cat /path/to/project/.crewloom/reviewer-token-reviewer-alex)" \
  crewloom workflow accept --project /path/to/project --step requirements
crewloom reviewer revoke --project /path/to/project --principal reviewer-alex
```

What this actually enforces, and what it does not:

- The issuance authority is `.crewloom/reviewers.json`, resolved with the internal runtime path rule. It is not a trackable project file, so it cannot be declared as a workflow input or output, copied into a task context body, committed, or indexed. Only its SHA-256 token hashes are stored; the token itself is written once to an owner-only `.crewloom/reviewer-token-<principal>` file and is never printed unless `--show-token` is passed. Credentials are accepted from `CREWLOOM_REVIEWER_TOKEN` or standard input, never from a command line.
- Each stored decision is HMAC-signed with a key derived from that principal's token hash and issuance epoch. Editing the principal, decision time, project, checkout, task, artifact, or criteria invalidates the signature; revocation and reissue rotate the epoch, so an earlier approval stops verifying.
- On POSIX the registry must be a single-link regular file owned by the current user with no group or other permission, and a refusal stops verified review from authorizing anything. Platforms without POSIX permission bits cannot be checked this way; use filesystem access control there, and do not read a successful load as proof of exclusive access.
- This bounds record tampering and casual disclosure. It is not an OS sandbox: every process running as the project owner can read the registry, and arbitrary tools run as that owner stay outside the boundary.
- Possession of a credential proves the caller holds a registered principal's secret. It does not prove a distinct human reviewed the work.
- Only `workflow accept` for a `task` step is gated. Acceptance commands still need executor evidence, and lesson promotion and lesson verification keep their own executor evidence. A reviewer credential never substitutes for either.

## State, resume, and failure

State lives in `.crewloom/workflows/<id>/state.json`; the failure ledger lives in `.crewloom/attempts.json` and includes the canonical project root, plan fingerprint, roles, inputs/outputs, command attempts, exit codes, image ID, duration, and output capture capped at 64 KiB (additional output is drained and discarded).

- Re-running a completed workflow verifies fingerprints and skips successful commands.
- Changed completed inputs/outputs or a changed plan reject old evidence. Review changes and use a new workflow ID; old history remains available.
- Command failure or missing/unchanged pre-existing output stops the workflow. Two failed or interrupted attempts with unchanged command, inputs, and image block another attempt. A project-wide ledger carries this budget across workflow IDs; renaming the workflow cannot reset it. Successful attempts do not consume the failure budget. Change the actual cause before retrying.
- A project-wide lock prevents concurrent workflows from writing the same project. A lock left behind by a process that is provably gone is reclaimed automatically, under an exclusive reclamation claim and after verifying the exact inode the record was read from, so a competing live owner is never removed with a stale record. Reclamation does not stop a command or container that outlived its process: after a host crash, inspect the lock PID and Docker containers and stop anything still running. A `.reclaim` path that is a symlink or that holds anything this protocol did not create blocks the root and needs manual reconciliation. There is no automatic unsafe lock takeover.
- Managed commands publish only validated declared outputs after success; failed commands publish nothing. One declared output group is published as one recoverable transaction: the whole group and every input fingerprint are checked before the first write, the group is staged with a backup of every destination under protected `.crewloom`, and the project lock is held for the whole publication and its recovery. A failed group is rolled back to the recorded content and mode after every journal record is validated; a writer killed mid-group is reconciled by the next managed publication, project entry or workflow run before it reads state, freezes context or records acceptance. A destination that no longer matches its journal blocks recovery and keeps its journal for manual review. Publication across several files is not an instant atomic filesystem change, so a reader that ignores the project lock can observe a group half applied.

Exit 0: complete workflow, successful task acceptance, readable status/handoff, or ready doctor. Exit 2: blocked/failed/awaiting-task execution or unavailable setup. The JSON status is authoritative for progress.

## Isolation boundary

See [managed enforcement](ENFORCEMENT.md) for input snapshots, declared writable outputs, provider RPC, resource limits, and the trusted-host boundary. Manual tasks and explicitly enabled native CLI hosts remain outside that boundary.

## Project ownership between task steps

`run`, `status`, `handoff`, `accept` and `cancel` require `--project`. An active-workflow reservation persists across `awaiting_task`, so a second task cannot take the same root while the first awaits an artifact. Running invocations still use the project process lock. Finish or explicitly `cancel` the matching workflow before switching tasks. Cancellation preserves files/failure history and prevents resuming that ID; inspect partial artifacts first. See [parallel project rules](PROJECTS.md).

## Parallel tasks in one root

One root runs one workflow at a time. Independent work that belongs to the same project is run as a batch instead: [the concurrent task coordinator](COORDINATOR.md) gives each task its own Git worktree, runs the same managed executor inside it with up to four concurrent tasks, and moves the root only after an explicit reviewed decision.
