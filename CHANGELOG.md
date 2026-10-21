# Changelog

## Unreleased

- Exclude ignored project-local teamwork memory from source archives; test wheel/sdist boundaries with synthetic private content.

- Keep async cancellation attached to its worker and owned teardown, tolerate observed automatic removal races, and enforce output budgets after UTF-8 decoding.
- Reject unsupported languages before execution; AutoGen refuses the full batch before running a supported prefix.
- Label adapter demos as previews and require explicit Docker execution with honest prerequisite failures.
- Preserve explicitly bound alternate project configuration across context/status/relocation, managed lifecycle and lesson fingerprints; protect it from workflow and adapter writes.

- Pin local-provider sockets to validated IP addresses while preserving HTTP Host and TLS verification; restricted local connections bypass proxies.
- Provide an explicit async executor for AutoGen 0.4 and verify the real pinned SDK agent without model calls.
- Capture stateful child-process and raw-fd stdout/stderr, bound output and disable persistent container logs.
- Avoid importing consumer workflow.py from installed adapters; reject malformed write-grant sequences before conversion.

- Make interop workspaces read-only by default; validate explicit output grants and refuse control trees, links and overlapping paths before creating directories.
- Include `adapters.interop` in wheel and sdist; test installed imports outside a checkout.
- Keep stateful AutoGen Python in a live isolated interpreter instead of replaying commands. Add cleanup, named CLI sessions/reset and bounded cancellation/timeout teardown; ignore legacy command histories.
- Refresh navigation parses when optional JS/TS syntax support changes; approximate extraction never claims a complete graph.
- Align dashboard setup on Node 24+; check optional readiness honestly and document the minimal core path.
- Add actual Docker/session, installed-artifact and warm-cache transition acceptance.

## 0.8.1 — 2026-10-18

- Add native standard-library loopback gateways for local open-weights model runtimes: Ollama (`/api/chat`) and vLLM (`/v1/chat/completions`), with loopback host validation, explicit port enforcement, and transparent markdown code-fence stripping.
- Add cross-framework interoperability adapters in `adapters/interop/` providing drop-in zero-trust container sandboxes for CrewAI (`CrewloomSandboxTool`), Microsoft AutoGen (`CrewloomAutoGenExecutor`), and LangChain/LangGraph (`CrewloomLangGraphNode`), with pure standard-library implementations.
- Add comprehensive architecture guides for local AI sovereignty (`documentation/LOCAL_AI_SOVEREIGNTY.md`) and cross-framework interoperability (`documentation/INTEROP.md`).
- Add 17-test regression suite for cross-framework interop adapters (`scripts/test_interop_adapters.py`) and 13-test regression suite for local provider gateways (`scripts/test_provider_gateway.py`).
- Clean up orphaned merge marker in `README.md` and expand competitive comparison table with Local AI Sovereignty and Framework Interoperability dimensions in both English and Arabic.

## 0.8.0 — 2026-10-18

