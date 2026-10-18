# Release and verification

## Current development snapshot

The package version is `0.8.0`. The sections below retain historical release evidence;
they do not establish acceptance of later changes. A release requires checks on its exact
commit, successful hosted CI and a deliberate tag/publication step.

| Component | Prerequisites | Acceptance |
| --- | --- | --- |
| Core CLI and roles | Git, Python 3.9+ | Full repository gate, including refusal cases |
| Dashboard | Node 24+, locked npm dependencies | Unit tests, TypeScript, production build |
| Distribution | Python, network access to the build backend | Build/install wheel and sdist outside the checkout |
| Task MCP | Python 3.11+, `.[mcp]`, Docker | Actual SDK read/write round trips and container verification |
| Chrome companion | Playwright 1.63.0, Chromium; Linux uses Xvfb | Load the actual unpacked extension, inspect, click and capture |
| Native desktop fixture | macOS, explicitly approved bounded driver | Separate opt-in live fixture acceptance; CI does not grant OS access |

Run these commands from an activated development environment at the repository root:

```bash
git config core.hooksPath .githooks
python -m pip install '.[syntax,mcp]' 'playwright==1.63.0'
python scripts/check_repository.py
# After changing tracked files, refresh the manifest first: python scripts/check_repository.py --write-manifest
python scripts/package_browser.py --check
CREWLOOM_DISTRIBUTION_TESTS=1 python -m unittest discover -s scripts -p test_distribution.py
CREWLOOM_MCP_TESTS=1 python -m unittest discover -s scripts -p test_mcp_bridge.py
CREWLOOM_MCP_TESTS=1 python -m unittest discover -s scripts -p test_chat_capture.py
python -m playwright install chromium
CREWLOOM_REAL_BROWSER=1 python -m unittest discover -s scripts -p test_sidepanel.py
```

The integration commands require Python 3.11+; Python 3.9 remains supported for the
standard-library core. Pull `python:3.14-slim` before Docker acceptance. On Linux install
Chromium's system dependencies with `python -m playwright install --with-deps chromium`
and prefix the browser command with `xvfb-run -a` for a headed display.

In `dashboard/`, run `npm ci`, `npm test`, `npx tsc --noEmit`, and `npm run build`.
Check `npm audit` separately: zero known advisories does not prove absence of vulnerabilities.

[CI](../.github/workflows/ci.yml) runs the supported Python matrix, dashboard, distribution,
isolated workflows, coordinator, path boundaries and actual MCP/browser protocols. Explicit
browser/distribution acceptance fails if its prerequisites are missing; default core runs
retain optional skips. The screenshot-refresh and separate Playwright MCP provider tests
remain opt-in. No paid model generation or native desktop permission prompt runs in CI.

Dependency update proposals are scheduled through [Dependabot](../.github/dependabot.yml).
Updates require the same checks and review; there is no automatic merge rule.

## Historical initial public edition

Crewloom provides 42 English public role adaptations, clean memory templates, a repository CLI, bilingual context labels, a structure validator, and a resource-pattern checker.

## Included and excluded

Included: public procedures, first-party core Python tools, regression fixtures, Apache-2.0 attribution, documentation, and CI / commit checks.

Excluded: upstream Git history, client records, operational memory, account credentials, infrastructure services, third-party media, full internal tool catalogs, and private commercial templates.

The source adaptation hashes are recorded in [PROVENANCE.json](PROVENANCE.json). No external dependencies or bundled media are required by the core Python tools. Third-party CI actions are referenced, not redistributed as toolkit source.

## Validation scope

The release process checks public role structure, Python syntax, Markdown links, local CLI behavior, core regression fixtures, heuristic scanner positive / negative cases, redacted secret patterns, and commit gate rejection / acceptance. The machine-readable evidence records completed results; it does not establish specialist task quality or production suitability.

CI is configured for Python 3.9 and 3.14. Local validation uses the runtime recorded in the evidence. A configured CI matrix is distinct from a completed hosted run.

## Remaining work

- Representative role evaluations across agent hosts and both response languages.
- Optional external tool integrations and their own setup / license review.
- Broader application localization and a package distribution format.

There is no central agent orchestration service or published package in this edition.

## Recorded results

[VALIDATION.json](VALIDATION.json) records 42 accepted role structures, 19 passing core regressions, successful English / Arabic context CLI commands, a zero-finding redacted public-source secret-pattern scan, and gate rejection / acceptance. Repository checks also pass from an extracted source archive. Specialist workflows are not covered by those results.

## 0.2.0 depth refresh

