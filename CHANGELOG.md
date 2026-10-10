# Changelog

- 2026-10-10: Add explicit-project priority scheduling, shared managed-generation admission, bounded role activity charts, and a frozen bilingual developer pilot with preserved provider failures.

## 0.4.0 — 2026-10-01

- Add project-bound Docker workflow execution with ordered commands/tasks, persistent attempts, locks, fingerprint verification, and handoff JSON.
- Add fail-closed readiness, explicit image selection, network-off command containers, runtime-state protection, resource limits and bounded output capture.
- Add a six-stage Unicode feature example, a real-project task plan, and English contracts for six software roles.
- Add a label-free, held-out objective feature grader and repeated reference/baseline measurements.
- Add host-layout setup guidance and real Docker integration checks in CI.

## Unreleased

- Package the Python runtime, all 42 roles, native adapters and runnable examples in a wheel and source archive; add an optional pinned JavaScript/TypeScript syntax backend.
- Add isolated concurrent model-task worktrees, dependency integration, combined Docker acceptance, credential-scoped review and recoverable artifact publication.
- Add version-scoped native lifecycle setup, explicit context delivery and tool guards, terminal-session refresh and bounded private event logs.
- Add a complete English/Arabic reporting application and a frozen full-source/selected-map study with held-out grading and nullable provider measurements.
- Require dashboard authentication, CSRF checks and revocable sessions; add read-only registered-project readiness.
- Run repository regression files through sequential bounded invocations, retaining recursive discovery and failure/timeout propagation.
- Add a mandatory repository scope gate (`REPOSITORY_SCOPE.json`): an unregistered top-level directory or file, a foreign project ID, a missing or malformed contract and case or path collisions are refused, even when ignored. An independent application belongs in its own repository.
- Fix OpenCode context delivery: the adapter replaced `output.system` instead of extending the host-owned array, so the hook ran but the model received nothing. Verified against a real OpenCode 1.18.32 host.
- Record the first frozen context study honestly: Codex full-source passed all held-out checks, the selected map passed none, OpenCode produced no scored trial; no saving is claimed.
- Address review findings: close open dashboard event streams when their session is revoked, ignore foreign hooks under events the adapter never installed, persist worker-crash outcomes with declared outputs, and resolve root conditional package exports.
- Add the study v2 dependency-closure map (`repo_map.closure_context`, `closure-map` prompt arm, `study_plan_v2`) and an offline sufficiency gate that rejects the v1 selected-map prompts before any provider call. The v2 study was run once afterwards; its outcome is recorded below.
- Add the study v2 runner: `collect_study(protocol_version='v2')` and `evaluate_hosts.py --study-v2` freeze the references and the map generator, refuse to start (before any call or write) when the sufficiency gate fails, and report full-source against closure-map. The frozen references are public grader data in `examples/context-study/grader/references/`.
- Re-verify every frozen study input after the last trial (fixture, helpers, prompt files, grader, transport, map generator, references): `verification.json` is always written and a mismatch refuses the run without publishing `report.json`. A v2 record now describes the closure-map comparison instead of the v1 one.
- Record the first completed study v2 run: closure-map matched full-source on all held-out checks (99/99 each) with about 18% fewer input tokens on three synthetic tasks, one host; no cost, speed or wider quality claim.
- State the artifact schema to OpenCode in its agent system prompt (`model_host.opencode_schema_instruction`, `opencode_agent_config(model, outputs)`): `opencode run` has no schema option and 14 finished generations of the first study were refused for inventing a response shape. The study prompt is still delivered byte for byte and exactly once, other hosts are unchanged and every invented shape is still refused.
- Make the native lifecycle tests portable to hosted CI (no host binaries, case-sensitive filesystems) and verify the gate on Python 3.9 and 3.14.

- `grid-safety` no longer flags fixed floors inside breakpoint-prefixed Tailwind grids that fit the breakpoint.
- Add a with/without-role evaluation on a seeded fixture (result: tie, inconclusive) to `documentation/EVIDENCE.md`.
- Add `palette-drift` (13th tool): flags literal colors outside the approved design tokens.
- Add a second with/without-role evaluation (3 runs per condition) to `documentation/EVIDENCE.md`.
- Add `pyproject.toml` (`pip install -e .` provides the `crewloom` command), `crewloom install --host claude|agents`, and `crewloom dashboard`.
- Add issue and pull request templates and an inline dashboard demo.
- Add the optional live web dashboard (`dashboard/`): role status, memory counts, tool runner, run feed, and repository checks with server-sent updates.
- Record every `crewloom.py run` to `.crewloom/runs.jsonl` (opt out with `CREWLOOM_NO_LOG=1`).

## 0.2.0 — 2026-10-01

- Restore 108 detailed, filtered source references across all 42 roles.
- Add nine domain tools, bringing the catalog to twelve local Python tools.
- Add CLI tool discovery and execution, six runnable examples, and workflow recipes.
- Expand regression coverage for frontend checks and delivery evidence.
- Rework English and Arabic entry points with a banner and direct paths to useful work.

## 0.1.0 — 2026-10-01

- Initial public role guides, clean memory, context packs, and repository gate.

## Project catalog and monitoring

Adds `project setup`, `projects add/list/remove/cancel-task`, catalog overlap guards and authenticated multi-project monitoring. Existing coordinator, packaging and executor limits are reused. Provider comparisons remain scoped to their recorded evidence.

## Password-free local dashboard

`crewloom dashboard` now opens on loopback without sign-in or generated credentials. Local request URLs and mutation Origins are checked; non-loopback hosting retains explicit token authentication.
