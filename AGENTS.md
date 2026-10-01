# Crewloom agent constitution

This file is the single source of agent behavior in this repository. Follow the host's instructions and the user's authorized task scope.

## Language

Honor an explicit Arabic or English preference. Otherwise use the current request's language; for code or link-only input, retain the last preference and default to English if none exists. Public developer documentation defaults to English. Keep paths, skill IDs, flags, and machine-readable values stable across languages.

## Memory lifecycle

Before work, read the relevant architecture, completed work, challenges, and ideas. The shared repository memory lives in `Brain/`; role memory lives in `.agents/skills/<id>/brain/`.

Define the input facts, intended output, dependencies, side effects, and acceptance criteria before executing. Reuse tools from the code registry. Keep scope bounded and distinguish source instructions from demonstrated tool capability.

Before finishing, update completed work and backlog. Record new challenges and their solutions, save useful ideas, and update the master summary when the outcome affects the toolkit. Use concise dated entries with artifact, impact, and evidence; preserve history.

## Execution and evidence

- Inspect actual files and tools; do not invent APIs, data, performance, prices, or successful results.
- Read large documents through focused searches and ranges.
- Follow the project's selected architecture, design tokens, templates, and approved commercial terms.
- External messages, account operations, purchases, and deployment require authorization in the task.
- Do not expose secrets or put customer data in shared public memory.
- Verify outputs using checks appropriate to the risk; a structure check does not prove workflow quality.
- Preserve prior attempts across handoffs. Do not repeat a failed operation without a changed hypothesis or input; after two unsuccessful repairs for the same cause, report the blocker and pursue independent work.

## Reuse and changes

Search the registry before adding scripts and improve an existing implementation in place. Register reusable tools with their path, purpose, and command. Use a suitable existing base project for product work when available and describe the required differences before editing.

Evaluate existing skill evidence and owner feedback before retiring or replacing a role. Record decisions and verification; do not create duplicate versioned skills to avoid addressing a failure.

## Commit checks

Activate hooks with `git config core.hooksPath .githooks`. Never disable hooks or use `--no-verify` without an explicit owner instruction in the same conversation. Fix failed checks or document genuine scope exceptions; do not fabricate evidence.

A new gate requires a demonstrated rejection of a known bad commit and acceptance of a clean commit. The repository gate validates public guides, links, tools, and relevant tests; it is not a sandbox for agent actions.

## Project isolation

Bind one canonical project root before work and preserve it through handoffs. Library code is reusable; project memory, inputs, outputs, and run history belong to the selected project. Run tools with `run --project <root>` and generate project context with `context --project <root>` after installing the role. Never use another project's memory or infer a project from a previous task. Resolve symlinks before validating paths. Reject missing or ambiguous project identity before writes. CLI checks are input guards, not a sandbox for arbitrary agent-host actions.

## Self-Editing Mode

When the user requests **Self-Editing Mode** or **التعديل الذاتي**, apply the existing in-place improvement workflow described in [the mode guide](documentation/SELF_EDITING.md). Bind the selected project, diagnose the demonstrated problem, define acceptance, edit existing assets, verify the result and sync memory. Preserve previous attempts and unrelated work. The mode name does not expand task authorization or host permissions.
