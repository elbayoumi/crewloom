<p align="center"><img src="assets/crewloom-banner.svg" alt="Crewloom: Give agent work a role, memory, and evidence." width="100%" /></p>

<p align="center">
<a href="https://github.com/elbayoumi/crewloom/actions/workflows/ci.yml"><img src="https://github.com/elbayoumi/crewloom/actions/workflows/ci.yml/badge.svg" alt="Repository checks" /></a>
<a href="https://github.com/elbayoumi/crewloom/releases/latest"><img src="https://img.shields.io/github/v/release/elbayoumi/crewloom?color=2ea44f&label=release" alt="Latest Release" /></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0" /></a>
<img src="https://img.shields.io/badge/Python-3.9%2B-3776AB" alt="Python 3.9 or later" />
<a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-Protocol-purple" alt="Model Context Protocol" /></a>
<a href="https://github.com/elbayoumi/crewloom/stargazers"><img src="https://img.shields.io/github/stars/elbayoumi/crewloom?style=social" alt="GitHub stars" /></a>
</p>

<p align="center"><a href="README.ar.md">العربية</a> · <a href="documentation/SKILLS.md">43 Roles</a> · <a href="documentation/TOOLS.md">Tool Catalog</a> · <a href="examples/README.md">Run Examples</a> · <a href="dashboard/README.md">Live Dashboard</a> · <a href="CONTRIBUTING.md">Contribute</a></p>

Crewloom is a repository-native toolkit for specialist AI agent work. Choose a role, give it your project inputs, keep working memory, and check the result with local tools. Use your existing agent host and model.

The toolkit brings together **43 English role guides**, **153 detailed reference documents**, **19 catalogued Python tools**, and **five memory templates per role**. English is the primary entry point; detailed source playbooks include Arabic. Context packs and task instructions support English or Arabic. See [language support and paired acceptance](documentation/LANGUAGES.md) for UI behavior and runtime boundaries.

Managed workflows add project and checkout identities, frozen context, isolated Docker acceptance, credential-scoped review, and concurrent task worktrees. [Native lifecycle setup](documentation/HOST_LIFECYCLE.md) connects supported host callbacks; [agency readiness](documentation/READINESS.md) reports client evidence without modifying client projects. See [enforcement boundaries](documentation/ENFORCEMENT.md) for what each execution path actually covers.

The optional [project task MCP bridge](documentation/MCP_BRIDGE.md) gives Codex and other MCP hosts read-only project context and workflow packets. Explicitly enabled candidate imports preserve task review and isolated acceptance. Tested templates are available for [Cursor](examples/mcp/cursor.json) and [Windsurf](examples/mcp/windsurf.json) (see [MCP guide](examples/mcp/README.md)).

## Quickstart in 20 seconds

Run the zero-friction onboarding script or test the interactive walkthrough:

```bash
# 1-line bootstrap & sanity check
./quickstart.sh

# Interactive 20-second walkthrough (role selection, working memory, Docker isolation)
python3 scripts/crewloom.py demo --fast
```

The [quickstart script](quickstart.sh) detects prerequisites, configures Python dependencies, and provides instant verification without requiring external API keys.

## How Crewloom works: Architecture & workflow

The diagram below illustrates the end-to-end task lifecycle across developer IDEs, the vector memory engine, isolated container sandbox, and evidence review gates:

