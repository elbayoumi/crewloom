# Project context

Project context gives a registered task the minimum evidence it needs inside one project: a stable project identity, a local checkout binding, a bounded navigation index, a frozen task context, and lessons that only an objective check can promote. It is opt-in per project. Nothing here changes workflow isolation, provider defaults or host permissions.

## Identity and files

Two identities are always required. A remote URL, a folder name or the last chat message is never accepted as identity.

| Path | Scope | Contents |
| --- | --- | --- |
| `crewloom.project.json` | portable, reviewed, committable | schema version, project ID, tooling attribution, policy, source roots, exclusions, language, byte budgets, host adapter |
| `.crewloom/binding.json` | local to this checkout | canonical root, project ID, checkout ID, configuration fingerprint, relocation history |
| `.crewloom/index/map.json` | rebuildable | one versioned symbol generation keyed by project and checkout |
| `.crewloom/context/<task-id>.json` | rebuildable | one frozen context generation with rules, criteria, navigation, ranges, lessons, bodies and recorded omissions |
| `.crewloom/tasks/<task-id>/state.json` | durable task record | ownership, lifecycle label, verification evidence, refresh results, metrics |
| `.crewloom/lessons/<lesson-id>.json` | durable local learning | candidate/verified/invalidated/superseded lessons with conditions and evidence |
| `.crewloom/active_task.json` | runtime | the reservation that serializes writers of this root |

`crewloom.project.json` contains no absolute machine paths, credentials or client history. Its attribution block describes tooling, never ownership of client code:

```json
"tooling": {"vendor": "Rumuze", "tool": "Crewloom", "role": "tooling", "owns_client_code": false}
```

Existing customer instructions and installed role memory are never rewritten. `AGENTS.md` or `CLAUDE.md` is only touched when `host_adapter.enabled` is true, and then only between managed markers that this repository replaces idempotently. The managed block is written before the context is frozen, so the generation hashes the final instructions file; the customer text around the markers is preserved byte-for-byte. Each command in the block is one runnable shell line, with the exit evidence given as a shell-quoted JSON argument.

## Entry, status, finalization

```bash
crewloom project enter  --project ROOT --project-id ID --task-id TASK --role ROLE [--seed PATH] [--source PATH] [--criteria FILE]
crewloom project status --project ROOT --project-id ID
crewloom project finish --project ROOT --project-id ID --task-id TASK --changed PATH --evidence '[{"workflow": "flow-id", "step": "acceptance", "scope": "unit tests"}]'
crewloom project cancel --project ROOT --project-id ID --task-id TASK --reason TEXT
crewloom project rebind --project ROOT --project-id ID --reason TEXT
```

Entry is idempotent. Missing metadata is created with complete schemas; existing metadata is validated and reused; the project constitution, role memory and lesson history stay untouched. Repeating entry refreshes navigation and reuses the frozen generation when nothing semantic changed, so telemetry alone never increments it. The generation fingerprint covers semantic content only: the generation counter, the recorded payload size and telemetry-derived values are excluded, so an unchanged task keeps one generation however often it is re-entered. Every superseded generation stays readable under `.crewloom/context/history/`.

Local runtime state stays out of version control: bootstrap appends a single `.crewloom/` rule to `.gitignore` when one is missing and never rewrites existing rules.

Every writable metadata path is validated before the first write. Malformed schemas, ambiguous or missing identity, foreign or corrupt local bindings, path escapes, symlinks and hardlinks are rejected without leaving a half-created project behind.

Entry reserves the root. Ownership is checked before any snapshot, instruction or task record is written, so a task rejected for a conflict leaves the owner's metadata byte-identical. A second task, an unfinished managed workflow, or a running project lock blocks it, and a managed workflow refuses to start while a native context task owns the root. Two projects or worktrees in different roots stay parallel. Project-lock ownership is per process and thread, so a forked child contends for the lock instead of inheriting it.

Finalization is idempotent and honest. `--evidence` names workflow steps this project's executor recorded, and only that recorded evidence can complete a task. `--verification` is an operator attestation: it is recorded as a claim, it never completes a task, and a claimed non-zero exit fails closed. The outcome is `complete` only when every correlated executor check passed, `awaiting_verification` when no executed evidence was supplied, and `failed` when a check failed. A failed task is never relabelled successful by a later call.

`rebind` is the only way to move a checkout. Ordinary entry refuses a binding that belongs to another root. Explicit relocation records where the checkout came from, rebuilds the navigation and context caches, and keeps durable lessons, role memory and task history.

## Agency project control

Agency tasks validate the existing project-control ledger; this repository keeps no second client list.

```bash
crewloom project enter --project ROOT --project-id ID --task-id TASK --role ROLE --agency-registry .agents/project-control/registry.json --agency-root AGENCY_ROOT
```

