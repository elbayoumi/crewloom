# Automatic project context: implementation plan

Status: implemented for opted-in projects, measured locally, and documented in [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). The lifecycle labels, deferred adapters and remaining evidence gaps below are unchanged by that implementation. Two authorized public-project English/Arabic navigation and lifecycle pilots are complete; client delivery, host folder-open callbacks and general provider billing effects are not claimed.

## Objective

A registered agency task should initialize missing Crewloom project metadata, reuse existing valid context, refresh navigation after verified edits, and retain evidence-backed lessons within that project. The map is a navigation index; actual relevant code and governing instructions remain necessary. Evaluate input-token reduction, latency and correctness independently.

## Current foundation and gaps

- `repo_map.py` extracts Python AST symbols and approximate JS/TS definitions, caches by SHA-256 and renders a bounded task map. Every refresh still reads candidate source bytes; it saves parsing and transmitted context, not all disk reads.
- `model_host.py` supports explicit map inclusion and bounded historical memory. It preserves declared source inputs and checks prompt hashes on completed-model reuse.
- The agency already owns a project-control registry and a project-ID-aware context-pack builder. Reuse that registry for client identity rather than creating a competing client list.
- Missing lifecycle: idempotent initialization, portable metadata versus local root binding, centralized enter/finish hooks, authenticated evidence-linked learning and coherent context snapshots.
- JS/TS regex extraction can miss methods, arrows or nested definitions and match misleading text. Current import-neighbour hints do not cover package resolution, aliases, re-exports or Python relative-import semantics reliably.
- A rendered map can omit a seed file whose whole symbol block exceeds the budget. Add guaranteed seed-path representation and explicit completeness before unattended adoption.
- Existing root-only caches need schema migration. Process locks must be reconciled with paused-workflow ownership from the project-scope change before parallel adoption; do not create a second lock protocol.

## Identity and files

Two identities are required: a stable project ID and a checkout ID. Git worktrees share the project ID but have distinct checkout IDs, roots, task ownership and local caches. A remote URL is descriptive evidence, not a unique identity: forks, local projects and multiple worktrees make that assumption unsafe.

Proposed portable file: `crewloom.project.json`, containing schema version, project ID, Crewloom/agency attribution, policy reference, configured source roots, exclusions, language, budgets and explicitly enabled host adapter. It contains no absolute machine paths, credentials, client history or automatic publishing settings. Attribution describes tooling, not ownership of client code. Preserve pre-existing customer rules and licensing.

Proposed local layout:

```text
crewloom.project.json                 portable, intentionally reviewable
.crewloom/
  binding.json                       canonical root + project/checkout IDs
  index/                             rebuildable symbol cache and generation
  context/<task-id>.json              selected evidence and fingerprints
  tasks/<task-id>/                    task state, verification and finalization
  lessons/                           project-local candidate/verified lessons
```

`.crewloom/` remains excluded from version control by default. Portable configuration is committed only as a normal reviewed project change. Local learning does not magically move to another machine: optional approved export/import must strip sensitive details, verify project identity and invalidate stale evidence. Existing installed-role memory remains valid; expose it through the context selector rather than silently migrating or duplicating it.

## Lifecycle contract

Proposed commands, not current CLI capabilities:

```text
crewloom project enter --project ROOT --project-id ID --task-id TASK --role ROLE
crewloom project finish --project ROOT --project-id ID --task-id TASK
crewloom project status --project ROOT --project-id ID
```

### 1. Resolve and preflight

Resolve an explicit canonical root and project ID. Agency client tasks validate the existing control registry and respect `needs_reconciliation`: evidence gathering is allowed, implementation is not assumed authorized. Public standalone projects may supply their own explicit ID. Missing or conflicting identity requires clarification; never guess from the last chat, folder name or matching filename.

Validate all writable metadata paths, including resolved parents, links and root containment, before creating files. Reuse the current root lock and task-reservation semantics. Distinct roots/worktrees can run independently; two writers sharing one root must serialize or report a conflict. Read-only status does not claim ownership of a running task.

### 2. Idempotent bootstrap

