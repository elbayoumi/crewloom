# Completed work

### 2026-10-01 — Initial public toolkit
- Artifact: 42 English public role guides, clean memory, core CLI and checks.
- Impact: Independently usable repository edition without client history or external account configuration.
- Evidence: See the exact validation results in the release notes.

### 2026-10-01 — Public edition verification
- Artifact: `documentation/VALIDATION.json`.
- Impact: 19 core tests pass; 42 guides pass structure checks; English and Arabic context commands work.
- Evidence: Clean archive checks pass, public secret-pattern scan reports zero findings, bad commit rejected and clean commit accepted.

### 2026-10-01 — Public toolkit depth and presentation
- Artifact: 108 detailed references, twelve tools, six examples, workflow recipes and bilingual entry pages.
- Impact: Roles link to detailed procedures and applicable executable checks.
- Evidence: 52 regression tests pass, including all six published CLI examples.

### 2026-10-01 — Live dashboard
- Artifact: `dashboard/` (Next.js), `scripts/crewloom.py` run log, `scripts/test_run_log.py`.
- Impact: Roles, memory counts, tool runs, and repository checks are observable live; CLI runs appear in open tabs without reload.
- Evidence: 4 dashboard unit tests, typecheck and production build pass; API run, traversal rejection, and SSE change event verified against the running server.

### 2026-10-01 — Adoption path
- Artifact: `pyproject.toml`, `crewloom install/dashboard` commands, issue/PR templates, README GIF.
- Impact: Roles installable into a project in one command; dashboard starts with one command.
- Evidence: 3 install tests pass; editable pip install in a clean venv runs `crewloom tools`; `crewloom dashboard` served `/api/overview` 200.

### 2026-10-01 — First real-project evidence
- Artifact: `documentation/EVIDENCE.md`.
- Impact: Tools run on 3 internal projects; 2 findings measured and classified false positives, not hidden.
- Evidence: commands and browser measurements recorded in the file.

### 2026-10-01 — grid-safety breakpoint awareness
- Artifact: `.agents/skills/frontend-ux-auditor/scripts/check_responsive_grid_safety.py`.
- Impact: Removes the 2 measured false positives without hiding unprefixed or oversized floors.
- Evidence: 10 tests pass (4 new); code-vault re-run passes.

### 2026-10-01 — With/without role evaluation
- Artifact: `examples/evaluation/frontend-audit/`, section in `documentation/EVIDENCE.md`.
- Impact: First controlled comparison; result is a tie (9/9 both), recorded honestly as inconclusive.
- Evidence: ground truth written before runs; both reports scored against it.