```mermaid
flowchart TD
    subgraph IDE ["1. AI IDEs & Developer Entry"]
        CLI["Developer CLI / Quickstart<br/><code>quickstart.sh</code> • <code>crewloom demo</code>"]
        IDEs["AI IDE Ecosystem<br/>Cursor • Windsurf • Codex"]
        MCP["Project Task MCP Bridge (stdio)<br/><code>examples/mcp/{cursor,windsurf}.json</code>"]
        IDEs <--> MCP
    end

    subgraph Memory ["2. Vector Memory & Context Engine"]
        Rules["Policy & Constitution<br/><code>AGENTS.md</code>"]
        Roles["43 Specialist Roles<br/><code>.agents/skills/*/SKILL.md</code>"]
        Brain["Hierarchical Memory & Lessons<br/><code>Brain/</code> • Role Brains • <code>lessons.jsonl</code>"]
        Indexer["Code Range Index & Vector Recall<br/>Lexical + Semantic Matching • Range Hashes"]
        FrozenGen["Sealed Frozen Generation<br/><code>sha256</code> + <code>semantic_sha256</code> Context"]
        
        Rules --> FrozenGen
        Roles --> FrozenGen
        Brain --> Indexer
        Indexer --> FrozenGen
    end

    subgraph Sandbox ["3. Isolated Execution Sandbox"]
        Worktree["Git Task Worktree<br/><code>.crewloom/worktrees/{task_id}</code>"]
        Docker["Isolated Docker Container<br/><code>--network none</code> • Read-Only Snapshot"]
        Journal["Transactional Grouped Publication<br/>Atomic Journal & Rollback Protection"]
        
        Worktree --> Docker
        Docker --> Journal
    end

    subgraph Verification ["4. Evidence Verification & Review"]
        Gate["Objective Contract Evaluator<br/>Standard-Library Verifier • Test Suites"]
        Reviewer["Reviewer Credential Registry<br/>Cryptographic Proof • Human Attestation"]
        GitMerge["Fast-Forward Git Integration<br/><code>git merge --ff-only</code>"]
        
        Journal --> Gate
        Gate --> Reviewer
        Reviewer --> GitMerge
    end

    subgraph Feedback ["5. Observability & Memory Loop"]
        Dashboard["Live Local Dashboard<br/><code>localhost:4317</code> • Stdio Event Stream"]
        Evidence["Executor Evidence Ledger<br/>Promotes Verified Lessons Only"]
    end

    CLI --> FrozenGen
    MCP --> FrozenGen
    FrozenGen --> Worktree
    GitMerge --> Evidence
    Evidence --> Brain
    Gate -.-> Dashboard
    Journal -.-> Dashboard
```

## Framework comparison

| Dimension | Crewloom | CrewAI | AutoGen (AG2) | LangGraph |
| :--- | :--- | :--- | :--- | :--- |
| **Architecture** | **Repository-native toolkit**; standard library Python 3.9+; brings 43 roles to existing hosts. | Standalone framework; heavy dependencies (Pydantic, LiteLLM); role-playing simulation. | Multi-agent conversation runtime; message-passing loops; code-extraction execution. | Graph-based state machine library; deeply coupled to LangChain ecosystem. |
| **Memory & Vector Recall** | **3-tier structured memory** (`Brain/`, role brains, project context); hash-anchored code ranges; evidence-gated lessons. | ChromaDB vector store + SQLite; generic chunk search without line-hash verification. | Conversational chat history buffer; optional external RAG plugins; no repository brain. | State channel checkpointers (Memory/Postgres); vector search deferred to external stores. |
| **Isolation & Security** | **Docker sandbox (`--network none`)**; read-only snapshots; transactional publication with rollback journals. | Host OS execution by default; optional Docker without strict network or file isolation. | Optional Docker code executor; network enabled by default; no transactional rollback. | No built-in sandbox; executes directly on host or requires manual third-party sandbox setup. |
| **Orchestration** | **Deterministic DAG workflows**; concurrent Git worktrees; credential-reviewed `--ff-only` integration. | Sequential / hierarchical delegation; prone to unbounded agent chatter and loops. | Conversational group chats; prone to repetitive chatter and missed termination conditions. | Explicit stateful graphs with cycles and conditional edges; boilerplate-intensive. |
| **Developer Experience** | **Zero friction**: 1-line quickstart (`quickstart.sh`), instant 20-second offline demo (`crewloom demo`), zero API keys needed. | High setup friction; large dependency tree; mandatory paid API key for hello-world. | Requires virtualenv, `OAI_CONFIG_LIST` configuration, and active LLM credentials. | Requires multi-package installation, model credentials, and complex graph wiring. |
| **AI IDE & MCP** | **Native stdio MCP bridge** with fine-grained security flags for Cursor, Windsurf, and Codex. | No repository MCP server; relies on standalone Python execution scripts. | Client-side tool consumer only; does not expose repo context or task packets to IDEs. | Client-side tool consumer; lacks repository-native MCP server for AI IDEs. |
| **Cloud Overhead** | **100% local and offline**; zero telemetry; local dashboard on `localhost:4317`. | Pushes toward CrewAI Enterprise / cloud monitoring. | Standalone library; optional cloud extensions. | Strongly coupled with LangSmith cloud monitoring and LangGraph Cloud. |

## Execute a software workflow

Run a six-stage feature with actual commands, project-bound evidence and resumable state:

```bash
docker pull python:3.14-slim
cp -R examples/software-workflow/project /tmp/crewloom-demo
python3 scripts/crewloom.py workflow doctor
python3 scripts/crewloom.py workflow run --project /tmp/crewloom-demo
python3 scripts/crewloom.py workflow handoff --project /tmp/crewloom-demo
```

