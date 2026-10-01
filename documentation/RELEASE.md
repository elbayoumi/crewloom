# Initial public edition

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
