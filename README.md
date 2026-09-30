# Crewloom

**Skills, memory, and checks for agent work.**

[العربية](README.ar.md) · [Skill catalog](documentation/SKILLS.md) · [Getting started](documentation/GETTING_STARTED.md) · [Architecture](documentation/ARCHITECTURE.md)

Crewloom is an open-source, repository-native toolkit for specialist AI agent work. It combines **42 English role guides**, clean working-memory templates, a small Python CLI, bounded context packs, and repository checks.

Derived from RUMUZE Agency's internal workspace, this first public edition adapts the role procedures for general use. It excludes client records, private operational history, infrastructure configuration, and the internal Code Vault application. The full internal workflow implementations are not included in this edition.

## Start in three commands

Requires Python 3.9+ and Git. The included core tools use the Python standard library; no provider key is needed for these commands.

```bash
git clone https://github.com/elbayoumi/crewloom.git
cd crewloom
python3 scripts/crewloom.py list
```

Inspect and validate a role:

```bash
python3 scripts/crewloom.py show fullstack-mvp-engineer
python3 scripts/crewloom.py validate
```

Build a context pack:

```bash
python3 scripts/crewloom.py context fullstack-mvp-engineer --out /tmp/crewloom-context.md --language en
python3 scripts/crewloom.py context fullstack-mvp-engineer --out /tmp/crewloom-context-ar.md --language ar
```

Open this checkout in your agent host and ask it to read `AGENTS.md`, the selected skill, and its memory before executing your task. See [the getting-started guide](documentation/GETTING_STARTED.md).

## What you get

| Component | Purpose |
| --- | --- |
| 42 role guides | Software, QA, design, marketing, sales, delivery, and operations procedures |
| Five memory templates per role | Architecture, completed work, challenges, ideas, and backlog |
| Context packs | Complete source documents or explicit reading references within a bounded budget |
| Bilingual context labels | English by default, Arabic through `--language ar`; source procedures remain English |
| Structure validator | Arabic, English, or mixed procedure sections with mandatory memory checks |
| Resource-pattern checker | Heuristic detection of over-fetching, looped requests, and heavy imports |
| Commit and CI checks | Python syntax, Markdown links, role structure, and core regression tests |

## Use Arabic or English

English:

> Read AGENTS.md and the context-guardian role. Use English. Review the local documentation and report concrete issues. Do not make external changes.

العربية:

> اقرأ AGENTS.md ومهارة context-guardian. استخدم العربية. راجع التوثيق المحلي واعرض المشاكل المحددة دون تغييرات خارجية.

The agent constitution selects the response language. Context-pack labels support both languages; Python errors and role source documents are primarily English. Host model behavior and every specialist workflow have not been evaluated across all providers.

## Scope and limitations

Crewloom supplies procedures and local tools. Your agent host supplies the model, tool permissions, and execution environment. It does not provide a central orchestration server, model billing dashboard, autonomous task scheduler, or external account credentials.

Most roles are instruction guides, not bundled software implementations. A video role needs media tools; an advertising role needs authorized platform access. Read the skill and project requirements before execution. Structural validation is distinct from demonstrating end-to-end role performance.

This edition is consumed by cloning the repository. No npm or PyPI package is published.

## Development

```bash
git config core.hooksPath .githooks
python3 scripts/check_repository.py
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Core test evidence and release scope are recorded in [the release notes](documentation/RELEASE.md).

## License

[Apache-2.0](LICENSE). Copyright 2026 RUMUZE Agency. See [NOTICE](NOTICE) for attribution. The product name Crewloom is separate from the agency identity.
