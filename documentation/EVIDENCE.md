# Evidence log: tools run on real projects

Dated records of Crewloom tools run against real codebases, with commands, raw results, and what was and was not verified. Project names are internal RUMUZE products; no client code is included.

## 2026-10-01 — Frontend checks on three Next.js projects

Role: [frontend-ux-auditor](../.agents/skills/frontend-ux-auditor/SKILL.md). Commands (`{dir}` = project folder):

```bash
python3 scripts/crewloom.py run ui-hints -- --project-dir {dir} --json
python3 scripts/crewloom.py run grid-safety -- --project-dir {dir} --json
```

| Project | Files scanned | `ui-hints` | `grid-safety` |
| --- | --- | --- | --- |
| code-vault | 19 | 0 hints, exit 2 (rendered review required) | **2 flagged**, exit 1 |
| rumuze-mvp-boilerplate | 19 | 0 hints, exit 2 | pass |
| restaurant-cafe-base | 46 | 0 hints, exit 2 | pass |

`ui-hints` exits 2 by design: a static scan cannot accept a layout, so it asks for rendered review instead of claiming a pass.

### The two flagged grids

Both are in code-vault and use a fixed pixel floor in a column track behind the `lg:` prefix:

- `app/services/[slug]/service-detail-client.tsx:238` — `lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.85fr)]`
- `app/services/runs/[id]/run-client.tsx:180` — `lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.7fr)]`

Verification: a headless Chromium replica of the same `grid-template-columns` (16 px side padding, 20 px gap) at the smallest width where `lg:` applies and at 1280 px.

| Grid | Viewport | Columns | Horizontal overflow |
| --- | --- | --- | --- |
| 238 | 1024 | 596 px + 376 px | none |
| 238 | 1280 | 754 px + 474 px | none |
| 180 | 1024 | 663 px + 309 px | none |
| 180 | 1280 | 837 px + 391 px | none |

**Conclusion: both findings are false positives.** The floor only applies from 1024 px, where a 320 px track plus gap fits. Limits of this check: it reproduces the grid alone, not the full page with its real content, and was not run in the live app (which needs a database).

### What this shows

- The tools run on real projects and finish in well under a second each.
- `grid-safety` flags any fixed floor, even behind a breakpoint prefix that already guarantees the width. Recorded as a follow-up in `Brain/ROADMAP_TODO.md`.
- No claim is made that the role improves an agent's output; that needs a controlled with/without comparison on the same task, which is still open.

### Follow-up: tool corrected

`grid-safety` now skips a fixed floor inside a Tailwind `sm:`–`2xl:` arbitrary grid class when the floors sum to at most half that breakpoint's width. Unprefixed floors, floors too large for their breakpoint, and other tokens on the same line are still flagged (4 new regression tests). Re-running the original command on code-vault now passes; the two findings above no longer appear. The half-breakpoint margin is a conservative rule of thumb, not a measurement of gaps or padding in a given page.

