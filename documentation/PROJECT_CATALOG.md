# Project catalog and task monitoring

The catalog is an explicitly selected **machine-local** list of bound projects. Portable identity
stays in `crewloom.project.json`; the agency project-control ledger remains authoritative for
client delivery. Do not commit local paths. Crewloom does not scan the machine for projects.

## Install and prepare

From a source checkout, install with `python3 -m pip install .`. The wheel includes roles and CLI
assets; the dashboard currently requires a source checkout and Node. Choose existing independent
roots. Setup binds identity and installs the context role without replacing existing role memory,
instructions or code:

```bash
crewloom project setup --project /absolute/projects/shop --project-id shop-api --host agents
crewloom project setup --project /absolute/projects/reports --project-id reports-app --host agents
crewloom projects add --catalog /absolute/local/projects.json --project /absolute/projects/shop --project-id shop-api
crewloom projects add --catalog /absolute/local/projects.json --project /absolute/projects/reports --project-id reports-app
crewloom projects list --catalog /absolute/local/projects.json
```

Repeat `--skill` to install selected roles. The default installs only `context-guardian`. Setup
never calls providers, installs project dependencies or starts Git operations. Docker and provider
readiness remain separate: `crewloom workflow doctor --project /absolute/projects/shop`.

## Identity and path rules

- The catalog is an absolute path outside registered roots, with no symlinks or hardlinks.
- Each entry binds project ID, canonical root and checkout ID. Unchanged registration is idempotent;
  reusing an ID for another checkout is refused.
- Registered roots are disjoint. Parent/child roots and case/Unicode-folded overlaps are refused.
- Nested portable projects are refused before bootstrap or workflow execution. The existing
  coordinator's linked worktrees are an exception: the fixed layout and matching Git common
  directory are verified. They cannot be separately registered inside the parent root.
- Moved, redirected or rebound entries are unavailable. Remove the entry, explicitly rebind if
  needed, then register the reviewed root. No identity is silently repaired.
- An exclusive lock covers catalog read/check/write, followed by atomic replacement. A simultaneous
  mutation can be refused; retry after the first completes. Interrupted catalog locks require
  operator reconciliation.

Select the same catalog for runtime overlap checks and monitoring:

```bash
export CREWLOOM_CATALOG=/absolute/local/projects.json
crewloom dashboard --project /absolute/projects/shop
```

Without that environment setting, registration remains checked, but independently launched runners
do not consult the other registered roots. Nested portable-project checks still apply. Unregistered
disjoint projects remain usable with explicit identity. This local guard does not sandbox arbitrary
host tools or establish a global filesystem lease.

## Dashboard and task actions

The authenticated panel displays registered roots, policy mode, reservations, context tasks,
workflows and coordinator batches. Each root is inspected independently. Stale identity and unsafe
state appear as unavailable entries. Existing roles/tools/memory panels still belong to the
selected dashboard project; monitoring does not silently switch its execution root.

Context tasks expose explicit inspection/resume commands and a cancellation button that preserves
files and history. The server resolves the root from registration; browser requests cannot supply
paths. Workflow-owned context tasks must use their original workflow plan for cancellation, so half
an ownership record cannot be released. Coordinator continuation/cancellation uses its original
manifest; see [the coordinator](COORDINATOR.md). Provider execution stays an explicit CLI action.

```bash
crewloom projects cancel-task --catalog /absolute/local/projects.json --project-id shop-api --task-id inspect-shop
crewloom projects remove --catalog /absolute/local/projects.json --project-id reports-app
```

Removal changes registration only; it does not cancel work or delete project files. The catalog
has at most 128 projects and 1 MiB. Monitoring caps task/runtime collections at 128 entries and
individual state at 1 MiB. Dashboard output and read time are bounded.

## Existing execution limits and quality evidence

Use [the coordinator](COORDINATOR.md) for concurrent dependent tasks in one Git project. It creates
worktrees and requires verified integration and review before publication. Separate roots can run
independently; direct host edits stay outside these guards.

The executor already supplies per-step timeouts, evidence-sensitive retry budgets, a request
ceiling and an attempt ledger. These are not a provider-account dollar cap or an aggregate
multi-checkout ceiling. Use provider account spending controls and nullable reported usage/cost;
see [enforcement](ENFORCEMENT.md).

The [context study](CONTEXT_STUDY.md) records one Codex study on three tasks. Its v2 arm passed
99/99 held-out checks with lower measured input tokens. It does not establish every role's quality,
bilingual role advantage or provider comparisons. Deterministic fixtures cover both languages;
live cross-provider/bilingual quality evaluation still needs authenticated providers and frozen
tasks. Mock transport passes cannot replace that evidence.