`--agency-root` is required because ledger paths are relative to the agency workspace. The adapter validates the ledger contract: schema version 1, unique lowercase IDs, `active_dir` and `context_snapshot` inside the agency workspace and its active directory, `delivery_owner` and `next_action.owner` naming installed roles, `control_status` from `needs_reconciliation`, `blocked`, `in_progress`, `ready_for_review`, `approved`, `last_verified_at` ISO-8601 (null only for `needs_reconciliation`), and `state_evidence` with a matching SHA-256, a known `source_type` and an ISO-8601 `observed_at`. `--agency-validator` runs an explicitly selected agency validator first, and a non-zero result blocks entry.

`needs_reconciliation` and `blocked` allow evidence gathering only. Enforced context is refused for them, and implementation is never assumed to be authorized.

## Frozen context and code ranges

Each task freezes one generation scoped to project ID, checkout ID, canonical root and task ID. It contains the full governing rules and acceptance criteria first, then a bounded navigation map, bounded verified lessons, suggested read ranges, explicitly declared source bodies, and an explicit list of omitted optional records.

Optional evidence is admitted by exact remaining serialized bytes, not by a fixed count. Rules, criteria, declared bodies and seed navigation are never traded away; related test hints and dependency neighbour hints are kept until the remaining room is spent, and what did not fit is recorded as an omission. The indexed file inventory is recorded as a digest plus a bounded sample, so a large repository cannot grow the generation.

Suggested read ranges are the exception: they carry their own modest allowance instead of whatever the global ceiling leaves over. `budgets.range_bytes` sets it and defaults to `map_bytes`, and at most 64 range records are kept across all files, seed ranges first. A large context ceiling is permission for large required sources, never a target to fill with unrelated symbol hints; every omitted range is recorded with its real count.

Byte budgets are explicit in `crewloom.project.json`: `context_bytes` for the whole frozen generation, `map_bytes` for the navigation index, `lesson_budget_bytes` for verified lessons and `range_bytes` for suggested ranges. Verified lessons are additionally measured as the exact JSON array that is stored, so an oversized remedy is recorded as omitted instead of being trusted to a record count.

A range cache key covers project ID, checkout ID, the normalized project-relative path, file SHA-256, line range, policy version and parser version. Two identical files therefore resolve separately, and neither key resolves in another project root. Reading a range requires the stored hash to still match, so a changed file can never keep a stale line reference. Managed model calls cannot fetch code, so only explicitly declared source bodies leave the coordinator; a required body that does not fit is refused from its declared size, before its bytes are read, instead of disappearing.

Freshness uses the same inventory the index itself would scan — configured source roots, exclusions, size caps, decodability and scan budgets — so a file outside the configured scope never invalidates a frozen generation while an in-scope create, delete, rename, branch switch or configuration change always does. The scan caps are enforced before the candidate is read and every candidate byte counts against the aggregate budget, including bytes a failing decode later discards, so unreadable files cannot buy unbounded reads or make an over-budget project look fresh.

## Lessons

Lesson states are `candidate`, `verified`, `invalidated` and `superseded`. Every record carries the issue, the applicable conditions, a concise remedy, the source task, a verification reference, input/output fingerprints and provenance.

Promotion requires evidence this checkout's executor actually produced:

```bash
crewloom lesson verify --project ROOT --lesson-id ID --evidence '[{"workflow": "flow-id", "step": "build", "scope": "unit tests"}]'
```

The referenced workflow state and attempt ledger must contain a recorded attempt with a real exit code, and its signature must exist in the project attempt ledger, correlated to the same workflow, step and outcome. Provider generation is not an acceptance check. Every output hash is re-read before promotion, an in-place input/output is validated against its post-execution hash, and a changed or vanished non-output input invalidates reuse instead of passing quietly. Described, planned or self-asserted checks cannot promote a lesson; a native or external attestation is recorded for review and never promotes on its own. Failed checks, and artifacts or inputs that drifted after a recorded success, keep the lesson a candidate and are labelled negative evidence; a later passing verification makes the remedy retrievable again while the earlier failures stay in its history. A changed policy configuration, declared source or verified input invalidates a verified lesson. Stored commands are references for a human operator and are never executed by this repository.

Export is explicit and reviewed, verifies project identity, and strips nothing silently. Import verifies the project ID and leaves every imported lesson a candidate that must be re-verified locally.

Project entry revalidates verified lessons before selecting them, so a changed policy configuration, declared source or verified input invalidates the lesson automatically instead of waiting for an operator to run `crewloom lesson revalidate` by hand. A stale remedy is neither delivered to a model nor left claiming to be verified.

