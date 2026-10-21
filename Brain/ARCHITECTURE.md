# Repository architecture

### 2026-10-21 — Cancellation and configuration identity
Async adapter cancellation owns its worker until cleanup finishes; waiting for a busy session is cancellation-aware. Returned UTF-8 and diagnostics share the output budget. Explicit alternate project configurations are resolved from the binding by default consumers, lifecycle selection and lesson fingerprints; both managed artifacts and adapter grants protect the bound authority. Preview examples require a separate execution flag and never imply SDK acceptance. Project-local teamwork memory is excluded from source archives independently of Git ignore rules.

### 2026-10-21 — Transport and adapter consumer boundaries
Restricted local provider requests pin validated numeric IPs at the socket while retaining the URL host for HTTP and verified TLS, with no proxy forwarding. Interop uses self-contained standard-library helpers, validates grant sequence types before conversion, and exposes an explicit awaited AutoGen adapter. Persistent Python sessions capture OS descriptors with a bounded collector and disable Docker logging; background output is not a later-results channel.

### 2026-10-20 — Interop boundary and live Python sessions
Framework adapters mount the selected project read-only by default, validate explicit output grants and share bounded Docker process collection. They expose the whole readable project, not workflow snapshots or transactional output publication. AutoGen Python state lives in an owned isolated interpreter with bounded socket requests and explicit close/reset; named CLI sessions survive process exit until reset. No command history is replayed. Adapter code is packaged under its existing `adapters.interop` imports. Optional parser changes invalidate warm navigation caches; approximate graphs remain incomplete. Dashboard setup requires Node 24+ consistently.

### 2026-10-15 — Release verification boundaries
The default core remains standard-library compatible on Python 3.9+. Explicit integration CI installs the pinned MCP SDK and Playwright, runs actual SDK/container protocols and loads the unpacked extension in headed Chromium. Missing explicit prerequisites fail; optional native desktop approval remains outside CI. Dashboard development requires Node 24+, ES modules and lockfile installation.

### 2026-10-14 — Browser and dashboard correctness
- Index replies bind tab/navigation request; targets bind frame, document token, generation and action fingerprint. Clicks recheck ancestor interactivity and hit-test visibility. Open Shadow DOM/readable frames share a bounded viewport-prioritized inventory; the directory is paginated.
- Dashboard role status uses run evidence rather than template headings. Memory counters accept dated compact records; malformed run values are isolated. Tool arguments are data, with bounded quote/JSON parsing and no shell evaluation; external-root tools remain CLI-only.
- A deterministic source-only browser packager and stale/unreviewed-file regressions prevent ZIP drift. Runtime source and monitored project are displayed separately. These changes do not add autonomous model/browser dispatch or a native desktop controller.

[Public architecture](../documentation/ARCHITECTURE.md) describes the toolkit boundaries. [AGENTS.md](../AGENTS.md) is the single authority for agent behavior. Public role procedures and core tools improve in their existing paths; do not maintain duplicate versioned implementations.

Model generation passes explicit project text to a trusted CLI in a temporary directory; the artifact layer validates writes and the Docker executor verifies code. Host CLI flags are not an OS sandbox. Trial treatment labels remain outside the deterministic scorer.

Managed runs use tool-free provider RPC and declared-file container snapshots. Native CLI use requires an explicit operator exception. The trusted runtime cannot be a managed output destination.

### 2026-10-04 — Concurrent worktree coordination with reviewed integration
- The task coordinator is one layer over the existing managed executor, not a second runtime: each task runs `workflow.run` inside its own Git worktree, so isolation, the declared-artifact broker, the attempt ledger and the image policy stay shared with an ordinary workflow. Batch ownership is a kernel-held advisory lock, and the root is held with the same reservation a managed workflow writes, so ordinary workflow and native-context writers refuse it in both directions. The project lock covers short controller state and Git mutations only; each worktree takes its own root lock while it runs.
- A task commit carries only its verified declared outputs, so combining task commits once carries artifact diffs. Verified ancestor commits are merged into a dependent worktree before it runs, so it reads its ancestors' files rather than the untouched base. A failed or blocked task blocks its dependents with the blocking IDs recorded; no partial acceptance exists.
- The root moves only through one recorded `--ff-only` fast-forward of a reviewed candidate, after the manifest, project and checkout binding, every task commit, output hashes, criteria, integration head, recomputed diff digest, reviewer credential and revocation, current root HEAD, clean tracked tree and untracked collisions have all been revalidated. The nonce of a consumed decision cannot be replayed. Conflicts keep every branch, worktree and index; nothing is reset, forced or cleaned, and no push or GitHub merge exists.
- Not claimed: this is not a scheduler, a provider client, or a boundary for arbitrary host tools; a command step is the only step kind it runs; reclaiming batch ownership does not stop a container that outlived its controller; a declared-label review names a reviewer without authenticating one, and a credential proves key possession only; Git's own atomicity limits still apply to that single fast-forward.