- Add cross-host provider evaluation across Claude, Codex, and OpenCode runtimes, with normalized Anthropic token usage metrics separating prompt cache reads (`cached_input_tokens`) and cache creation writes (`cache_write_tokens`) (resolves #37).
- Formalize prompt cache efficiency telemetry metric calculation (`cached / (uncached + cached + cache_write)`), recording trial generation latency and Docker grading duration in evaluation summaries.
- Add headless Chrome extension background service worker verification (7 tests), bidirectional in-page HUD language switching (LTR / RTL) with persistent state, and automated WCAG 2.1 AA audits across side panel and dashboard (resolves #38).
- Enforce strict manifest completeness gate in `scripts/check_repository.py` rejecting uncommitted, missing, or mismatched SHA-256 digests in `documentation/MANIFEST.json`, and provide `--write-manifest` regeneration flag (resolves #33).
- Add production MCP integration workflow plan (`workflows/mcp-integration.json`), short-form reel video production workflow plan (`workflows/social-reel.json`), and application MCP server architecture guide (`documentation/MCP.md`) (resolves #34).

## 0.7.0 — 2026-10-18

- Add the `distributed-systems-architect` role (44 roles), an architecture procedure in English and Arabic, standard-library `system-design` verifier (20 tools) checking high-availability SLOs and SPOFs, workflow contract `workflows/system-design.json`, and a 100K RPS real-time global messaging reference blueprint.
- Add the `reverse-engineering-analyst` role, an authorization-first procedure in English and Arabic, a pinned [REA](https://github.com/morluto/rea) MCP configuration (`examples/mcp/rea.json`) and the read-only `re-findings` tool that checks a findings packet's target hash, authorization and evidence links. REA is a separate MIT-licensed project and is not bundled.
- Add `quickstart.sh` zero-install script with environment discovery, dry-run support, and automated prerequisites checking across macOS and Linux.
- Add `crewloom demo` interactive ANSI terminal walkthrough simulating role selection, 5-stage memory consultation, and isolated container execution in 20 seconds.
- Add official Model Context Protocol (MCP) configuration templates for Cursor (`examples/mcp/cursor.json`) and Windsurf (`examples/mcp/windsurf.json`) with three-tier verification guide in `examples/mcp/README.md` (resolves #40).
- Add bilingual 7-dimension competitive framework comparison matrix (Crewloom vs CrewAI vs AutoGen vs LangGraph) and vector architecture workflow diagrams to `README.md` and `README.ar.md`.
- Formalize rootless container policies, non-root `uid:gid` mirroring, and `userns-remap` bind-mount ownership guidelines in `SECURITY.md`, and reject comma characters in both source and destination mount parameters to eliminate parameter injection (resolves #39).
- Dashboard child processes no longer inherit `CREWLOOM_DASHBOARD_TOKEN` or secret-named variables, and stored tool output redacts exact secret values and common credential shapes.
- Split `docker_execute` into `docker_command` and `bind_mount`, and add Docker-free regressions that pin every isolation flag.
- Workflow containers refuse execution under host root (UID 0) to ensure container isolation cannot inherit root privileges.
- Host lifecycle test fixtures fall back to supported host releases when unpinned or upgraded host binaries are installed.

## 0.6.1 — 2026-10-17

- Browser companion2.3.2 translates known errors and in-page HUD status in Arabic/English, preserves site language and reacts to saved-language changes.
- Fix HUD hiding against its own important CSS declaration; switching language keeps a hidden HUD hidden.
- Make paired language, direction and failure-state acceptance explicit without claiming every external/CLI diagnostic is translated.

## 0.6.0 — 2026-10-16

- Fix audited browser targeting, dashboard run validation and extension packaging/download behavior.
- Add project/task-bound MCP, freshness-checked candidate import, source-linked capture/clarification and selected user-context delivery into isolated worktrees.
- Add exact application/window AX button scopes and observation-only native sessions; verify real Chrome profile, Calculator and TextEdit acceptance.
- Record a complete real model-generated Ledgerline delivery with independent Docker checks, reviewed publication, preserved failed attempts, resumption and an Arabic correction. See [the acceptance record](examples/evaluation/agency-acceptance-20261015.json).
- Keep role/domain coverage and unreported model identity/cost explicit; no universal model-quality claim.

- 2026-10-10: Add explicit-project priority scheduling, shared managed-generation admission, bounded role activity charts, and a frozen bilingual developer pilot with preserved provider failures.

## 0.4.0 — 2026-10-01

- Add project-bound Docker workflow execution with ordered commands/tasks, persistent attempts, locks, fingerprint verification, and handoff JSON.
- Add fail-closed readiness, explicit image selection, network-off command containers, runtime-state protection, resource limits and bounded output capture.
- Add a six-stage Unicode feature example, a real-project task plan, and English contracts for six software roles.
- Add a label-free, held-out objective feature grader and repeated reference/baseline measurements.
- Add host-layout setup guidance and real Docker integration checks in CI.

## Unreleased

- Allocate native operation locks inside the running event loop for Python 3.9 compatibility; retain serialized actions and refuse foreign-loop reuse.

- Run official MCP round trips and real headed Chrome extension acceptance in CI; fail explicit browser/distribution acceptance when prerequisites are unavailable.
- Use the dashboard lockfile on first launch, require Node 24+, and declare ES modules for its TypeScript test runner.
- Schedule reviewed dependency updates, bound CI job duration, and cancel superseded pull-request runs.
- Align English/Arabic setup, dashboard status rules and release documentation with the implemented authentication and integration boundaries.

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

### 2026-10-11 — Source-linked user context
Added `crewloom user-context` for project-local quoted statements, assumptions, retained corrections and task interpretations. Frozen managed prompts carry selected records and reject stale sources or explicitly unresolved questions. No mandatory external dependency or model-quality gain is claimed.

### 2026-10-11 — Private customization and publication
Added private source copies, automatic chained Git protection for new user context, private installed-role memory ignores and `crewloom privacy` setup/check/export. Selected export packets are local and owner-readable; existing tracked files and history are retained for explicit review.

- Patched dashboard PostCSS through a locked 8.5.29 override; regression refuses an untrusted external source map without reading its file.

- Reuse validated inherited privacy guards across linked worktrees instead of chaining owned wrappers recursively.
