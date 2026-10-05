# Native host lifecycle

Crewloom can install, observe, guard and verify a coding agent host's own lifecycle callbacks
inside one bound project. This guide is the one-time setup per host. It is deliberately not a
universal agent framework: it covers the callbacks a host actually delivers on a version that
was actually probed, and it reports everything else as unobserved.

## What this is, and what it is not

A native host adapter is one thin layer over the existing managed runtime. It adds no second
context engine, no second verification path and no self-reported checks:

- frozen context still comes from `project_context` through `project_binding.enter`;
- freshness still comes from the recorded generation digests;
- acceptance still runs through the managed workflow Docker broker, and completion still
  requires correlated executor evidence resolved by `project_binding.finish`.

Three states are reported separately and never collapse into one another:

| State | Meaning |
| --- | --- |
| **installed** | The rendered payloads exist and still hash to what this installer wrote. |
| **observed** | A real host callback reached this engine carrying the exact installed payload digest. |
| **verified** | The project's own Docker executor ledger resolved configured acceptance evidence. |

An installed adapter is not an observed one, and neither is a verified one. A `Stop` hook, an
idle event, a session-end event or a confident reply never becomes verification on its own.

## Before you start

You need an already bound project. This adapter never bootstraps one and never infers identity
from a folder name, a remote URL, Git or a prior conversation:

```bash
crewloom install --host agents --target /abs/path --skill <role>
crewloom project enter --project /abs/path --project-id <project-id> --task-id bind-host --role <role>
crewloom project cancel --project /abs/path --project-id <project-id> --task-id bind-host --reason "Setup complete; native session owns its own task"
```

The role must already be installed in the project (`crewloom install --host agents --skill <role>`).
The adapter refuses to install against a role that is missing.

## Install

`install` writes one host's owned payloads, merges them into that host's project control
configuration and records bounded owner-only state under `.crewloom/hosts/<host>/`. It needs
explicit identity, an explicit declared output set, and it never takes a root that another
writer already reserved.

```bash
crewloom host install \
  --project /abs/path --project-id <project-id> \
  --host codex --role <role> \
  --criteria criteria.md --seed src/login.py --source src/login.py \
  --output out/report.txt \
  --managed-command "python3 -m unittest discover -s tests" \
  --acceptance acceptance.json --acceptance-step acceptance
```

- `--output` is the exact set of files the host agent may write. There is no default: an
  unguarded task has no boundary, so an empty set is refused.
- `--managed-command` is an exact argv allowlist entry. It is matched by exact canonical working
  directory and exact argv, never by a substring inside a longer command.
- `--acceptance` names an existing managed workflow plan whose step is the project's real
  acceptance check. Without it a `Stop` event can never verify anything.

Foreign hooks, settings, extensions and plugins are preserved. Existing entries that this
installer does not own are never rewritten, and `uninstall` removes only items that still match
the recorded bytes; anything altered reports a conflict and is preserved for review.

## Status

```bash
crewloom host status --project /abs/path --project-id <project-id> --host codex
```

The `lifecycle` label is one of `not-installed`, `altered`, `config-ready`, `needs-trust`,
`observed` or `verified-executor`, and the report always carries the separate booleans, the
actual host version, the control-configuration digest, the installed content digest and the
names of observed callbacks.

## Hosts

### Codex CLI 0.155.1

Requires `features.code_mode_host=true`. Native Codex tools were observed to be unavailable with
`code_mode_host=false` even while `shell_tool=true` and `code_mode=false`; tools being
unavailable was never treated as a denial proof.

- Installed control config: `.codex/hooks.json`.
- **Delivery is reported as `needs-trust`.** Project-file hooks were probed twice and delivered
  nothing, even with an enabled features block and an inline `projects.<root>.trust_level`.
  Those flags are not evidence that project hooks load, so no automatic project-file delivery is
  claimed.
- Use the explicit launcher, which injects this installer's own digest-validated hook entries
  into the session inline configuration instead of rewriting any global file:

```bash
crewloom host run --project /abs/path --project-id <project-id> --host codex --model gpt-6-sol
```

