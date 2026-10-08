# Continuing a task with another agent

When an agent host stops (quota exhausted, rate limited, authentication lost, timeout, or a crash), the controller already holds what a different agent needs. Crewloom writes a checkpoint from its own records at every workflow boundary, so nothing depends on an exhausted model producing a final summary.

## What is recorded

`.crewloom/handoffs/<workflow>/` inside the selected project holds numbered, hash-chained checkpoints, `latest.json`, a short derived `HANDOFF.md`, and `owner.json`. A checkpoint has the project ID, canonical root, checkout ID and task ID; the plan and policy hashes; the base revision and a content hash for each uncommitted path; completed steps with their input/output hashes; pending and unverified steps; every recorded attempt and the exhausted-attempt list; consumed model requests (tokens and cost stay `null` unless a host reported them); the producer and the interruption cause; and the next safe action. Boundaries are `before_dispatch`, `dispatched`, `after_step` and `complete`.

**Durability contract.** The `dispatched` checkpoint is mandatory recovery state: it is committed before a command or provider request can start, and if it cannot be committed nothing is dispatched, no output changes, and the attempt is recorded as `dispatched: false` (it still counts toward the two-attempt limit; an admitted batch slot is released as failed, never refunded). Commit order is the immutable sequence record, then `latest.json` by one atomic rename (the commit point), then `HANDOFF.md`; every write is flushed and synced. `latest.json` with no matching sequence record is not a recovery point, and `validate` refuses it. `before_dispatch`, `after_step` and `complete`, plus the display file, are optional: a failure there is written to `checkpoint-error.txt` and the run continues. A project with no binding has no identity to hand over, so it has no required checkpoint and ordinary workflows run unchanged; a binding that is present but invalid fails closed.

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

**The plan is always verified.** `validate` and `accept` resolve the project-relative plan path the checkpoint recorded (`crewloom workflow run --plan` stores it in the run state and every later checkpoint copies it) and refuse unless that file's identity and fingerprint still match; the path may not escape the project, use symlinks or be missing. `--plan FILE` names a different file for the same plan, and is held to the same identity and fingerprint, so an override cannot weaken the check. A checkpoint with no recorded path (a plan run programmatically, or a run started by the coordinator or the context pilot) is refused with a message saying so until the caller supplies `--plan` or, from code, `plan=` with the plan object (`continuation.validate/accept(..., plan=...)`); nothing invents a path or skips the check. A refusal changes nothing: no owner record, ledger, output or uncommitted edit.

Steps whose recorded outputs still match are reported as preserved; changed ones are listed as stale for scoped re-verification. Uncommitted edits stay where they are: nothing is stashed, reset or committed.

## Safety rules

- One writable owner at a time. `accept` validates and claims the slot inside one critical section under the project lock that a running workflow also holds, so two simultaneous receivers cannot both win: the loser is refused with a locked error and claims nothing. `interrupt`, `release` and `reconcile` take the same lock; `validate` is advisory and lock-free. A live (`active`) owner is never taken over; `interrupt` or `release` it first. `accept` increments the epoch and keeps the lineage, so a second handoff is traceable.
- An owner record alone does not authorize work. `accept` returns a one-time `owner_token` (only its hash is stored). Resume a workflow with `crewloom workflow run ... --owner-id ID --owner-epoch N` and the token in `CREWLOOM_OWNER_TOKEN`; the owner id, epoch and token are checked before the run reserves anything, before every dispatch and before artifact publication. A copied id/epoch without the token, a stale epoch, another receiver, a changed project policy or root, or an interrupted slot is refused with no dispatch. A workflow with no owner record, or a released one, runs as before.
- An attempt that was still running when the host stopped has unknown side effects. `reconcile` marks it failed with `uncertain_side_effects`; it is never replayed automatically, and it still counts toward the two-attempt limit. Accepting a packet never resets counters or budgets.
- Failures are classified, not merged: quota exhaustion, rate limit (with a retry time, not exhausted quota), authentication, timeout and unknown.

