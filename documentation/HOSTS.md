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