Missing metadata is created with complete schemas and bounded defaults. Existing metadata is validated and reused. Repeating entry must preserve project memory, customer instructions and installed role brain. A copied/renamed project with conflicting local binding must not be silently rebound. Explicit relocation regenerates local caches and checks reusable memory provenance.

Do not run Git initialization, dependency installation, model requests, global host-setting changes or deployments during bootstrap. Existing non-Git projects need an explicitly configured source-root/ignore adapter; initially report unsupported instead of making their entire filesystem discoverable.

### 3. Refresh navigation

Version the extraction schema and parser implementation. Prefer precise parsers; Python AST is available now, optional Tree-sitter for JS/TS is a later adapter with pinned dependencies and fixtures. Unsupported syntax remains visible as incomplete navigation; never pretend the map is comprehensive.

Use Git status/diff plus create/delete/rename detection to nominate changed files, and hashes to verify actual content. Modification time and size alone are not proof of freshness. Task-boundary reconciliation must detect untracked edits, branch switches, external changes and configuration/parser changes. Initial correctness-first mode may hash all candidates; enable a faster metadata/event path only after adversarial freshness tests establish its limits and periodic full reconciliation is implemented.

Write map generations atomically under the project lock. A crash leaves the previous generation marked stale, not a half-written current index. Deletions are pruned; renames move navigation without inventing evidence. Enforce file-count, scan-byte and output budgets with explicit completeness counts. Cache corruption triggers an explicit safe rebuild; identity/path corruption blocks writes.

### 4. Assemble minimal task context

Include project binding, full applicable rules and acceptance criteria first. Select seed files, related tests, directly resolved dependencies and verified relevant lessons. Return explicit omissions and unsupported dependency-resolution cases. Represent seed paths even when their full symbol list exceeds the map budget.

Provide paths and ranges for actual code reads. A range’s cache key includes project ID, checkout ID, file hash, line range, policy and parser versions. A change invalidates old line references and related context. Never reuse a response across projects solely because file text matches.

A tool-free managed model cannot fetch extra code itself: the trusted coordinator must prepare declared source inputs or obtain missing context through a bounded additional stage. Native agents can read suggested ranges using their host tools, but those reads remain subject to host permissions. Do not infer readiness from a map alone.

Stateless API requests still need their required context each time. Local parsing reuse and compact selection do not guarantee provider prompt-cache hits or elimination of repeated billed input. Record the provider’s actual usage when reported.

### 5. Execute and checkpoint

Carry project ID, checkout ID, task ID and context generation through every handoff. Record the source hashes actually consumed. If a relevant source changes before write/publication, invalidate the snapshot and rebuild the affected context instead of publishing against obsolete evidence. For arbitrary native host writes, pre-write verification depends on a supported host integration; the repository cannot force all external tools through this checkpoint.

Existing managed command isolation and artifact broker continue to own execution permissions. Task orchestration must not let a generated plan or a learning record modify the trusted runtime’s policy. Changing language changes human-readable context, not identifiers or isolation rules.

### 6. Verify and finalize

Finalization records the actual changed files, verification command/exit/result, evidence fingerprints and remaining problems. Refresh the index only after writes settle; failed edits still need refreshed navigation but must not be labeled successful. A crash/interruption marks the task incomplete; next entry reconciles before using old context. Finalization is idempotent and cannot duplicate a lesson or repeat an external action.

Lesson states are `candidate`, `verified`, `invalidated` and `superseded`. Required fields include issue, applicable conditions, concise remedy, source task, command/evidence reference and input/output fingerprints. Model statements alone cannot promote a lesson. Objective checks can establish technical observations; general recommendations or ambiguous root causes require review. A test pass proves its tested scope, not universal correctness.

Retrieve verified lessons for matching conditions; keep failed attempts as labeled negative evidence. Revalidate after relevant dependency/policy changes. Deduplicate without erasing provenance. No automatic execution of commands stored in lessons. Shared agency memory receives only reviewed, sanitized reusable knowledge; project-specific history stays local.

## Host integration

The first supported path is the Crewloom-managed task runner: entry before context construction and finalization after verified publication, with interrupted-state recovery. This provides reliable lifecycle control.

For native agency agents, add a small project-scoped instruction entry point using the host’s supported project rules. Preserve an existing AGENTS.md/CLAUDE.md constitution; add a bounded managed reference only where authorized and verify idempotent updates. Native host adapters must capability-check actual documented entry/finalization hooks; do not invent hooks or claim that opening any folder invokes them.