`--one-shot-trust` adds a single `-c projects."<root>".trust_level="trusted"` override for that
invocation. `--bypass-hook-trust` exists for a vetted disposable fixture only and is refused
whenever a global hook file, a foreign project hook or another installed plugin is present: an
unvetted hook source is never bypassed.

### OpenCode 1.18.32 (V1)

- Installed plugin: `.opencode/plugins/crewloom-lifecycle.js`. A project plugin is loaded without
  `--pure`; a `--pure` run suppresses it entirely.
- The installed plugin package types are 1.18.23 while the binary is 1.18.32. The types are a
  schema hint only, never binary callback proof.
- OpenCode V2 is not supported: the V1 plugin implementation does not run on V2. An unsupported
  version is refused rather than extrapolated.
- The plugin refuses rather than silently continuing. A turn without a real `sessionID` and message identity, an unprepared session, an unknown session, or an explicit bridge refusal all stop
  generation instead of proceeding without the project contract.
- `chat.message` may omit its optional input `messageID`; the generated `output.message.id` then provides the real turn. Conflicting IDs or a message from another session are refused. No random or clock-based identity is substituted.
- No global configuration is written. Note that OpenCode merges configuration rather than
  replacing it, so a local config file is not proof of global isolation.

### Claude Code 2.1.150

- Installed control config: `.claude/settings.json`.
- Schemas are available and the adapter is installed-schema-ready, but this host was **logged
  out**. No callback has been observed, so status stays unobserved and no live flow is claimed.

## Guard policy

The guard runs before a host tool executes and covers only what the host actually delivers.

- A declared output may be added, updated, deleted or moved. Both endpoints of every move are
  validated with the same rules as any other destination, and every record in a multi-record
  patch is checked before the first one is allowed.
- Never writable, in any spelling, even when declared: `.crewloom`, `.git`, `.agents`, `.claude`,
  `.codex`, `.opencode` and `crewloom.project.json`, plus root `opencode.json` and `opencode.jsonc`. This includes the host's own configuration
  and plugin files, so an agent cannot edit the guard that is constraining it.
- A destination is refused when it resolves through a symlink, a hardlink, a physical case
  alias, a foreign directory, or the trusted Crewloom runtime.
- Unknown, hosted and MCP tools are denied under strict policy where the event is actually
  delivered.
- Compound, redirected and substituted shell commands are denied. No shell parser is claimed.

Limits worth stating plainly: a hook guard runs inside the host process and does not close a race
against a privileged concurrent mutation. The Docker broker remains the strong managed boundary.
Arbitrary external host tools and privileged processes remain outside managed coverage.

## Context injection

`UserPromptSubmit` (Codex, Claude) or `experimental.chat.system.transform` (OpenCode) freezes the
generation and injects it before the model generates.

- Mandatory rules and acceptance criteria are included unchanged and in full.
- A declared source body that does not fit the configured context limit is recorded as an
  explicit omission. Mandatory content alone exceeding the limit is refused, never truncated.
- The delivery marker exists only in this injected context. It is never written into a prompt, a
  source file, a criteria file or `AGENTS.md`, so a model reporting it discriminates real
  injection from ordinary file, skill or instruction discovery.

A real `PostToolUse` / `tool.execute.after` checkpoint invalidates the scoped generation for
declared changes, so the next turn is rebuilt from fresh sources, configuration and criteria.

## Verification

`Stop` (Codex, Claude) or `session.idle` (OpenCode) runs only the configured acceptance, through
the real Docker executor ledger. A `stop_hook_active` payload is skipped, so a stop hook cannot
author its own response loop.

Completion requires correlated executor evidence, valid output hashes, matching criteria and a
fresh context. A failed or interrupted run leaves the task incomplete with its evidence intact
and promotes no lesson. A session or turn scope is re-enterable after an interruption, while a
different host, checkout, configuration or session can never take a reserved root.

## Uninstall

```bash
crewloom host uninstall --project /abs/path --project-id <project-id> --host codex
```

Only unchanged owned items are removed. An altered owned file is preserved and reported as a
conflict for review.

## Not proven here

- Codex project-file hook loading is unproven; delivery is reported as `needs-trust`.
- Claude has no observed callback.
- No live provider call is made by the tests or by installation.