## Lifecycle labels

| Label | Meaning |
| --- | --- |
| `managed-runner` | the Crewloom managed runner performs entry, per-step checkpoint and finalization for this project |
| `instruction-assisted` | a bounded managed reference is written into the authorized instruction files and the operator runs the commands |
| `manual` | context selection is off; nothing automatic happens |

Opening a folder never invokes any of this by itself. `status` reports `host_callbacks_verified: false` for every project because no host folder-open callback has been verified here.

Policy modes are `off`, `observe` and `enforced`. `off` performs no automatic selection. `observe` builds and records context without gating managed publication. `enforced` additionally refuses to publish managed artifacts against a stale snapshot and fails the run when finalization cannot record evidence. Disabling selection deletes no durable memory and does not loosen workflow isolation.

## Navigation index

`repo_map.py` is the project-local index behind the context. Generations, schema and parser versions are explicit. Every refresh re-reads and re-hashes candidate bytes, so reuse saves parsing and transmitted context, never all disk reads. Git status nominates changed, untracked, deleted and renamed paths; hashes decide freshness, and modification time or size alone is never proof.

Python extraction uses the standard AST, including relative and absolute import resolution. A standard-library import is an external dependency rather than an unresolved project edge. JS/TS extraction remains approximate: methods, arrows and nested definitions can be missed, and package, alias and re-export resolution is a deferred adapter. Unresolved imports and approximate files are reported as incomplete rather than hidden, and the map never claims a comprehensive graph. Seed paths always appear even when their symbol list exceeds the byte budget.

`source_roots` and `exclude` in `crewloom.project.json` control the scan. Root aliases, symlinked source roots and paths escaping the canonical root are rejected. Non-Git roots are unsupported until an explicit adapter exists; Crewloom never runs `git init`.

## Managed runner integration

With `managed_lifecycle` enabled the managed runner enters before context construction, checks the frozen snapshot before every step, rebuilds it when a relevant source or the declared per-step sources changed, blocks managed publication on stale evidence, and finalizes with real executor evidence. The existing project lock, attempt ledger, artifact broker and provider restrictions are unchanged; the runner reuses them rather than introducing a second protocol. When that entry is refused — a declared source larger than the context budget, for example — the reservation is recorded and explicitly cancellable, so a failed start never leaves the root reserved forever, and no declared file is modified.

A managed model call receives the frozen evidence itself, not only a stored snapshot: the scope, generation, semantic SHA-256, complete governing rules, acceptance criteria, navigation index, verified remedies, bounded ranges and recorded omissions travel in the prompt. A resumed or repeated step is re-bound to the immutable archived generation it originally consumed, so the same call keeps the same frozen identity instead of drifting to a newer generation; a record that never recorded its generation cannot be reused. A managed map request obeys the bound project's source roots, exclusions and scan caps instead of scanning a wider tree.

## Measurements

```bash
python3 scripts/context_pilot.py --out /tmp/pilot.json
python3 scripts/context_pilot.py --project /path/to/project --seed PATH --criteria FILE --acceptance-input PATH --out /tmp/pilot.json
```

The synthetic suite measures two project sizes so the crossover is reported rather than assumed, and records cold and warm index counts and durations, selected versus full context bytes, the exact serialized payload size, recorded omissions and acceptance results. Acceptance executes the frozen `python3 -m unittest discover -s tests` check inside the isolated Docker executor over every file that check reads, and finalization is verified only through correlated executor evidence. A real project is never initialized or altered by the pilot: it must already be bound and must name its own seed, criteria and acceptance inputs. The pilot never calls a provider, so token, cache and cost effects stay unknown until a real provider reports them; without a reachable Docker daemon it reports `executed: false` with a reason instead of claiming verification.

## Limits

- Bounded selection helps once indexed source exceeds its fixed overhead; small projects can be larger than the full context.
- JS/TS symbol extraction and dependency resolution are approximate and incomplete by design.
- Reviewer identities are declared by default; a project that opts into `policy.review.mode: verified` requires an authenticated registered principal, which still proves credential possession rather than independent human review. See [execution](EXECUTION.md).
- Project context controls Crewloom-managed entry and finalization; arbitrary host tools and host folder-open events remain outside it.

The [two frozen public-project runs](../examples/evaluation/project-context-20261003/README.md) passed all nine navigation/context checks in English and Arabic, including the full declared source, managed finalization, verified lessons and one-attempt reuse. Selected payloads were 43,231 bytes for Crewloom and 54,106 bytes for the scoped Paperclip UI. These are navigation byte measurements; provider token and cost effects remain unknown.

Before client rollout, use the [readiness guide](READINESS.md) to check one explicit registered project against current recorded evidence without modifying its registry, configuration or memory.