Use a fresh destination. Commands run inside Docker with network access disabled and only the selected project mounted. The example tests a supplied Unicode implementation in English and Arabic; it demonstrates execution, not model-generated feature quality.

For real model-generated source, run the [bounded model workflow](examples/model-workflow/README.md) with Codex or Claude and verify it in Docker. Compare repeated submissions with the [provider-trial harness](examples/evaluation/unicode-slug/HOST_TRIALS.md).

For a complete application with parallel billing and planning tasks, dependency-aware integration,
English and Arabic reports, and credential-reviewed publication, run the
[concurrent development example](documentation/DEVELOPMENT_EXAMPLE.md). Its acceptance uses real
worktrees and Docker; the automated regression suite substitutes only provider generation.
The [controlled context study](documentation/CONTEXT_STUDY.md) measures input tokens, cache usage,
latency and held-out correctness separately. Missing provider metrics remain unknown.

Use the [software task plan](workflows/software-feature.json) for agent-produced work. Read [execution and failure handling](documentation/EXECUTION.md), [host setup and portable agent packets](documentation/HOSTS.md), and [objective evaluation](examples/evaluation/unicode-slug/README.md).

## Try local checks in a minute

Requires Git and Python 3.9+. The Python core uses the standard library; isolated workflows additionally require Docker.

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
| Reverse engineering & binary audit | [Reverse engineering analyst](.agents/skills/reverse-engineering-analyst/SKILL.md) | Findings packet with evidence-linked verification |
| Review a frontend | [UI auditor](.agents/skills/frontend-ux-auditor/SKILL.md) | Source findings, grid checks, and supplied layout evidence |
| Prepare organic content | [SEO engineer](.agents/skills/seo-growth-engineer/SKILL.md) | Article brief and checked metadata packet |
| Produce a short video | [Script architect](.agents/skills/video-script-architect/SKILL.md) + [Studio director](.agents/skills/studio-director/SKILL.md) | Beat sheet, pacing measurement, and production handoff |
| Review automation | [Automation operations](.agents/skills/automation-ops-engineer/SKILL.md) | Checked n8n export and operational handoff |
| Coordinate project work | [Context guardian](.agents/skills/context-guardian/SKILL.md) | Bounded context pack and updated project memory |

## Use it in your project

