# Self-Editing Mode

Arabic name: **التعديل الذاتي**.

Self-Editing Mode is Crewloom's named maintenance workflow for improving existing roles, tools and documentation from demonstrated failures or an explicit owner request. The existing `skill-improvement-engineer` role owns the repair procedure; `skill-performance-auditor` evaluates role retirement or replacement when that decision is needed.

## Activate the workflow

Ask your agent host to enter **Self-Editing Mode** or **التعديل الذاتي**, and specify the selected project, problem and intended result. Read [the role procedure](../.agents/skills/skill-improvement-engineer/references/PLAYBOOK.en.md) and [the constitution](../AGENTS.md). The name is a task instruction for your host, not a new CLI flag or background worker.

English task example:

> Enter Self-Editing Mode for this Crewloom checkout. Reproduce the reported failure, inspect relevant memory and the existing implementation, improve it in place, run the required checks, and record the actual result. Preserve unrelated changes and previous attempts. Keep project data inside its selected root.

Arabic task example:

> ادخل وضع التعديل الذاتي لهذا المشروع. أعد إنتاج المشكلة، واقرأ الذاكرة والكود الحالي المرتبطين بها، وعدّل التنفيذ الموجود، وشغّل الفحوص المطلوبة، وسجّل النتيجة الفعلية. حافظ على التعديلات غير المرتبطة وسجل المحاولات، ولا تستخدم ذاكرة أو ملفات مشروع آخر.

## Repair cycle

1. Bind one canonical project root. Read relevant architecture, completed work, challenges and ideas; inspect existing code and dependencies.
2. Define the observed failure, affected files, bounded change and acceptance evidence. Record previous attempts and a concrete repair hypothesis.
3. Edit the existing implementation in place. Preserve unrelated work, project memory and machine-readable identifiers.
4. Reproduce the original failure and run relevant checks. Crewloom repository changes must pass the commit gate; use isolated command steps for generated project code where suitable.
5. Record completed work, remaining backlog, root cause and useful ideas. Report actual artifacts, checks and unresolved limitations.

After two unsuccessful repairs for the same cause, retain the evidence, report the blocker and continue independent authorized work. Do not reset the budget by renaming a task or invent passing results.

## Scope and authority

The selected task determines what may be changed. Choosing this mode does not expand authority to other projects, external messages, purchases or publication. Existing task authorization remains valid. Host tools retain their own permission and sandbox boundaries; this workflow name does not create additional filesystem isolation.
