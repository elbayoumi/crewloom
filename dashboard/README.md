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
| Tool runner for the 26 registered tools | `documentation/TOOLS.json` via `crewloom.py run` |
| Recent runs (CLI and dashboard) with exit code and duration | `.crewloom/runs.jsonl` |
| Repository checks button | `scripts/check_repository.py` |

Updates arrive through Server-Sent Events (`/api/events`): editing a memory file or running `python3 scripts/crewloom.py run ...` refreshes every open tab without a reload.

## Status rules

- `attention`: a failed run is recorded for the role, or a challenge entry has status open (`Status: open` / `الحالة: مفتوح`).
- `documented`, `configured` and `exercised`: progressively observed role setup/use, without task acceptance.
- `verified`: current scoped executor acceptance resolves successfully.

## Authentication

Every API read, every API write, and the event stream require authentication. There is no anonymous mode: a server started without a configured credential answers `503` rather than serving project data.

| Variable | Meaning |
| --- | --- |
| `CREWLOOM_DASHBOARD_TOKEN` | The single access secret. Server-only: never declare it as `NEXT_PUBLIC_*`, or it ships in the browser bundle. `crewloom dashboard` generates one and writes it to `<project>/.crewloom/dashboard-token` with mode `0600`, printing only the path. |
| `CREWLOOM_DASHBOARD_HOST` / `CREWLOOM_DASHBOARD_PORT` | The bind address, which also defines the trusted origins. |
| `CREWLOOM_DASHBOARD_SCHEME` | `https` marks the session cookie `Secure`. |
| `CREWLOOM_DASHBOARD_ORIGINS` | Extra exact origins, comma separated, for a reverse proxy. |

`POST /api/auth/login` exchanges the token for a signed, HttpOnly, `SameSite=Strict` session cookie that expires after an hour. It refuses a missing or foreign `Origin`, so a page on another site cannot make a browser adopt a session, and the token is read from the request body so it never enters a URL, history, or access log. `DELETE /api/auth/login` revokes the session the server issued and clears the cookie. Mutations additionally need an exact trusted `Origin`; the allowlist is built from the variables above and never from the request, so a forged `Host` cannot widen it.

For automation, send `Authorization: Bearer $CREWLOOM_DASHBOARD_TOKEN` on any route. A browser never adds that header on its own, so a bearer caller is exempt from the origin rule by construction.

Server-side session revocation is per process: restarting the dashboard invalidates every session.

## Safety

The API runs only tools registered in `TOOLS.json`, rejects absolute or `..` path arguments, caps output at 20 KB and run time at 60 s. Binding to a non-loopback interface still requires an explicitly configured credential. Authentication is an integrity boundary, not a sandbox: any process running as the operator can read the dashboard's environment.

Project selection and isolation: [project guide](../documentation/PROJECTS.md).

## Role status and what it means

A role's status states what is known, in this order of evidence:

| Status | Meaning |
| --- | --- |
| `documented` | A role guide exists. Nothing is installed in the selected project and no tool has run. |
| `configured` | The role is installed in the selected project (`.agents/skills` or `.claude/skills`). |
| `exercised` | A registered tool for the role has run at least once. A tool exit code is not application acceptance. |
| `verified` | Schema 2 `.crewloom/acceptance/<role>.json` binds the role, project/checkout and executor references; current inputs/outputs and the referenced command role still match. A schema 1 `passed` flag is unverified. |
| `attention` | The latest run of a tool failed, or a challenge is open or has an unknown status. This takes precedence. |

A challenge entry counts as `open` or `resolved` only when it has a recognised status line (`Status:`/`State:`/`الحالة:` with an open or resolved value). An entry without one is shown as unknown (`n?`) instead of being treated as closed.

Tool arguments are parsed with shell-style quoting, so `--input "docs/My folder/ملف.md"` is one argument. The exact argument array is shown before launch; unterminated quotes are refused, and traversal, absolute paths and NUL bytes are still rejected by the server. Role descriptions support plain, quoted, folded (`>`) and literal (`|`) YAML scalars; other constructs are reported as warnings rather than shown as garbage.

## Select independent existing projects

Single-project `CREWLOOM_PROJECT` remains supported. For multiple projects, set server-only `CREWLOOM_PROJECTS` to an ordered JSON array of `{ "id": "sample-project", "root": "/canonical/external/project" }`. Each root needs an existing matching `crewloom.project.json`; an existing local binding must match too. Entries cannot be duplicate, overlapping, aliased or nested in the toolkit. This allowlist references existing roots; it is not a second project registry and performs no customer enrollment or copying.

Authenticated requests select an approved ID with `?project=sample-project`. Arbitrary paths and ambiguous selection are refused. Reads, tool cwd, logs and SSE watchers carry the selected root per request; switching projects discards late responses and closes the old stream. Selection is disabled during a running tool. English and Arabic project controls use the same scope checks.

Task summaries show historical completion separately from current verified acceptance. At most 200 bounded task records are read, and up to 64 receive current controller acceptance checks per request; additional tasks remain unverified. Foreign/malformed records are diagnosed without displaying private payloads. Roles show documented/configured/exercised/verified/attention evidence tiers. Legacy acceptance self-attestations are unverified; schema 2 scoped executor references must still resolve to unchanged input/output bytes.
