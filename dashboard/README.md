# Crewloom Dashboard

A standalone Next.js web app that monitors a Crewloom checkout live. The Python toolkit stays standard-library only; the dashboard is optional and needs Node 20+.

```bash
cd dashboard
npm install
npm run dev        # http://localhost:4317
npm test           # parser and validation tests
```

Set `CREWLOOM_ROOT` to point at another checkout (default: the parent directory).

## What it shows

| Panel | Source |
| --- | --- |
| 42 role rows: status, open tasks, completed entries, open challenges, last memory update | `.agents/skills/<id>/brain/*.md` |
| Role detail with `SKILL.md` and all five memory files | same |
| Tool runner for the 12 registered tools | `documentation/TOOLS.json` via `crewloom.py run` |
| Recent runs (CLI and dashboard) with exit code and duration | `.crewloom/runs.jsonl` |
| Repository checks button | `scripts/check_repository.py` |

Updates arrive through Server-Sent Events (`/api/events`): editing a memory file or running `python3 scripts/crewloom.py run ...` refreshes every open tab without a reload.

## Status rules

- `attention`: a failed run is recorded for the role, or a challenge entry has status open (`Status: open` / `الحالة: مفتوح`).
- `healthy`: no attention signal and at least one run or completed entry.
- `idle`: no runs and no completed entries.

## Safety

The API runs only tools registered in `TOOLS.json`, rejects absolute or `..` path arguments, caps output at 20 KB and run time at 60 s. There is no authentication: bind it to localhost only and do not expose it to a network.