From the clone, create an isolated Python environment (macOS/Linux):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .  # adds the `crewloom` command
crewloom install --host claude --target /path/to/your/project --skill frontend-ux-auditor
```

`--host claude` copies roles to `.claude/skills`; `--host agents` copies them to `.agents/skills` for hosts that read that folder (omit `--skill` for all 43). Existing roles are never overwritten without `--force`. Copied roles are static: re-run the command after pulling updates. A normal `pip install .` builds a local wheel with the Python runtime, role resources, adapters and examples. The editable command above keeps a development link to the clone. The optional Node dashboard runs from a source checkout.

Use the optional [native Codex plugin](documentation/CODEX_PLUGIN.md) for role/context/workflow guidance and the separate [manual browser companion](documentation/CHROME_EXTENSION_SIDE_PANEL.md) for element inspection and tab capture. For AI IDEs, integrate with tested MCP templates for [Cursor](examples/mcp/cursor.json) and [Windsurf](examples/mcp/windsurf.json) (see [MCP guide](examples/mcp/README.md)).

## Live dashboard

```bash
crewloom dashboard          # needs Node 24+; opens on http://localhost:4317
```

![Dashboard demo: role status, tool runs, and live updates](assets/dashboard-demo.gif)

Monitor roles, memory, and tool runs live with the optional [web dashboard](dashboard/README.md) ([MP4 version](assets/dashboard-demo.mp4)). `crewloom dashboard` opens on `127.0.0.1` without a password. Local request and Origin checks remain active; non-loopback hosting requires an explicitly configured `CREWLOOM_DASHBOARD_TOKEN`.

See [evidence from real projects](documentation/EVIDENCE.md), including a false positive.

For contributing or preparing a release, use the [verification checklist](documentation/RELEASE.md).
The current package metadata is `0.6.1`; check the repository's release tags for what has been published.

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

Start with [Getting started](documentation/GETTING_STARTED.md), [Architecture](documentation/ARCHITECTURE.md), [Workflow recipes](documentation/WORKFLOWS.md), and [OpenCode/local models](documentation/LOCAL_MODELS.md). Read [Contributing](CONTRIBUTING.md), [Security](SECURITY.md), and [the changelog](CHANGELOG.md) before proposing changes.

Derived from RUMUZE Agency's first-party procedures, with clean public memory and filtered operational references. Client records, private infrastructure, and internal history are excluded. See [provenance](documentation/PROVENANCE.json).

[Apache-2.0](LICENSE) · Copyright 2026 RUMUZE Agency · [Attribution](NOTICE).

Project selection and isolation: [project guide](documentation/PROJECTS.md).

## Self-Editing Mode

Use [Self-Editing Mode](documentation/SELF_EDITING.md) to repair an existing role, tool or document from an observed problem. The workflow binds a project, makes an in-place change, verifies acceptance and records the result. Arabic activation name: **التعديل الذاتي**.

Managed execution now rejects native model CLI steps by default. See [enforcement and compatibility](documentation/ENFORCEMENT.md) before running an existing model plan.

[Context efficiency](documentation/CONTEXT_EFFICIENCY.md) selects relevant historical records while keeping rules and inputs complete, and verifies context hashes before reusing completed model work.

[Project repository maps](documentation/REPOSITORY_MAP.md) provide a bounded file/symbol index with project-local parsing reuse: `crewloom map --project /path/to/git-project --query login`.

[Project context](documentation/PROJECT_CONTEXT.md) is opt-in per project and adds a portable project ID, a local checkout binding, a frozen per-task context with hash-validated code ranges, and lessons that only recorded executor evidence can promote.

```bash
crewloom project enter  --project /path/to/your/project --project-id sample-project --task-id login-fix --role context-guardian --seed src/auth.py
crewloom project status --project /path/to/your/project --project-id sample-project
crewloom project finish --project /path/to/your/project --project-id sample-project --task-id login-fix --evidence '[{"workflow": "login-flow", "step": "acceptance", "scope": "unit tests"}]'
```

Entry creates missing metadata and refreshes existing ones without rewriting your constitution or role memory. `status` reports whether the lifecycle is managed by the Crewloom runner, instruction-assisted or manual; opening a folder never triggers it by itself. `finish` completes a task only from recorded executor evidence; `--verification` records an operator attestation and keeps the task awaiting verification. See [the pilot](documentation/PROJECT_CONTEXT.md#measurements) for measured cold/warm behaviour.

## Run independent tasks concurrently

Independent tasks in one project run as a batch instead of one after another. Each task gets its own Git worktree under the project's `.crewloom`, runs the same isolated Docker executor, and a dependent task reads its ancestors' committed output:

```bash
crewloom coordinator validate --project /path/to/your/project --project-id sample-project --manifest coordinator.json
crewloom coordinator run      --project /path/to/your/project --project-id sample-project --manifest coordinator.json
crewloom coordinator prepare  --project /path/to/your/project --project-id sample-project --manifest coordinator.json
```

The checked-out tree changes only after an explicit reviewed decision moves it by one recorded fast-forward. See [the coordinator](documentation/COORDINATOR.md) and its [Arabic guide](documentation/COORDINATOR.ar.md).

## Schedule projects and monitor admission

Queue explicit registered projects by priority, keep one batch per root, and share managed-generation allowances across worktrees. The dashboard shows project-local tool activity, role failures, queue status, and unknown cost without treating it as zero.

See [scheduling and shared budgets](documentation/SCHEDULING_AND_BUDGETS.md) for setup, crash recovery, and the distinction between admission allowances and vendor billing limits. The queue preserves the existing review step before publication.

See the [Arabic/English developer pilot](examples/bilingual-evaluation/README.md) for the actual generated code, 40 held-out cases, passing Codex trials, and preserved provider failures. Cross-provider evaluation remains incomplete.

[Source-linked user context](documentation/USER_CONTEXT.md) adds project-local quoted statements, labelled assumptions and explicit task interpretations to frozen model context. Corrections retain history; changed sources invalidate reuse. This is provenance checking, not proof of speaker identity or model accuracy.

[Private customization and selected publication](documentation/PRIVACY.md) keeps conversation inputs and project memory local, chains commit guards and builds reviewed file-selection packets. Known-pattern scanning does not prove content is safe to publish.

Optional [native prompt capture](documentation/USER_CONTEXT.md) preserves exact private user messages after task opt-in and blocks actions on unresolved source-linked questions. The separate [scoped native AX acceptance](documentation/NATIVE_DESKTOP.md) client targets an account-free synthetic application; live control requires human-approved driver capabilities and actual Accessibility verification.