108 detailed references, twelve local tools and six runnable examples. All 52 regression tests pass locally. See [the changelog](../CHANGELOG.md) and [validation metadata](VALIDATION.json).

## 0.4.0 execution foundation

Docker-isolated software workflow commands, manual task handoffs, persistent evidence and resume, objective feature scoring and six English role contracts. See [execution](EXECUTION.md), [host setup](HOSTS.md), [evidence](EVIDENCE.md), and [changelog](../CHANGELOG.md).

## 0.5.0

Adds project-bound model artifact generation for Codex/Claude CLIs, a real generated-feature/Docker acceptance example, repeated provider collection with label-free grading, and English specialist procedures for all 42 roles. Codex generation and acceptance are executed; Claude live success is unavailable because the CLI is logged out. Ten Codex trial submissions tie at full contract acceptance. This release makes no broad superiority or independent-human-review claim.

Provider CLI processes remain trusted host dependencies outside the Docker command sandbox. Authenticate locally, review supplied inputs, and run generated code through isolated checks. Default model identity and unreported cost are not inferred.

## 0.5.1

Workflow task actions require an explicit project root. Project ownership persists while a manual task awaits an artifact; other workflows cannot take that root until completion or explicit cancellation. Cancellation preserves partial files and failure history. Concurrent same-root rejection, parallel distinct-root execution and runtime reservation boundaries are verified. Direct host edits are outside the runner guards.

## 0.6.0 development metadata

The preceding development snapshots used `version = "0.6.0.dev0"`. The reviewed release candidate now uses `0.6.0`; metadata alone does not assert a published tag.

- Installable distributions: a standard wheel and an sdist build from `pyproject.toml` with a pinned `setuptools>=77,<81` backend and no runtime dependencies. One explicit resolver (`scripts/crewloom_resources.py`) maps repository paths to either a checkout or the installed data package, so `list`, `show`, `install`, `context`, `validate`, `project` and `workflow` all work outside the source checkout without duplicating the role tree, reading the working directory, or relying on an editable path.
- The flat runtime is declared as `py-modules`, including `js_syntax`, which `repo_map` imports at module scope so an installed navigation index always has it. The optional extra `crewloom[syntax]` pins `tree-sitter==0.23.2`, `tree-sitter-javascript==0.23.1` and `tree-sitter-typescript==0.23.2`. Without it every core command still works and the generated map records that approximate extraction was used. `crewloom[mcp]` additionally pins the official MCP SDK on Python 3.11+.
- The sdist carries the approved public source: role trees, documentation, examples, English/Arabic guides, `LICENSE`, `NOTICE`, `MASTER_BRAIN.md`, `Brain/`, `.github/`, `.githooks/`, and the dashboard sources referenced by the README. It never carries `.crewloom`, `node_modules`, generated builds, or logs.
- The dashboard is not bundled in the wheel because its Node dependencies are not. Running `crewloom dashboard` from an installed wheel prints that diagnosis with exit 2 instead of a missing-file traceback; start it from a checkout or unpacked sdist.
- The dashboard launcher enables password-free access on a verified loopback listener. Local URL and mutation Origin checks remain required. Non-loopback hosting requires an explicitly configured credential; local launches do not generate a token. See [dashboard authentication](../dashboard/README.md#authentication).

`CREWLOOM_DISTRIBUTION_TESTS=1` builds and installs both artifacts and exercises them outside the checkout. It is opt-in and never part of the commit gate.

## 0.6.0 release scope

The 0.6.0 candidate packages the integrated workflow, coordinator, source-context, MCP, browser and scoped native functionality described in the current guides. The [operational acceptance record](../examples/evaluation/agency-acceptance-20261015.json) records real model-generated delivery, actual isolated checks and scoped Chrome/Calculator/TextEdit results; it also preserves failures and coverage limits. The core remains dependency-free. The optional MCP extra uses the pinned official SDK; the dashboard remains a source/sdist component with its own Node dependencies. Loopback dashboard access follows the current [dashboard guide](../README.md#live-dashboard).

A release tag is created only after the final-head required GitHub checks pass and the reviewed PR is normally merged. Wheel, sdist and extension ZIP are reviewed local build outputs; no package-index upload is implied. Broad specialist quality, all-app desktop control and unknown provider cost/model identity are not release claims.

## 0.6.1 language follow-up

Browser companion2.3.2 follows the saved language for known error details and its own in-page status, including Arabic RTL and English LTR. Language changes preserve the underlying site and hidden HUD state. Empty capture and accessible control labels are localized. Paired rendered regressions cover reload, frame propagation and refusal states. See [language support](LANGUAGES.md) for exact scope; unknown external diagnostics and technical identifiers remain intact.
