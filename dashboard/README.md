# Crewloom Dashboard

A standalone Next.js web app that monitors a Crewloom checkout live. The Python toolkit stays standard-library only; the dashboard is optional and needs Node 20+.

```bash
cd dashboard
npm install
CREWLOOM_DASHBOARD_LOCAL=1 npm run dev -- --hostname 127.0.0.1  # no password
npm test           # parser and validation tests
```

Set `CREWLOOM_ROOT` to point at another checkout (default: the parent directory).

## What it shows

| Panel | Source |
| --- | --- |
| 42 role rows: status, open tasks, completed entries, open challenges, last memory update | `.agents/skills/<id>/brain/*.md` |
| Role detail with `SKILL.md` and all five memory files | same |
| Tool runner for the 18 registered tools | `documentation/TOOLS.json` via `crewloom.py run` |
| Recent runs (CLI and dashboard) with exit code and duration | `.crewloom/runs.jsonl` |
| Repository checks button | `scripts/check_repository.py` |

Updates arrive through Server-Sent Events (`/api/events`): editing a memory file or running `python3 scripts/crewloom.py run ...` refreshes every open tab without a reload.

## Status rules

- `attention`: a failed run is recorded for the role, or a challenge entry has status open (`Status: open` / `الحالة: مفتوح`).
- `healthy`: no attention signal and at least one run or completed entry.
- `idle`: no runs and no completed entries.

## Authentication

`crewloom dashboard --project /absolute/project` opens locally without a password or sign-in screen. The launcher binds to `127.0.0.1` and explicitly enables local access. Reads require a loopback request URL; mutations require an exact local Origin. Foreign origins and remote bind configurations cannot use this mode.

Non-loopback hosting retains token authentication. A remote server without a configured credential answers `503` rather than serving project data.

| Variable | Meaning |
| --- | --- |
| `CREWLOOM_DASHBOARD_LOCAL` | `1` enables password-free access only when the actual listener and configured bind host are loopback; set automatically by the CLI. |
| `CREWLOOM_DASHBOARD_TOKEN` | The single access secret. Server-only: never declare it as `NEXT_PUBLIC_*`, or it ships in the browser bundle. Required only for explicitly selected non-loopback hosting. Local launches do not generate or write a token. |
| `CREWLOOM_DASHBOARD_HOST` / `CREWLOOM_DASHBOARD_PORT` | The bind address, which also defines the trusted origins. |
| `CREWLOOM_DASHBOARD_SCHEME` | `https` marks the session cookie `Secure`. |
| `CREWLOOM_DASHBOARD_ORIGINS` | Extra exact origins, comma separated, for a reverse proxy. |

`POST /api/auth/login` exchanges the token for a signed, HttpOnly, `SameSite=Strict` session cookie that expires after an hour. It refuses a missing or foreign `Origin`, so a page on another site cannot make a browser adopt a session, and the token is read from the request body so it never enters a URL, history, or access log. `DELETE /api/auth/login` revokes the session the server issued and clears the cookie. Mutations additionally need an exact trusted `Origin`; the allowlist is built from the variables above and never from the request, so a forged `Host` cannot widen it.

For automation, send `Authorization: Bearer $CREWLOOM_DASHBOARD_TOKEN` on any route. A browser never adds that header on its own, so a bearer caller is exempt from the origin rule by construction.

Server-side session revocation is per process: restarting the dashboard invalidates every session.

## Safety

The API runs only tools registered in `TOOLS.json`, rejects absolute or `..` path arguments, caps output at 20 KB and run time at 60 s. Binding to a non-loopback interface still requires an explicitly configured credential. Authentication is an integrity boundary, not a sandbox: any process running as the operator can read the dashboard's environment.

Project selection and isolation: [project guide](../documentation/PROJECTS.md).

## Multiple-project monitoring

Set `CREWLOOM_CATALOG` to an absolute local catalog before launching. The authenticated projects panel displays registered roots and task ownership; context cancellation resolves identity on the server and retains artifacts. The tool execution panel stays bound to `--project`. See [the catalog guide](../documentation/PROJECT_CATALOG.md).

The npm launcher owns the HTTP listener. Local authentication checks its actual bound address and port; direct `next dev` cannot enable password-free access with an environment flag alone. Invalid arguments or bind errors stop startup.
