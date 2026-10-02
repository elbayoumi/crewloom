# Agent-host setup and handoff

Crewloom integrates through project-local role files and explicit handoff JSON. The supported installation layouts are `agents` (`.agents/skills`) and `claude` (`.claude/skills`). Layout installation and validation are tested; model behavior and automatic host discovery must be verified in your actual host.

## Setup

```bash
crewloom install --host agents --target /path/to/project
crewloom workflow doctor --host agents --project /path/to/project
crewloom workflow handoff --project /path/to/project
```

Use `--host claude` for the `.claude/skills` layout. Keep one installed copy of each selected role; the context generator rejects ambiguity. `install --force` preserves local memory. Docker doctor readiness is separate from host-role setup.

## English host task

> Read this project's AGENTS.md if present and the next role's installed SKILL.md and five brain documents. Consume Crewloom's handoff JSON. Bind its canonical project root and workflow ID for this entire task. Produce only the declared artifacts and explicitly authorized implementation changes. Read and verify upstream inputs. Run commands through the isolated workflow when possible. Record missing requirements or tools rather than inventing results. Deliver concrete file paths and acceptance evidence for review. Update only this project's memory.

## Arabic host task

> اقرأ AGENTS.md الخاص بالمشروع إن وجد، ودليل الدور التالي المثبّت وملفات البرين الخمسة. استخدم حزمة التسليم من Crewloom. ثبّت مسار المشروع ومعرف المسار طوال المهمة. أنتج الملفات المحددة وتعديلات التنفيذ المصرح بها فقط، وافحص المدخلات السابقة. شغّل الأوامر عبر المسار المعزول متى أمكن. وثّق المدخلات أو الأدوات الناقصة بدل اختراع نتائج. سلّم مواقع الملفات وأدلة القبول للمراجعة، وحدّث ذاكرة هذا المشروع فقط.

## Permissions and credentials

Configure the agent host's own file permissions for this project and read-only role guidance. Use task-specific authorization for external messages, publication, deployment, and credentials. Crewloom does not rewrite global host settings or forward provider API keys into command containers. A host that runs outside Docker remains outside the command sandbox.

The handoff identifies the next step, role setup, input/output paths, completed evidence and requested language. Give it to the next host explicitly. The runner does not send messages between hosts automatically.

## Automatic bounded artifact generation

A managed workflow `model` step selects `host: openai` or `host: anthropic` with an explicit model and local API credential. The following legacy CLI example requires the operator exception `--allow-host-cli`. It needs exactly one project-installed copy of the owning role. Crewloom sends that role's English procedure, five project memory documents, optional project constitution and only the step's declared text inputs. The host starts in a temporary directory rather than the project checkout, generates a schema-constrained artifact list, and never receives the Docker socket. Crewloom rejects missing, duplicate, undeclared, empty, oversized or symlink-directed outputs before writing them. Inputs are rechecked after generation.

```bash
cp -R examples/model-workflow/project /tmp/crewloom-model-demo
crewloom install --host agents --target /tmp/crewloom-model-demo --skill fullstack-mvp-engineer
crewloom workflow doctor --project /tmp/crewloom-model-demo --model-host codex
crewloom workflow run --allow-host-cli --project /tmp/crewloom-model-demo
```

Use a fresh project destination. Authenticate the selected CLI locally first; Crewloom never logs in for you or copies credentials into the project. Install/currently validate the CLI flags listed by doctor. Read the [Codex noninteractive documentation](https://learn.chatgpt.com/docs/non-interactive-mode) and [Claude programmatic interface](https://code.claude.com/docs/en/headless). The adapters were checked against Codex CLI 0.155.1 and Claude Code 2.1.150; later versions must preserve the required flags.

Codex uses read-only mode, ephemeral sessions, ignores user configuration and disables shell, multi-agent, plugins, apps, hooks, browser/computer and image tools. Claude uses an empty tool list, no user/project/local settings, empty strict MCP configuration, disabled hooks and session persistence. Returned tool events/permission denials fail generation. Operator-managed CLI authentication remains on the host. These flags and artifact guards do not constitute an OS sandbox around the CLI process; use trusted CLI binaries. Provider connections run outside Docker and consume your provider/account quota.

Model selection is optional in a step's `model` field. If omitted, the adapter uses the CLI's built-in default; Codex user-config defaults are deliberately not loaded. No fallback to a different host/model occurs. Record a model explicitly when comparing model quality. Generation evidence records requested model, CLI version, duration and reported usage/cost; unreported cost stays null. Provider error text is withheld from public/project logs because it may contain sensitive configuration. Diagnose credentials locally.

A successful model step means declared artifacts were generated, not that they are correct. Follow it with Docker command checks and a separate review task when appropriate. Failed or interrupted unchanged generations consume the persistent two-attempt budget. Artifacts can be partially written if the filesystem fails during the final replacements; inspect the project diff before retrying. Memory changes occur only if explicitly declared as outputs or performed by the separate reviewer.

Managed execution now rejects native model CLI steps by default. See [enforcement and compatibility](ENFORCEMENT.md) before running an existing model plan.