### 2026-10-03 — Recoverable grouped artifact publication
- One declared output group is published as one recoverable transaction: the whole group, its destinations and its input fingerprints are validated before the first write; the group and a backup of every destination it replaces are staged under protected `.crewloom` with a scoped journal; the project lock is held for the whole publication and its recovery. A failure is rolled back to the recorded content and mode, or removes only files that attempt created, and only after every journal record is proven restorable, so a rollback never leaves an unrecorded third state.
- This is recoverable grouped publication, deliberately not an instant multi-file atomic filesystem change: a reader that ignores the project lock can observe a group half applied. Managed writers serialise on the same lock and an interrupted group converges instead of accumulating.
- Publication recovery runs before any managed work observes the project: project entry reconciles it after the identity/ownership preflight and before any criteria, instruction, context or reservation write, and a workflow run reconciles it before it reads workflow state. A destination that no longer matches its journal is refused and left untouched with its journal kept for manual review.
- The root lock is reclaimed only for an owner that is provably gone, under an exclusive reclamation claim and verified against the exact inode the record was read from. Reclamation never follows a symlinked lock, claim or owner path and never deletes unrecognised claim contents; an unrecognised claim blocks the root for manual reconciliation. Reclaiming a lock does not stop a command or container that outlived its process.

### 2026-10-02 — Context efficiency
- Model prompts select whole historical records with Unicode lexical relevance and bounded budgets; constitution, architecture, roadmap and inputs remain full. Reuse validates prompt hashes; history is not rewritten.

### 2026-10-02 — Repository navigation
- Project maps use Python AST and approximate JS/TS extraction with per-root SHA-keyed parsing cache. Map metadata is opt-in for managed prompts and never substitutes for actual declared source inputs.

### 2026-10-02 — Automatic project context
- Project identity is split into a portable `crewloom.project.json` project ID and a local `.crewloom/binding.json` checkout ID; navigation and context caches are rebuildable, lessons and task records are durable. Every generation is scoped to project ID, checkout ID, canonical root and task ID, and a stable semantic fingerprint excludes telemetry so unchanged entry reuses its generation. Lifecycle shares the workflow root lock and its reservation discipline in both directions; managed runner entry, checkpoint, publication gate and finalization reuse the existing broker, ledger and provider restrictions. Lesson promotion requires recorded executor evidence, never prose.

### 2026-10-09 — Machine-local project catalog
The existing project binding module owns catalog registration, overlap guards and setup. Portable config and checkout binding remain the identity sources; the catalog stores local references only. Dashboard monitoring reads explicit entries through the CLI; cancellation resolves project roots server-side and uses the existing project lock. Existing role/tool panels retain their selected execution root.

### 2026-10-09 — Password-free local dashboard
The launcher explicitly enables loopback-only local access. Local URLs and exact local mutation Origins are checked before project access; non-loopback deployments retain configured-token authentication. No generated token or cookie is required locally.

- 2026-10-09: Password-free local access now reads the real HTTP listener address/port from the npm custom server; an environment flag alone fails closed.

### 2026-10-10 — Scheduling, shared admission and measured activity
- An explicit machine-local queue schedules registered canonical roots by priority, with one active batch per root and unchanged coordinator worktree/review boundaries. The managed model step reserves shared request/dollar admission atomically before creating a provider attempt; unknown cost retains allowance. Dollar admission is not a vendor account billing cap.

### 2026-10-11 — Source-linked user understanding
The existing frozen context owns delivery of optional project-local user statements, labelled assumptions and explicit task interpretations. `user_context.py` records exact source quotes and hashes under the selected project/checkout, uses the existing lock and reservation protocol, retains correction history and fails on unresolved questions or stale sources. Provenance is not speaker authentication, factual truth, user confirmation or execution authority. No external memory runtime is required.

### 2026-10-11 — Private customization and publication boundary
Personal data uses `.crewloom/private/` and ignored installed-role memory. User-context sources get private copies and canonical publication-deny registrations; recording enables a chained project hook under the existing lock. The guard scans index objects, including checked temporary indexes, while preserving prior hooks. Publication packets contain explicit files only and never upload. Known-pattern checks do not prove confidentiality.

- 2026-10-11: Dashboard pins PostCSS 8.5.29 through npm overrides so Next resolves a patched CSS processor; regression observes external map reads and must refuse an absolute untrusted sourceMappingURL.

- Linked worktree privacy setup validates/reuses an inherited owned guard instead of replacing shared core.hooksPath; source registrations remain local and the committing worktree is scanned.

### 2026-10-11 — Understanding pilot preparation
The existing bilingual evaluator owns pinned synthetic understanding contracts, strict per-field grading and prompts that exclude held-out answers. Raw-history and selected-context arms reuse the production user/task correction selector. Full runtime selection still validates binding and source freshness. Offline contract verification performs no provider calls and grants no action permission.

- User-context revisions and selection now separate quoted statements from assumptions. Task/global precedence applies within each kind; both kinds retain binding/freshness checks and enter managed/native payloads with explicit uncertainty.

- Understanding offline verification now audits each generated prompt against independently declared required record IDs and exact source/scope data; grading expectations remain excluded from prompts. Live collection must reuse this preflight.

- 2026-10-11 | The understanding collector binds canonical project identity and records a shuffled fixed paired plan before generation. Output is restricted to new private evaluation directories; each trial is preserved, failures stop repeated transport attempts, and model identity is explicitly requested.

