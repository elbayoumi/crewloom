<p align="center"><img src="assets/crewloom-banner.svg" alt="Crewloom: Give agent work a role, memory, and evidence." width="100%" /></p>

<p align="center">
<a href="https://github.com/elbayoumi/crewloom/actions/workflows/ci.yml"><img src="https://github.com/elbayoumi/crewloom/actions/workflows/ci.yml/badge.svg" alt="Repository checks" /></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0" /></a>
<img src="https://img.shields.io/badge/Python-3.9%2B-3776AB" alt="Python 3.9 or later" />
</p>

<p align="center"><a href="README.ar.md">العربية</a> · <a href="documentation/SKILLS.md">42 roles</a> · <a href="documentation/TOOLS.md">Tool catalog</a> · <a href="examples/README.md">Run examples</a> · <a href="CONTRIBUTING.md">Contribute</a></p>

Crewloom is a repository-native toolkit for specialist AI agent work. Choose a role, give it your project inputs, keep working memory, and check the result with local tools. Use your existing agent host and model.

The toolkit brings together **42 English role guides**, **108 detailed reference documents**, **12 Python tools**, and **five memory templates per role**. English is the primary entry point; detailed source playbooks include Arabic. Context packs and task instructions support English or Arabic.

## Try it in a minute

Requires Git and Python 3.9+. The included tools use the standard library.

```bash
git clone https://github.com/elbayoumi/crewloom.git
cd crewloom
python3 scripts/crewloom.py tools
python3 scripts/crewloom.py run workflow-contract -- examples/workflows/valid.json
python3 scripts/crewloom.py run seo-packet -- --packet examples/seo/article-packet.json
```

Both example checks print `PASS`. See [six runnable examples](examples/README.md), including MCP configuration, spend pacing, video timing, and responsive grids.

## What can I do with it?

| Work | Start with | Concrete output |
| --- | --- | --- |
| Build a product feature | [Full-stack engineer](.agents/skills/fullstack-mvp-engineer/SKILL.md) + [QA](.agents/skills/qa-test-automation-engineer/SKILL.md) | Implementation and a delivery evidence packet |
| Review a frontend | [UI auditor](.agents/skills/frontend-ux-auditor/SKILL.md) | Source findings, grid checks, and supplied layout evidence |
| Prepare organic content | [SEO engineer](.agents/skills/seo-growth-engineer/SKILL.md) | Article brief and checked metadata packet |
| Produce a short video | [Script architect](.agents/skills/video-script-architect/SKILL.md) + [Studio director](.agents/skills/studio-director/SKILL.md) | Beat sheet, pacing measurement, and production handoff |
| Review automation | [Automation operations](.agents/skills/automation-ops-engineer/SKILL.md) | Checked n8n export and operational handoff |
| Coordinate project work | [Context guardian](.agents/skills/context-guardian/SKILL.md) | Bounded context pack and updated project memory |

Follow the [workflow recipes](documentation/WORKFLOWS.md) for role order, inputs, and acceptance evidence. Roles guide your agent; specialist platforms and project assets remain project inputs.

## Give your agent a task

Open the checkout in your agent host. Start with a specific role and outcome:

> Read AGENTS.md and the frontend-ux-auditor skill, including its references and brain. Use English. Review my project's responsive layout, run the applicable local checks, and report findings with file locations and evidence. Update working memory when finished.

> اقرأ AGENTS.md ومهارة frontend-ux-auditor ومراجعها والبرين. استخدم العربية. راجع تجاوب واجهة مشروعي، وشغّل الفحوص المحلية المناسبة، واعرض المشاكل بمواقع الملفات والأدلة. حدّث الذاكرة بعد الانتهاء.

```bash
python3 scripts/crewloom.py show frontend-ux-auditor
python3 scripts/crewloom.py context frontend-ux-auditor --language en --out /tmp/crewloom-en.md
python3 scripts/crewloom.py context frontend-ux-auditor --language ar --out /tmp/crewloom-ar.md
```

## Inside the repository

| Location | Contents |
| --- | --- |
| [.agents/skills](.agents/skills) | Role guides, detailed playbooks, architecture references, memory, and tools |
| [documentation](documentation) | Setup, architecture, workflows, tool contracts, and release evidence |
| [examples](examples) | Synthetic inputs with runnable commands and expected results |
| [Brain](Brain) | Shared architecture, decisions, challenges, ideas, and roadmap |
| [scripts](scripts) | CLI and repository validation |
| [.github/workflows](.github/workflows) | Python 3.9 and 3.14 CI checks |

## How checks work

Run the repository gate locally; enable the same gate before commits:

```bash
git config core.hooksPath .githooks
python3 scripts/check_repository.py
```

Checks cover role structure, Python syntax, Markdown links, and regression suites. Domain tools inspect the inputs documented in the [tool catalog](documentation/TOOLS.md). Static findings and evidence bookkeeping do not establish rendered UI quality or the truth of supplied evidence.

Crewloom does not include a hosted orchestration server or a model provider. It is distributed as a Git repository; no npm or PyPI package is published. See [project inputs and boundaries](documentation/PROJECT_INPUTS.md).

## Documentation and contribution

Start with [Getting started](documentation/GETTING_STARTED.md), [Architecture](documentation/ARCHITECTURE.md), and [Workflow recipes](documentation/WORKFLOWS.md). Read [Contributing](CONTRIBUTING.md), [Security](SECURITY.md), and [the changelog](CHANGELOG.md) before proposing changes.

Derived from RUMUZE Agency's first-party procedures, with clean public memory and filtered operational references. Client records, private infrastructure, and internal history are excluded. See [provenance](documentation/PROVENANCE.json).

[Apache-2.0](LICENSE) · Copyright 2026 RUMUZE Agency · [Attribution](NOTICE).
