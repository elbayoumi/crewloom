# Project scheduling and shared admission

Crewloom schedules explicitly registered projects on POSIX hosts with advisory locks. It never discovers a project from a previous task or from matching filenames. Queue records contain identities and control metadata; source files, generated artifacts, context, and execution history remain inside each selected project.

## Set up a queue

Register disjoint canonical project roots using the existing catalog. Keep the catalog and shared queue outside project roots. Control directories must be owned by the current user with mode `700`; symlink and hard-link control records are refused.

```bash
crewloom projects add --catalog "$HOME/.local/state/crewloom/catalog.json" --project /work/shop --project-id shop-project
crewloom queue enqueue --directory "$HOME/.local/state/crewloom/queue" \
  --catalog "$HOME/.local/state/crewloom/catalog.json" --project-id shop-project \
  --manifest coordinator.json --priority 20
crewloom queue run --directory "$HOME/.local/state/crewloom/queue" --workers 2
crewloom queue status --directory "$HOME/.local/state/crewloom/queue"
```

Higher priority runs first; ties keep insertion order. Queue priority and optional coordinator task `priority` are integers from `-100` to `100`, defaulting to `0`. Task dependencies always take precedence over priority. Scheduling is nonpreemptive: increasing another job's priority cannot interrupt a running task.

One dispatcher owns each queue. It may run up to four different projects concurrently, with at most one batch per canonical root. Each batch retains the coordinator's own bounded task workers, Git worktrees, Docker acceptance, cancellation, and review requirements. Queue worker count limits concurrent projects; it is not a combined container limit.

The dispatcher drains eligible jobs, including jobs enqueued while it is running. It exits when nothing can run. A project reserved by a different workflow, native task, or batch remains queued with `waiting_for`; after releasing that reservation, run the queue again. This is an explicit local dispatcher, not an installed background service or calendar scheduler.

A queued project's root and checkout identity are checked again at execution. The manifest digest and semantic workflow-plan fingerprints must match the queued intent. Changed or redirected projects fail before execution. An interrupted dispatcher marks unfinished jobs `interrupted`; it does not automatically repeat potentially billed work. Inspect the batch and explicitly retry:

```bash
crewloom queue retry --directory "$HOME/.local/state/crewloom/queue" --job-id JOB_ID
crewloom queue cancel --directory "$HOME/.local/state/crewloom/queue" --job-id JOB_ID
```

Queue cancellation applies to queued jobs. Cancel an active batch using `crewloom coordinator cancel` with its original project and manifest. Verified queue jobs retain their task worktrees and wait for the existing `prepare`, `review`, and `publish` workflow. The queue never grants a review or publishes changes. Native CLI generation still requires the manifest opt-in and the dispatcher's explicit `--allow-host-cli` flag.

## Share generation limits across checkouts

Create one explicit budget period and give all managed runners the same directory:

```bash
crewloom budget configure --directory "$HOME/.local/state/crewloom/budget-period-1" \
  --max-requests 50 --max-usd 10 --reserve-usd 1
export CREWLOOM_USAGE_BUDGET="$HOME/.local/state/crewloom/budget-period-1"
crewloom budget status --directory "$CREWLOOM_USAGE_BUDGET"
```

The numbers above are operator-selected admission allowances, not published provider prices. Dollar fields are optional, but configuring them requires both a period allowance and a positive per-call reservation.

Before each managed model-generation invocation, a kernel-locked ledger reserves one request and its dollar allowance. Reservations are shared across projects, coordinator worktrees, threads, and processes using that directory. A refused reservation makes no provider call and creates no provider attempt. Existing per-checkout ceilings continue to apply.

Reported cost settles a reservation. A reported zero releases its dollar allowance but retains the consumed request. A failure, unknown cost, or crashed call retains its allowance; unknown does not mean free. A reported overrun is visible and blocks further admission. Existing periods cannot be reset in place; select a new explicit period rather than erasing live reservations.

These limits cover **managed generation invocations** through `workflow.run_model_step`. A CLI may make internal calls or retries, and outside tools or direct evaluation calls are outside this ledger. Dollar reservations cannot stop a vendor from charging more than the allowance on an admitted request. This is conservative admission control, not a vendor-enforced account billing cap or an OS sandbox.

## Dashboard

Set `CREWLOOM_QUEUE` and `CREWLOOM_USAGE_BUDGET` on the dashboard server to monitor the selected controls. The authenticated overview reads status; browser requests cannot choose control paths or launch jobs. Errors and unknown cost remain visible. The dashboard shows the latest 100 queue records and bounded project-local tool history (up to 1 MiB / 1,000 records), UTC day buckets, role failures, and mean duration. Those charts describe registered tool runs, not a complete provider billing history.