- 2026-10-11 | Concurrent example generation now declares reused helper implementations as prompt inputs for billing, planning and report. Acceptance tools remain excluded from generation.

- 2026-10-11 | Planning acceptance enforces declared exception types without fixture-specific wording. Cycle representation is explicitly closed in the public generation contract.

- 2026-10-11 | Report titles are explicit bilingual contract resources. Invalid payload acceptance checks required ValueError and named unknown key, rather than fixture-specific messages.

- 2026-10-11 | Model repair_from references source failure state in the same bound checkout, exact candidate copies and unchanged producer/verifier scope; original sources/static verifier dependencies remain frozen. Failure diagnostics are bounded input data. Maximum two repair ancestors and existing request/admission budgets apply. Explicit plan preparation/dispatch remains pending.

- 2026-10-11 | Repair preparation and execution reuse workflow.py through prepare-repair/repair. Owner-only candidate copies and plans live under /.crewloom-repairs/; privacy.py ignores and rejects this namespace in staged indexes. Unchanged verifier argv/dependencies/image digest, recorded criteria inputs, source hashes and two-repair ancestry bound the cycle; ordinary run does not automatically spend on repair.

- 2026-10-11 | Final repair budget guard counts all model repair requests by original workflow across new IDs and branches. Regression rejects a branch after two requests, an oversized feedback prompt before provider calls and a substituted verifier image. Final Docker workflow31 passes.

- 2026-10-11 | OpenCode model IDs remain explicit provider/model values. Optional opencode_provider references a bounded project-private five-field loopback provider contract; fixed OpenAI-compatible SDK and deny-all host profile remain. Hash enters prompt/generation evidence; changed profiles reject repair, publication and reuse. Byte budgets are not tokenizer or context-capacity estimates.

- 2026-10-11 | Private local-provider readers now reject foreign ownership and any group/other permission bits on POSIX, matching the documented chmod600 contract. Non-POSIX ACL ownership remains unverified.

- 2026-10-12 | Portable external-agent generation reuses workflow.py agent-packet for the reserved awaiting task. Packet carries bound project/checkout, plan/input/prompt hashes, schema and existing handoff; same model_host prompt construction and fresh exact-scope managed context apply. Export never dispatches, imports replies or accepts tasks.

- 2026-10-12 | Manual browser companion is now an explicit extensions/ scope entry; native Codex plugin uses one CLI-backed skill under adapters/codex/plugin and a local marketplace. Browser activation is extension-wide persistent storage, default off, enforced at content/capture boundaries. Element clicks use owned references and generation checks. New API routes reuse guard/privateHeaders; native accessibility remains unknown, explicit screen probe is shell-free and bounded.

- 2026-10-13 | Capture requests persist in session storage per explicit window with a30-second expiry and original tab identity; panel readiness consumes once. Form index metadata excludes entered input/textarea/select values.

### 2026-10-14 — Bound MCP and external candidate imports
- Optional official MCP SDK2.3.0 stdio bridge fixes project/root, checkout, policy, task and plan at launch. Read-only tools are the default inventory; import and container verification require explicit launch flags. No tool selects arbitrary roots, commands or providers.
- External reply import reuses agent_packet, schema validation, project locks and grouped publication. Packet input/prompt/context/binding/output revisions must remain current, including output fingerprints captured before and after staging. Raw replies remain private; imports do not accept task reviews or create execution evidence.
- A pinned isolated Playwright MCP config provides a separately authorized host browser integration. It does not turn the Chrome manual panel into an autonomous channel or establish native desktop trust.

### 2026-10-14 — Scoped capture and native acceptance
- Optional per-task native prompt capture reuses user_context, validated native callbacks, private source storage and frozen context. Literal placeholders/language conflicts retain source-linked questions; native guards refuse actions until a later captured answer resolves them. Interpretation is not permission or speaker authentication. Task MCP adds read questions and opt-in answer writes.
- Separate native AX MCP connects only to an existing explicit private driver socket. Prepared fixture-only bounded manifests require human approval; exact app/window discovery, one-use button handles, serialization and private action audit precede re-observation. Mock acceptance and compilation do not establish live desktop control.
- The existing understanding collector supports explicit preselected cases and reports subset coverage; failures and all paired trials remain preserved.

- 2026-10-15 | Fixed observed PID replaces global app discovery under the fixture-only manifest. AX rows are projected by exact window ancestry; static counter text comes from its bounded tree block. Ambiguous identity/rows and potentially truncated blocks fail closed; menu history and raw tokens never leave the adapter.

- 2026-10-15 | Coordinator task context is now projected into same-project Git worktrees with private source copies and parent/child selection receipts. Recheck before commit and on resume refuses changed corrections. Native preparation accepts an explicit exact app/window/button set or observation-only scope; no implicit new application authority.

- 2026-10-17 | Bilingual acceptance covers the selected context/workflow language and localized UI success/empty/error states. Browser HUD retains only structured status keys/counts, reads saved language through extension storage, and updates its own lang/dir without changing the page; unknown external diagnostics remain verbatim.
