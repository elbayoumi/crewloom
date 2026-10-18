---
name: crewloom
description: Use Crewloom's installed project roles, source-linked context, memory, handoffs and isolated verification when the user asks to work through Crewloom. Requires its local CLI; does not provide desktop-control tools or a model provider.
---

# Crewloom

Use the installed `crewloom` runtime; do not maintain a second copy of its role guides here.

1. Bind the explicit selected project ID and canonical root. Read its constitution and relevant memory. If identity is ambiguous, obtain it before writes; never reuse another project's root or memory.
2. Check `crewloom --help` and `crewloom list`. If the runtime is missing, explain the dependency and use the repository's installation guide; do not claim plugin installation installed the runtime.
3. Select the role that owns the outcome; inspect it with `crewloom show ROLE`. Install its project-local copy only when needed using `crewloom install --host agents --target ROOT --skill ROLE`. Read its procedure and project-local memory.
4. Use `crewloom project status --project ROOT --project-id ID` and the existing `project enter` workflow to prepare scoped context. Keep quoted user statements distinct from assumptions, and define real acceptance criteria. Inspect available CLI help before supplying optional arguments.
5. Reuse existing workflow/coordinator plans and `workflow handoff` or `workflow agent-packet` for declared outputs. Run acceptance through the existing Docker executor. Generation, imported/operator artifacts and a passing process exit are different from reviewed delivery.
6. Preserve failed attempts and unrelated edits; use `workflow repair` only with recorded failure evidence and the existing budgets. Native model CLI generation still requires explicit host opt-in. Never weaken verification to make generated code pass.
7. Keep conversation excerpts, raw transport and project memory private. Use the current project's privacy guard before committing and publish only selected authorized files. Update project memory with actual evidence.

Respond in the user's chosen Arabic/English language. Foundation developer documents remain English. This plugin grants no permission to send messages, publish, alter another project or run arbitrary desktop tools. The optional browser companion has manual controls; its installation does not establish an autonomous model/browser bridge.
