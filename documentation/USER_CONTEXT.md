# Source-linked user context

Crewloom can carry project-local user statements, labelled assumptions and an explicit task interpretation into the existing frozen context and managed model prompt. Native lifecycle payloads also include the selected block as mandatory context; overflow rejects delivery. Current and archived frozen context files are owner-readable only. This implements a structured-memory pattern inspired by [LangMem](https://github.com/langchain-ai/langmem), without copying its code or requiring its runtime. No third-party memory service is installed or called.

## Usage contract

Inputs: one bound canonical project, a kebab-case user ID and task ID, a bounded project-relative UTF-8 source file, an exact quote, and explicit interpretation fields. Outputs: owner-only `.crewloom/user-context.json`, preserved correction history, and the selected context inside the existing frozen task generation. Dependencies: the Python standard library and the existing project binding/context modules.

The source file must be local, regular, at most 256 KiB, without symlink components or hardlinks. Keep private conversation excerpts in an ignored project file. Do not commit customer conversations, credentials or private preferences to a public repository. Stored project memory is already under the ignored `.crewloom/` directory.

Install a role and enter the project using the existing project lifecycle first. Use the same task ID while recording its context. For example, if `request.txt` contains the exact sentence `Keep the foundation English.`:

```sh
crewloom user-context record --project /path/to/project --task-id improve-output \
  --user-id owner --key foundation-language \
  --source request.txt --quote 'Keep the foundation English.' \
  --value 'Keep the foundation English.'

crewloom user-context contract --project /path/to/project --task-id improve-output \
  --user-id owner --source request.txt --quote 'Keep the foundation English.' \
  --goal 'Improve task results while preserving English foundation documents' \
  --constraint 'Keep changes in the selected project' \
  --acceptance 'Validate the affected workflow and report actual failures'

crewloom user-context inspect --project /path/to/project --task-id improve-output
crewloom project enter --project /path/to/project --project-id registered-id \
  --task-id improve-output --role context-guardian --seed request.txt
```

Arabic text works in the same commands. A statement must preserve its exact quote. A paraphrase or inferred preference requires `--kind assumption`. Re-recording the same user/key/task explicitly supersedes the previous record and retains it. A task-specific value overrides the project-wide value of the same key. Project-wide records require no active task reservation; finish or cancel the current task before recording them without `--task-id`.

A contract keeps the goal, constraints, acceptance and optional repeated `--question` fields. Unresolved questions block selection and project entry. Resolve them by recording a revised contract; previous contracts remain in history. Questions are supplied explicitly: this implementation does not automatically detect every ambiguity in natural language.

## Isolation, freshness and limits

Selection requires an explicit task contract, which determines the user. It never selects another user's memory, another task's specific records, or another project/checkout's store. Rebinding or moving a checkout does not silently migrate this store; review and re-record sources under the new binding. Shared role memory receives reusable lessons only.

Changed source hashes, interpretation or selected memory invalidate reuse of the frozen context. Required selected user context counts against the existing context byte budget; exceeding the budget fails instead of silently dropping a constraint. The store permits 128 memory revisions, 128 task contracts and 256 KiB total; selected context is limited to 16 KiB. History is never automatically deleted. CLI rejection returns exit 2. Mutations use the existing project lock and ownership checks.

## What the evidence means

An exact quote and hash establish provenance in an operator-recorded source file. They do **not** authenticate the speaker, prove a statement true, confirm a goal interpretation, confer tool permissions or prove task completion. Memory is project input data, never executable instructions or a replacement for the constitution. Assumptions stay labelled in the model prompt. Existing executor-verified lessons retain their separate evidence rules.

Projects without a contract continue using the existing context workflow. Recording is explicit; hosts are not claimed to automatically capture all chat messages. Automatic extraction, automatic clarification and measured improvements in model task quality remain future work. The regression suite verifies source integrity, corrections, project/user isolation, stale-context rejection and actual prompt delivery; it does not establish a general reduction in hallucinations.