### 2026-10-01 — palette-drift tool
- Artifact: `.agents/skills/frontend-ux-auditor/scripts/check_palette_drift.py` (+11 tests), registered as tool 13.
- Impact: Closes the gap where the playbook named a project-supplied check that did not exist; flags off-token colors with file:line.
- Evidence: on the seeded fixture it reports all 3 seeded off-token locations (#ff6600 x2, #ddd) plus #fff neutrals; real project code-vault passes (18 files).

### 2026-10-01 — Second with/without evaluation
- Artifact: `examples/evaluation/frontend-audit-v2/`, section in `documentation/EVIDENCE.md`.
- Impact: 3 runs per condition on a 20-defect fixture; recall tie (100%), role runs flagged 1/18 decoys vs 7/18, +15% tokens.
- Evidence: ground truth written before runs; per-run numbers in runs.json; graded non-blind by the runner.

### 2026-10-01 — Project path isolation
- Artifact: Project-scoped CLI logs/context and dashboard execution/memory.
- Impact: Project-relative inputs and isolated histories; cross-project paths rejected.
- Evidence: 75 Python tests, five dashboard tests and TypeScript checks pass.

### 2026-10-01 — Role installation memory isolation
- Artifact: Memory-preserving role updates and clean first-install project records.
- Impact: Library history is not imported; force updates retain local experience.
- Evidence: Existing install regressions now exercise retained memory and nested destination symlink rejection; full gate passes.

### 2026-10-01 — Executable software workflows
- Artifact: Isolated workflow runner, six-stage feature/task plans, objective grader and six English role contracts.
- Impact: Executable project work, persistent attempts/handoffs and verified command boundaries.
- Evidence: 100 Python cases covered across core/live-Docker suites; five dashboard tests; fresh editable install; reference 9/9 and seeded baseline 5/9 in three grader runs.

### 2026-10-01 — Bounded model generation and English role depth
- Artifact: CLI model adapters, generated-feature example, provider trial harness and 36 additional English specialist procedures.
- Impact: Explicit project inputs/outputs, checked generation, all 42 English procedures and reproducible scoring.
- Evidence: Codex feature passes five live Docker tests; ten fresh trial submissions tie at 9/9. Claude has two authentication failures/eight skipped calls; cross-host evaluation incomplete.

### 2026-10-01 — Self-Editing Mode naming
- Artifact: `documentation/SELF_EDITING.md`, constitution and improvement-role entry point.
- Impact: Owner-selected English/Arabic name activates the existing in-place maintenance workflow.
- Evidence: Role ID preserved; documentation explicitly distinguishes host task activation from CLI/background execution.

### 2026-10-02 — Managed enforcement
- Artifact: declared-file execution broker, tool-free provider gateway, default native CLI rejection and enforcement guide.
- Evidence: repository gate covers 139 cases (133 pass, six Docker cases skipped); live broker suite passes all six cases. Live provider authentication is unverified because API keys are not configured.

### 2026-10-02 — Context efficiency
- Artifact: bounded memory selection and context-aware reuse. Evidence: 25 model-host regressions pass; synthetic full/focused prompt 63,107/9,439 bytes (85.04% smaller). No live token-cost or quality claim.

### 2026-10-02 — Repository navigation
- Artifact: crewloom map CLI, project-local cache, bounded ranking and model opt-in. Evidence: seven map regressions; local 55-file scan renders 4076 bytes and second scan reuses 55 parses. No live token/latency claim.

### 2026-10-02 — Automatic context implementation plan
- Artifact: documentation/AUTOMATIC_PROJECT_CONTEXT_PLAN.md. Evidence: reviewed current map, model prompt, workflow and agency project-control/context binding; documentation structure/link check passes. Automatic lifecycle remains proposed.

### 2026-10-02 — Automatic project context implementation
- Artifact: `crewloom.project.json` plus `.crewloom/{binding,index,context,tasks,lessons}`; `scripts/project_binding.py`, `scripts/project_context.py`, `scripts/project_lessons.py`, `scripts/context_pilot.py`; in-place `repo_map.py` upgrade; managed enter/checkpoint/publish-gate/finalize in `scripts/workflow.py`; `crewloom project` and `crewloom lesson` commands; `documentation/PROJECT_CONTEXT.md`.
- Impact: opt-in project identity and checkout binding, safe idempotent bootstrap, explicit relocation, frozen per-task context with hash-validated ranges, executor-gated lesson promotion, and an agency ledger adapter that reuses the existing project-control contract instead of a second client list. Workflow reservations, artifact broker, provider defaults and model CLI opt-in are unchanged.
- Evidence: the draft measurements below were superseded by the corrected entries that follow; they are preserved as history.

### 2026-10-02 — Draft automatic project context evidence (superseded)
- Evidence: repository gate 251 cases (245 pass, 6 Docker skips); measured 64 indexed files / 391856 source bytes; synthetic pilot 62.6% / 0.92% selected share. Independent review later reproduced real defects in this draft, so these numbers are not final acceptance.

### 2026-10-02 — Independent automatic-context acceptance review
- Artifact: `scripts/test_context_acceptance_boundaries.py` and two frozen public-repository navigation pilots.
- Evidence: Docker executed all nine navigation checks in each English/Arabic pilot; the independent suite reached 5 pass / 5 fail on the draft.
- Limit: preliminary context/navigation checks only; they are not application build quality or final lifecycle proof.

### 2026-10-02 — Corrected automatic project context
- Artifact: process-scoped project lock ownership, byte-room-bounded optional context records, semantic-only generation fingerprints, immutable generation history, executor-outcome correlated lesson promotion, scoped index inventory for freshness, and frozen-context delivery inside the managed model prompt.
- Impact: unchanged work reuses its generation instead of incrementing; dense fan-out projects stay inside the frozen byte budget without dropping declared bodies; forged or drifted evidence can no longer promote a lesson; a rejected task writes nothing; the managed prompt now carries the frozen scope, complete governing rules, verified remedies and the immutable semantic SHA the gate accepted.
- Evidence: repository gate 287 cases (281 pass, 6 Docker skips), 135 new regressions against the independently measured 152-case baseline at 71da4ca; live Docker `CREWLOOM_DOCKER_TESTS=1` scripts suite 227/227; Python 3.9 container gate passes with 9 skips. This checkout: 65 indexed files / 473895 source bytes, cold parse 159 ms, warm reuse 72 ms with 0 parses, 8123-byte rendered map. Synthetic pilot executed its acceptance command inside the isolated Docker executor over six declared inputs and verified finalization for both sizes; selected context is 76.1% of full context at 26 files and 1.17% at 606 files. A 2002-indexed-file scoped reproduction produced a 16,663-byte context under the 131,072-byte budget with the declared body and seed intact.
- Limits: live provider tokens, cost and answer quality remain unmeasured; host folder-open callbacks are unverified; JS/TS package, alias and re-export resolution is a deferred adapter; the two authorized real-project pilots and final archive/release checks remain with the supervising agent.

### 2026-10-02 — Bounded optional ranges and exactly bound consumed evidence
- Artifact: decoder-aware scan accounting and pre-read refusal for oversized required bodies in `project_context.snapshot`; `budgets.range_bytes` plus a 64-record cap for suggested ranges; per-step `context_generation`/`context_semantic_sha256` binding resolved from the immutable archive; instruction block written before the freeze with shell-quoted exit evidence; navigation delivered in the managed prompt; managed map requests bound to project scope; entry-time lesson revalidation; explicit cancellation of a reserved but unstarted managed run.
- Impact: a large ceiling no longer fills itself with unrelated symbol hints; each completed model step re-verifies against the exact generation it consumed; first native entry no longer invalidates its own frozen instructions; an unreadable file can no longer buy unbounded scan bytes; a stale verified remedy cannot survive an entry.
- Evidence: repository gate 298 cases (292 pass, 6 Docker-gated skips); live Docker `CREWLOOM_DOCKER_TESTS=1` scripts suite 238/238 with 0 skips; independent boundary suite 27/27. Local dense reproduction (121 seed-related test files, 200 importers, 16.8 KB rules, 131072-byte ceiling): 1441 candidate ranges, 23 kept / 7928 bytes inside the 8192-byte allowance, 1418 recorded omissions, 44,729-byte snapshot, snapshot+rules+sources assembly 61,618 bytes; with the allowance removed the same fixture is refused at 131,137 bytes.
- Limits: this dense case is a local reproduction, not the authorized real project; the supervising agent still owns the Arabic/English and Paperclip reruns, the Python 3.9 gate, archive/manifest verification and any provider measurement.

### 2026-10-03 — Reproducible repeat measurement of identical context
- Artifact: `normalized_payload`/`stable_payload` in `scripts/context_pilot.py`, reported as `stable_sha256`, `stable_semantic_sha256` and `volatile_bytes`; corrected `test_repeat_measurement_of_the_same_size_is_identical` plus the deterministic `test_forced_recorded_timing_changes_measured_bytes_and_nothing_else` in `scripts/test_context_pilot.py`.
- Impact: a repeat measurement of the same project size is compared by exact payload equality over everything except the checkout's own identity and the recorded scan timing, while `selected_bytes`/`serialized_bytes` remain the actual recorded sizes; the raw size difference is accounted for exactly instead of tolerated as slop.
- Evidence: controlled reproduction of the reported flake (first/second byte delta 1 with equal root lengths, `telemetry.duration_ms` 120 vs 72); three live pairs show zero remaining differences after normalization with genuinely differing `semantic_sha256`; forced timings 9 and 1234567 resealed through `project_context.seal` give exact 6665/6671 bytes, stable payload and semantic digests equal and volatile byte delta exactly 6; negative controls (changed body text, moved range start) still reject. Focused pilot suite 7/7; independent boundary suite 27/27 unchanged; scripts suite 239 cases (233 pass, 6 Docker skips), giving 299 total cases with the 60 role-core cases, exit 0.
- Limits: Python 3.9 is not installed on this host now, so 3.9 coverage is an `ast` grammar check (`feature_version=(3,9)`) of both edited files rather than a second interpreter run; the supervising agent's earlier 3.9 gate predates this change. Docs, manifests and the pilot report archive remain with the supervising agent.

### 2026-10-03 — Commit-hook Git isolation for project discovery and fixtures
- Artifact: `git_environment`, `git_dir_for` and `require_git_root` in `scripts/repo_map.py`, used by every Git child (`git`, `git_optional`, `git_state`); repository-root binding before any cache write; the same cleared environment in the `scripts/test_*.py` repository fixtures and in `context_pilot.synthetic_project`; eight regressions in `scripts/test_repo_map.py`, including a source-level check that refuses any fixture starting Git without an explicit environment; the isolation contract in `documentation/REPOSITORY_MAP.md`.
- Impact: a commit hook's `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, object-store and `GIT_CONFIG_*` overrides can no longer bind discovery to the committing repository; the selected root must own the work tree, so a nested directory, a bare repository and a plain directory are refused instead of mapped, while author/committer identities, `PATH`, locale and time zone survive. Linked worktrees map as their own root, which is this checkout's own layout.
- Evidence: reproduction against a throwaway repository that exported the hook variables reported 30 failures and 8 errors across 242 cases and left a leaked `first` commit plus a `feature` branch in it, matching `HOOK_GIT_ENV_INCIDENT.json`; after the fix the same suite reports 250 cases, 0 failures, 0 errors, 6 skips with that repository's HEAD, index, configuration, refs and history byte-identical and its pending work still untracked. The same hook environment pointed at this real worktree maps 67 files at branch `codex/automatic-project-context`, head `71da4ca`, with the worktree HEAD/index/gitdir/commondir and the main repository configuration unchanged. The independent boundary suite is 30/30, the focused map suite 30/30, and `python3 scripts/check_repository.py` exits 0 with 310 cases (304 pass, 6 Docker-gated skips), the same 250-case scripts suite under the hook environment.
- Limits: this is an input guard on the environment Crewloom itself controls, not an OS sandbox, and a checkout whose work tree is configured elsewhere in `.git/config` is refused rather than followed. Python 3.9 is not installed on this host, so 3.9 coverage is an `ast` grammar check (`feature_version=(3,9)`) of the nine edited files rather than a second interpreter run; the supervising agent's earlier 3.9 gate predates this change. The actual commit, the public PR and the archive/manifest reconciliation remain with the supervising agent, and no commit or push was made here.

### 2026-10-01 — Precise concurrent project scope
- Artifact: Explicit workflow project selection, paused-task reservation, cancellation and concurrency regressions.
- Impact: Separate roots run together; one root cannot switch workflows while a manual task is outstanding.
- Evidence: Same-root concurrent invocation rejected; different roots with identical filenames run simultaneously; copied/symlinked reservations rejected and cancellation retains files/history.

### 2026-10-03 — Integrated automatic-context publication checks
- Artifact: Automatic context implementation `8e83941`, reconciled with main `a8dcff4`, public frozen pilot fixtures and final evidence/manifest.
- Impact: Bound project identity, incremental maps and executor-verified local lessons are available through managed lifecycle; native entry remains instruction-assisted.
- Evidence: Actual commit hook 310 cases (304 pass, 6 skips); post-integration live Docker scripts 250/250; actual Python 3.9 gate 310 (301 pass, 9 skips); clean source archive gate 310 (304 pass, 6 skips); independent boundaries 30/30. English/Arabic public pilots each pass nine frozen checks, repeat one acceptance attempt, and verify one local lesson.
- Limits: Provider bills and general answer quality unmeasured; no private-client rollout, no new release tag. GitHub checks and publication recorded separately after push.

### 2026-10-03 — Reviewable automatic-context publication
- Artifact: https://github.com/elbayoumi/crewloom/pull/2 at integrated head `4df2eae`; full implementation, public evidence and manifest uploaded without private client data.
- Evidence: Final 609-file source archive has 608 verified file hashes; fresh editable installation reports 0.5.1 and installed CLI role validation/project status pass. Hosted dashboard and isolated-workflow jobs pass on the first run.
- Limits: Hosted validate requires explicit default image preload; corrected in the existing matrix without removing tests. Current hosted result is visible on the PR; no new release tag asserted.

### 2026-10-03 — Automatic project context merged
- Artifact: PR #2 merged into public main at `d9e6c64` after exact head `13b29e4` passed every hosted check.
- Evidence: https://github.com/elbayoumi/crewloom/actions/runs/37117271745 — Python 3.9/3.14 validation, dashboard tests/type checking/build, actual Docker workflows/pilot/grader and GitGuardian all pass. Actual commit hooks remained enabled; source manifest and archive checks pass.
- Limits: No private-client rollout or new release tag; provider billing/quality and native callbacks remain deferred.

## 2026-10-04 — SMS Forwarder Android app built
- Artifact: /Volumes/main/Projects/crewloom/sms-forwarder
- Impact: New native Kotlin Android app (minSdk 26, compileSdk 35) forwarding SMS to POST /api/v1/incoming-sms via WorkManager queue, acquire.
- Evidence: ./gradlew testDebugUnitTest lintDebug assembleDebug assembleRelease all green; app/build/outputs/apk/release/app-release-unsigned.apk produced; required standalone Gradle 8.14.3 from services.gradle.org (no local gradle binary); ANDROID_SDK at /opt/homebrew/share/android-commandlinetools.
- Review gate: general-subagent final review found 14 findings; blockers fixed (shared SQLiteOpenHelper singleton, insertWithOnConflict, BROADCAST_SMS permission on receiver, goAsync in receivers, DB-attempt-only retry accounting, DELIVERED state retained for status, unique key broadened to sender+timestamp+subscription+body, encrypted-prefs no plaintext fallback, FAILED missing_config re-queued on save). Security-reviewer subagent unavailable (provider error); security checklist done inline.

## 2026-10-04 — SMS Forwarder E2E on real device + backend
- Backend deployed: /opt/sms-api/server.py on 46.202.194.237 (srv791731), token in /opt/sms-api/token, logs at /data/messages.log; nginx gateway exposes https://bmc.moaf.uk/sms-backend/ → 172.21.0.1:8085/
- Base URL for app: https://bmc.moaf.uk/sms-backend
- Device A6BIUOQCBADITWU8 (RMX3710/Realme) granted RECEIVE_SMS via dialog; E2E test passed: real incoming SMS (sender 01020472050) forwarded to backend, received 200, logged with ISO timestamp + UUID message_id; in-app Test button returns HTTP 200.
- Fixed on-device crash: TextInputEditText missing layout_width/height (ANR dialog was InflateException). Added launch-intent config injection (base_url/device_id/token extras) for adb provisioning.
- Truecaller hijacked foreground during UI dump tests; force-stopped.

## 2026-10-04 — Rveta SMS: pairing QR, outbox send, multi-device
- Backend: /opt/sms-api/server.py on 46.202.194.237 runs as systemd unit sms-api (restart-safe; earlier nohup processes died with shell). Apt-installed python3-qrcode for server-side QR.
- Endpoints: POST /api/v1/incoming-sms, GET /api/messages (inbox page), POST /api/v1/outbox, GET /api/v1/outbox?device_id=, POST /api/v1/outbox/{id}/result, POST /api/v1/pair (creates device_id + device token), GET /api/v1/devices, GET /pair?d&t (PNG QR of rveta://pair?d=..&t=..).
- Inbox page: device dropdown for send target, token field, send form, "pair new device" QR generator with polling list.
- App (rveta-sms library): OutboxWorker (periodic 15 min + on-open), SmsManager send, device-scoped fetch; MainActivity handles rveta://pair deep link to set deviceId/token; RECEIVE_SMS+SEND_SMS forced requests; QR on app side removed (server generates QR).
- Note: phone disconnected via USB late in session; E2E for pairing deep link not yet re-verified on device.

## 2026-10-05 — Rveta SMS: independent code review + fixes
- Review found 5 blockers, 13 majors. Fixed the functional ones:
  - B1: `sender_name` missing from CREATE TABLE — fresh installs crashed on EVERY SMS (no migration runs on fresh DB). Now in schema + regression test.
  - B2: camera buffer sized by stride math instead of `buffer.remaining()` → BufferUnderflowException killed the analyzer thread and leaked ImageProxy (permanent scanner death). Now sizes from the buffer, always closes in finally, rejects pixelStride != 1.
  - B3/M1: QR could rewrite baseUrl/deviceId/token from any https host → added trusted-host allowlist (bmc.moaf.uk) and URL-decoded params.
  - B4: EncryptedSharedPreferences failure silently discarded the token → now surfaced in the UI as "Secure storage unavailable".
  - B5: registerDevice() hardcoded the backend → now uses config.baseUrl.
- Reliability: cleanup() no longer deletes undelivered PENDING rows; FAILED(missing_config) rows recover on save/boot; outbox work switched to APPEND_OR_REPLACE so inbound SMS can't cancel an in-flight send; outbox retries bounded; connection/errorStream leaks fixed; M9 JSON injection fixed via JSONObject.
- Tests: 20 unit tests pass (added DbSchemaTest regression guards, QrPayloadTest, ScannerDecoderTest).
- Build: debug + release unsigned APK both build; lint clean of errors.

## 2026-10-05 — Rveta SMS: instant send + per-device intelligence
- Root cause of slow sending: outbox was only drained by a 15-minute periodic WorkManager job. Added PushService (foreground, short-poll every 3s) that runs ONLY while a web dashboard session is open and stops itself otherwise (no permanent foreground service).
- Bugs found and fixed during the work:
  - `startForeground(id, notification)` without a service type throws on Android 14+ (targetSdk 35) → the service silently never started. Now passes FOREGROUND_SERVICE_TYPE_DATA_SYNC and catches failures.
  - SSE long-lived push through the Cloudflare/nginx path was unreliable → replaced with a short-poll loop against /api/v1/push/status.
  - Server sent `"dashboard": 1` (int) while the device compared against `true` → link dropped immediately. Now sends a real boolean.
  - Items queued while the link was down were never picked up → dispatch now runs once on every (re)connect as a catch-up.
- Extracted OutboxDispatcher so both the push service (instant) and the periodic worker (fallback) share one implementation.
- Measured on device RMX3710: send latency 1.2-4.8s (was up to 15 min). Offline test: message queued while phone network was off stayed PENDING and flushed within 10s of reconnect.
- Dashboard: per-device panel listing every number seen by that device with message counts, last message and timestamp; devices identified by surname only.
