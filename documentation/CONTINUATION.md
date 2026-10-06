# Continuing a task with another agent

When an agent host stops (quota exhausted, rate limited, authentication lost, timeout, or a crash), the controller already holds what a different agent needs. Crewloom writes a checkpoint from its own records at every workflow boundary, so nothing depends on an exhausted model producing a final summary.

## What is recorded

`.crewloom/handoffs/<workflow>/` inside the selected project holds numbered, hash-chained checkpoints, `latest.json`, a short derived `HANDOFF.md`, and `owner.json`. A checkpoint has the project ID, canonical root, checkout ID and task ID; the plan and policy hashes; the base revision and a content hash for each uncommitted path; completed steps with their input/output hashes; pending and unverified steps; every recorded attempt and the exhausted-attempt list; consumed model requests (tokens and cost stay `null` unless a host reported them); the producer and the interruption cause; and the next safe action. Boundaries are `before_dispatch`, `dispatched`, `after_step` and `complete`.

Credentials, vendor session formats and conversation history are never recorded. Files are private (mode 0600) and stay in the project's ignored `.crewloom`.

## Moving to another agent

```bash
crewloom continuation create   --project /abs/app --plan workflow.json
crewloom continuation interrupt --project /abs/app --workflow handoff-flow --failure '{"kind":"quota_exhausted","confidence":"confirmed"}'
crewloom continuation reconcile --project /abs/app --workflow handoff-flow
crewloom continuation validate  --project /abs/app --workflow handoff-flow --receiver-id agent-b --receiver-host codex --receiver-model gpt-6-sol
crewloom continuation accept    --project /abs/app --workflow handoff-flow --receiver-id agent-b --receiver-host codex --receiver-model gpt-6-sol
```

You choose the receiver; nothing selects a host, changes billing or retries on its own. `validate` refuses when the packet is corrupt or edited, is not the latest checkpoint, belongs to another project/checkout/root (a moved checkout needs an explicit rebind), the plan or project policy changed, another workflow or context task holds the project, a live owner holds the writable slot, or the receiver is not a supported host. It always recomputes the receiver's own [capability profile](../scripts/model_host.py) instead of copying the sender's.

Steps whose recorded outputs still match are reported as preserved; changed ones are listed as stale for scoped re-verification. Uncommitted edits stay where they are: nothing is stashed, reset or committed.

## Safety rules

- One writable owner at a time. A live (`active`) owner is never taken over; `interrupt` or `release` it first. `accept` increments the epoch and keeps the lineage, so a second handoff is traceable.
- An attempt that was still running when the host stopped has unknown side effects. `reconcile` marks it failed with `uncertain_side_effects`; it is never replayed automatically, and it still counts toward the two-attempt limit. Accepting a packet never resets counters or budgets.
- Failures are classified, not merged: quota exhaustion, rate limit (with a retry time, not exhausted quota), authentication, timeout and unknown.

Automatic continuation to a pre-approved host and budget is not implemented; it additionally needs the aggregate budget and cancellation work (W09). Native-host and managed-generation continuation are different execution boundaries and are tested separately; the tests here use a stand-in for the host interruption and establish controller behavior, not model quality.