The earlier manual-only implementation is superseded by the explicit bounded quota fallback below. The aggregate budget and owned-resource cancellation it depends on now exist (W09), but a real Claude-to-other-agent handoff pilot has not been run; the concurrency, fencing and checkpoint guarantees above are established with real validation under controlled scheduling, not with a live vendor host. Native-host and managed-generation continuation are different execution boundaries and are tested separately; the tests here use a stand-in for the host interruption and establish controller behavior, not model quality.

## Explicit receiver dispatch and bounded quota fallback

Coordinator and context-pilot runs persist the exact generated plan under `.crewloom/pilots/<task-id>/workflow.json`; checkpoints record and validate that source. Consumer `workflow.json` is preserved. Other private paths remain forbidden as plan sources.

After `accept`, `workflow run --use-receiver-host --owner-id <id> --owner-epoch <epoch>` uses the authenticated receiver's host/model for pending model steps. Supply the once-returned token through `CREWLOOM_OWNER_TOKEN`, never in a plan or command argument. The immutable plan, artifact scope, policy, prior attempts and budget remain unchanged. A receiver capability fingerprint change refuses dispatch. Native CLI receivers still need operator `--allow-host-cli`.

Automatic quota fallback is explicit and bounded. The following example is configuration, not a statement that either model or account is available:

```sh
crewloom continuation resume --project /path/to/project --plan workflow.json \
  --receivers '[{"id":"backup-agent","host":"openai","model":"YOUR_EXPLICIT_MODEL"}]' \
  --max-switches 1 --max-model-requests 3
```

The receiver list is immutable for that workflow. Switch counts are persisted before transfer; aggregate admission counts survive resume and limits may tighten, never reset or loosen. Only a structured, confirmed quota rejection can trigger a switch. Probable CLI text, rate limits, authentication errors, timeouts and unknown/uncertain effects stop. Native CLI failures carry uncertain side effects, so they need explicit operator review/manual handoff. Outstanding or reconciled uncertain attempts prevent automatic replay. Completed evidence is rechecked and unchanged artifacts stay in place. A settled controller releases only its authenticated owner slot; a controller crash retains state and requires explicit ownership reconciliation, not a blind restart.

Local fixtures prove controller switching and refusal behavior without a provider call. No live Claude-to-another-provider task or billed saving has been established by this change.

## Incoming structure and identity

A correct packet checksum proves byte integrity, not a valid schema or an authorized origin. Validate consumed project/workflow/source/completed-step fields before dereferencing them or claiming an owner slot. Missing or wrong-shaped operational objects produce a named refusal; optional telemetry remains extensible. Receiver IDs must be stable lowercase hyphenated IDs, and a supplied model must be a nonempty string. These checks preserve the existing latest-record, root/checkout, plan, policy, epoch/token and budget fences; they never reset attempts or authorize replay.

## Live same-host acceptance — 2026-10-08

A real limited pilot exercised a manually selected clean boundary between two distinct Codex agents: the first generated the Unicode core, the receiver validated/claimed the packet with an epoch/token fence, generated CLI integration, and completed Docker acceptance. The core and immutable plan were preserved;8 application tests and9/9 independently graded core checks passed. The original failed Claude attempt and counters remained; a shared6-request ledger (also covering a context comparison) refused a seventh before dispatch. [Sanitized acceptance](../examples/evaluation/live-smoke-20261008.json) records the exact scope.

This establishes the exercised same-host managed text-generation handoff. Claude-to-Codex remains incomplete because local Claude authentication was absent. No genuine quota exhaustion, automatic cross-provider switch or arbitrary native-editor continuation was observed. Authenticate the selected second host locally before a new explicitly budgeted pilot; never reset the exhausted pilot ledger or replay uncertain native failures automatically.
