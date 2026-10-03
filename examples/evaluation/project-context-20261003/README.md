# Frozen project-context acceptance: English and Arabic

These independent acceptance runs use two public source revisions: Crewloom `71da4ca7b12ca64b0addef91868345334e61ebce` and Paperclip `427e0484059c33fdfd98263e2d6f4c3a27a7e156`. [Results](results.json) record actual executions on 2026-10-03 after the Git-environment correction, with the earlier 2026-10-02 measurements preserved as history. They evaluate navigation and project-context lifecycle, not application build quality or model answer superiority. No provider was called.

Both projects passed the same nine frozen checks: project identity, language, seed navigation, entire declared source, source hash, required symbols, direct relative imports, the unchanged 131072-byte ceiling, and governing role rules. The managed runner completed and repeated with one command attempt; the lesson was promoted from the correlated executor record. Rules, required source and criteria were retained. Optional omissions are recorded in the results.

| Project | Language | Indexed files | Selected bytes | Full indexed source + rules bytes | Cold / warm ms | Warm parses |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Crewloom | English | 57 | 43231 | 187358 | 158 / 102 | 0 |
| Paperclip UI | Arabic | 2001 | 54106 | 22705265 | 1531 / 362 | 0 |

The byte reductions are 76.93% and 99.76% for these navigation contracts. They are not token, cache, billing or total-development savings. Paperclip was explicitly scoped to `ui`; scanning its entire checkout exceeded the documented cap. Every refresh still reads/hashes candidates. JS/TS imports remain approximate beyond the verified direct relative edge.

## Reproduce the acceptance

Use fresh, disposable checkouts at the recorded revisions, the Crewloom implementation containing this evidence, Python >=3.9 and a reachable Docker daemon. The image was `python:3.14-slim`; the exact image ID is recorded in the results. These instructions write only the chosen test checkout. Do not run them on a client's active task root.

1. Choose the corresponding `crewloom-en` or `paperclip-ar` fixture. Copy its `project-config.json` to the test checkout as `crewloom.project.json`. Ensure exactly one project-local `context-guardian` role is installed: on a checkout without it, run `crewloom install --host agents --target ROOT --skill context-guardian`; keep any existing role and memory. Create `crewloom-hook-pilot/` and copy the fixture's `ACCEPTANCE.md`, `acceptance.json`, `workflow.json` and this directory's `check.py` there.
2. Read `acceptance.json` for the explicit project ID, language and seed. Enter the project with `crewloom project enter --project ROOT --project-id ID --task-id git-isolated-navigation-acceptance --role context-guardian --language LANG --seed SEED --source SEED --criteria crewloom-hook-pilot/ACCEPTANCE.md`.
3. Copy `.crewloom/context/git-isolated-navigation-acceptance.json` to `crewloom-hook-pilot/context.json` without changing its contents. The checker reads the whole frozen snapshot and the declared seed.
4. Run `crewloom workflow run --project ROOT --plan crewloom-hook-pilot/workflow.json --image python:3.14-slim`; repeat the same command. Inspect `crewloom-hook-pilot/result.json`, `.crewloom/workflows/git-isolated-navigation-acceptance/state.json` and project status. The repeat must reuse the completed command, and both finalizations must be verified.
5. A candidate lesson can be recorded against this task and verified with `[{"workflow":"git-isolated-navigation-acceptance","step":"acceptance","scope":"Nine frozen navigation/context checks"}]`; see the [lesson commands](../../../documentation/PROJECT_CONTEXT.md#lessons). Promotion requires the real local executor ledger; copying this results file cannot promote a lesson.

Cold/warm timings require separate index refreshes and depend on the machine. Roots and checkout IDs differ between runs, so exact serialized counts can differ while the same frozen acceptance stays fixed. Prior failed attempts were retained locally; the successful run used a fresh task contract after correcting optional-range bloat, without raising the budget or changing the checker.

The rerun uses fresh task and artifact paths, preserving the prior executed checks, lessons and negative attempts. Additional fixture source and retained eligible lessons explain why a later payload need not be smaller than the earlier one; all exact counts above are measured, not normalized.
