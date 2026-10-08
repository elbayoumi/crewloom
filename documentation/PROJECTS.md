# Project isolation

The Crewloom checkout supplies reusable code and role procedures. Each target project supplies its own installed role memory, relative inputs, outputs, and `.crewloom/runs.jsonl` history.

```bash
crewloom install --host agents --target /path/to/project --skill context-guardian
crewloom run --project /path/to/project workflow-contract -- workflow.json
crewloom context --project /path/to/project context-guardian --out /path/to/project/.crewloom/context.md
crewloom dashboard --project /path/to/project --port 4317
```

Without the installed CLI, substitute `python3 /path/to/crewloom/scripts/crewloom.py` for `crewloom`.

- `run` resolves inputs from the selected project (default: current directory), records its canonical root, and writes only that project's run history. Registered path arguments outside the project are rejected, including symlink redirects.
- `context --project` requires exactly one installed role under `.agents/skills` or `.claude/skills`, reads its local memory, and keeps output inside that project. It does not fall back to shared memory. The command without `--project` remains a library-role preview.
- A dashboard process monitors one project. `CREWLOOM_ROOT` selects the library checkout; `CREWLOOM_PROJECT` selects the project. Use separate ports for simultaneous projects. The current project is shown above the totals.
- Project role memory has no fallback to library memory. Repository checks still validate the library, as labeled.
- Installation refuses paths redirected outside the project. Keep project-specific state out of shared public role memory.

Existing unlabelled shared run records are not migrated into client histories: their project identity cannot be safely inferred. Older dashboard processes must be restarted with the project selected explicitly.

These guards apply to the CLI and dashboard entry points. Direct scripts, arbitrary agent tools, files referenced inside supplied packets, and external integrations require their own project-scoped permissions; this is not a filesystem sandbox.

Verification: two-project CLI and dashboard fixtures with identical relative filenames, separate run histories and memories, and rejected cross-project/context/symlink paths. See [the evidence log](EVIDENCE.md).

## Project context lifecycle

A project that wants automatic context writes a portable `crewloom.project.json` and binds itself once:

```bash
crewloom project enter  --project /path/to/project --project-id sample-project --task-id login-fix --role context-guardian --seed src/auth.py
crewloom project status --project /path/to/project --project-id sample-project
crewloom project finish --project /path/to/project --project-id sample-project --task-id login-fix --evidence '[{"workflow": "login-flow", "step": "build", "scope": "unit tests"}]'
```

Entry creates missing metadata, refreshes an existing one and reserves the root. It preserves the project constitution, installed role memory and lesson history. `status` never claims ownership of a running task. `finish` reports `complete` only from recorded executor evidence: `--evidence` names real workflow steps, while `--verification` is an operator attestation that keeps the task awaiting verification and fails closed when it claims a failure. `rebind` is the only supported way to move a checkout, and it rebuilds rebuildable caches without touching durable memory.

Context generations and navigation caches are rebuildable; lessons and task records are durable local memory. Agency projects validate the existing project-control ledger with `--agency-registry` and `--agency-root`, and `needs_reconciliation` permits evidence gathering only. Full contract, lifecycle labels and limits: [project context](PROJECT_CONTEXT.md).

## Installing and updating roles

Fresh installations copy reusable architecture guidance and initialize empty project records. `install --force` refreshes role procedures/tools while preserving all existing brain files and project-local custom files. It does not import completed work, incidents, ideas, or task history from the library. Resolved destination files are checked before copying to prevent nested symlink redirects.

## Multiple projects and tasks

Workflow task actions require an explicit `--project`; the current terminal directory is not inferred as task identity. Use a separate canonical root for each project. Separate roots can execute concurrently with independent project locks, histories and memory. When using dashboards simultaneously, select one root per process and separate ports.

One root admits one active workflow at a time. The process lock covers running commands/model calls. A project-bound `.crewloom/active_workflow.json` reservation also persists while a manual task awaits its artifact/review, preventing a different workflow from taking over between calls. Continue the same workflow or explicitly cancel it before starting another. Copied reservations and redirected runtime paths are rejected.

```bash
crewloom workflow run --project /path/to/project --plan workflow.json
crewloom workflow cancel --project /path/to/project --plan workflow.json
```

Cancellation needs the matching unchanged plan and cannot bypass an occupied process lock. It retains partial files and failure history; inspect them before new work. A cancelled workflow ID cannot resume. Completed and known failed/blocked executions release the reservation; the attempt ledger still prevents unchanged failure loops. Interrupted running state retains ownership until inspected and cancelled. Stale process locks require the existing manual recovery procedure.

For parallel tasks in one Git project, use [the concurrent task coordinator](COORDINATOR.md). It binds one worktree per task under the project's `.crewloom`, runs each task's own workflow there, integrates verified task commits once, and fast-forwards the root only after an explicit reviewed decision. Manual worktrees are still valid: create separate roots and branches yourself, install project-local roles and memory in each, do not copy `.crewloom` runtime state between roots, and review conflicting changes before merging. Direct host tools remain outside both runner guards.

Before client rollout, use the [readiness guide](READINESS.md) to check one explicit registered project against current recorded evidence without modifying its registry, configuration or memory.

## Explicit project catalog

[Project catalog and monitoring](PROJECT_CATALOG.md) adds canonical bound roots, overlap rejection, setup and dashboard task status. Select the same catalog explicitly for each managed host.