If the host has no reliable lifecycle callbacks, use an explicit agency task launcher and project instruction fallback. The UI/status must say automatic runner lifecycle, instruction-assisted native lifecycle, or manual lifecycle accurately. Keep global machine configuration unchanged.

## Implementation status

| Area | State | Where |
| --- | --- | --- |
| Portable identity, local binding, idempotent bootstrap, relocation | implemented | `scripts/project_binding.py` |
| Agency project-control ledger adapter and reconciliation gate | implemented against the existing contract | `scripts/project_binding.py` |
| Versioned navigation generations, scoped source roots, verified imports | implemented | `scripts/repo_map.py` |
| Frozen per-task context, hash-validated ranges, recorded omissions | implemented | `scripts/project_context.py` |
| Managed entry, checkpoint, publication gate, idempotent finalization | implemented, reuses the existing lock, ledger, broker and provider rules | `scripts/workflow.py` |
| Evidence-linked lessons with executor-gated promotion | implemented | `scripts/project_lessons.py` |
| off/observe/enforced policy, metrics, honest lifecycle labels | implemented | `scripts/project_binding.py` |
| Cold/warm synthetic pilot and regression gates | implemented | `scripts/context_pilot.py` |
| Optional Tree-sitter JS/TS adapter, host folder-open callbacks | deferred | not implemented |
| Two authorized real public-project English/Arabic pilots | independently passed frozen acceptance and managed finalization | [evidence](../examples/evaluation/project-context-20261003/README.md) |
| Provider billing and broad answer-quality effects | future controlled study | no claim |
| Local dense optional-navigation reproduction | measured on a local fixture, not a client project; the real dense-project rerun stays with the supervising agent | `scripts/test_task_context.py` |

## Delivery order and acceptance

1. Identity/bootstrap: stable project and checkout IDs, safe creation, schema migration and preservation. Accept repeated entry without overwrite; reject foreign bindings, ambiguous IDs, symlinks, hardlinks and cross-root output paths.
2. Index correctness: improve current map in place, guaranteeing seed visibility and adding precise import fixtures. Accept changed/add/delete/rename, equal-size edits, branch switches, parser upgrades, stale ranges, oversized files and unsupported syntax. Compare unchanged parse counts and cold/warm durations.
3. Context lifecycle: frozen context generations and bounded retrieval. Accept complete rules, relevant code/tests, explicit omission, invalidated stale snapshots and identical-filename isolation across two projects.
4. Managed integration: enter/checkpoint/finish callbacks reuse existing locks, reservations and publication gates. Accept same-root contention rejection, independent worktrees, resume, cancel, interruption, crash recovery and idempotent finalization.
5. Evidence-backed learning: candidate promotion, provenance, deduplication and revalidation. Accept unsupported success rejection, negative-evidence retention, cross-project rejection and no automatic shared-history export.
6. Pilot and native adapter: one synthetic fixture and two authorized real projects, Arabic and English. Freeze tasks/checks before comparing full versus selected context. Add a native adapter only after its lifecycle callbacks are verified.

Do not enable all-project automatic operation until these gates pass. Each new gate needs a demonstrated rejected violation and an accepted clean case. CI must run meaningful OS-boundary tests where isolation is claimed, not only mocks.

## Measurement and rollout

Measure prompt bytes, reported input/output/cached tokens, provider calls, indexing cold/warm duration, end-to-end task duration, context omissions, relevant-file retrieval and correctness against frozen acceptance. Keep missing provider usage explicitly unknown. Include indexing and any extra retrieval requests in total cost.

Roll out as off, observe, then enforced lifecycle for a selected project. Observe mode reports planned context and gaps without changing normal task execution. Enable selected context only after no critical-file omission on the pilot and all fixed acceptance checks pass; report per-task token/latency effects rather than promising a universal percentage. Support disabling automatic selection and rebuilding caches without deleting durable memory or loosening execution isolation.

The first milestone is safe project entry and refresh. Semantic embeddings, large dependency graphs, global learning and filesystem watchers are deferred until pilot evidence demonstrates a need.
