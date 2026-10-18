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

Arabic text works in the same commands. A statement must preserve its exact quote. A paraphrase or inferred preference requires `--kind assumption`. Re-recording the same user/key/task/kind supersedes the previous record of that kind and retains its history. Quoted statements and assumptions use separate revision streams: a new hypothesis never erases a quoted statement. Task-specific records override project-wide records within the same kind. Both selected kinds retain their source/freshness checks. Historical cross-kind supersedes links are preserved, but selection treats the kinds independently. Project-wide records require no active task reservation; finish or cancel the current task before recording them without `--task-id`.

A contract keeps the goal, constraints, acceptance and optional repeated `--question` fields. Unresolved questions block selection and project entry. Resolve them by recording a revised contract; previous contracts remain in history. Manual contract questions are supplied explicitly. Optional prompt capture also detects literal unresolved placeholders and conflicting language cues; it does not detect every ambiguity in natural language.

## Isolation, freshness and limits

Selection requires an explicit task contract, which determines the user. It never selects another user's memory, another task's specific records, or another project/checkout's store. Rebinding or moving a checkout does not silently migrate this store; review and re-record sources under the new binding. Shared role memory receives reusable lessons only.

Changed source hashes, interpretation or selected memory invalidate reuse of the frozen context. Required selected user context counts against the existing context byte budget; exceeding the budget fails instead of silently dropping a constraint. The store permits 128 memory revisions, 128 task contracts and 256 KiB total; selected context is limited to 16 KiB. History is never automatically deleted. CLI rejection returns exit 2. Mutations use the existing project lock and ownership checks.

## What the evidence means

An exact quote and hash establish provenance in an operator-recorded source file. They do **not** authenticate the speaker, prove a statement true, confirm a goal interpretation, confer tool permissions or prove task completion. Memory is project input data, never executable instructions or a replacement for the constitution. Assumptions stay labelled in the model prompt. Existing executor-verified lessons retain their separate evidence rules.

Projects without a contract continue using the existing context workflow. Recording defaults to explicit operation. Per-task capture can preserve native user-prompt events after opt-in; it does not capture all host history or establish a general improvement in model task quality. The regression suite verifies source integrity, corrections, project/user isolation, stale-context rejection and actual prompt delivery; it does not establish a general reduction in hallucinations.

## Private sources and commits

Prefer `.crewloom/private/inputs/message.txt` for source excerpts. New records also copy external project sources privately, register the original path as non-publishable and enable the chained commit guard. See [privacy and publication](PRIVACY.md). Run `crewloom privacy init` to register older recorded sources; source copies do not erase existing files or Git history.

## Optional native prompt capture

Enable capture only for an explicit user and task, with an operator-defined goal and acceptance:

```sh
crewloom user-context configure-capture --project /absolute/project --task-id native-task \
  --user-id owner --goal 'Fix the selected local defect' --acceptance 'Affected checks pass'
```

Use the task ID returned by the native `SessionStart` preparation. Codex and Claude supply their literal `UserPromptSubmit.prompt`. The OpenCode adapter carries only non-synthetic, non-ignored text parts from the prepared user message to its system-transform callback. A host that supplies no text is refused when capture is enabled; no transcript or identity is invented. This is source provenance, not speaker authentication. Native installation identity, version, owned adapter entries and scope are validated before capture.

Capture stores each bounded UTF-8 message privately, preserves exact chunks as statements and labels the configured goal as an interpretation. It does not execute the message or grant permissions. Identical replay is idempotent; changed text under the same native turn ID is refused. A task permits eight captured turns, 32 questions and the existing context store budgets. Overflow preserves history and refuses a new write. Consolidation is an explicit operator operation, not automatic deletion.

Use `crewloom user-context disable-capture --project /absolute/project --task-id native-task` to stop future capture. Existing sources, history and open questions remain preserved; disabling capture does not resolve a question or authorize execution.

Literal `[TBD]`, `[TODO]`, `[?]` and contradictory Arabic/English response-language cues produce source-linked questions. Unresolved questions remain open across later prompts and stop native project tools as well as context selection. They are heuristics, not comprehensive understanding. Questions can be read without claiming successful context delivery:

```sh
crewloom user-context questions --project /absolute/project --task-id native-task
crewloom user-context answer --project /absolute/project --task-id native-task \
  --question-id q-example --source .crewloom/private/inputs/chat-native-task/TURN.txt \
  --quote 'Exact answer from a later captured user message.'
```

Use the actual returned question ID and source path. A reply must quote a later captured source in this exact task; same-message answers, invented quotes and replay are refused. Capture questions cannot be erased by rewriting a task contract. Answers remain interpretations backed by source text, never tool authority. Strict native tool guards keep their existing unknown/MCP denial; an operator resolves the question through the CLI or a separately authorized MCP connection before the next native prompt.

The task MCP server always exposes `crewloom_questions`; `crewloom_answer` appears only with explicit `--allow-context-update`. Native capture is independent of that flag. Hosts without a native adapter may explicitly import a private message file using `capture --host HOST --session-id SESSION --turn-id TURN --source .crewloom/private/inputs/message.txt`; that input is operator supplied. A configured task does not authorize capture for another task or user. Private event logs retain capture counts/status, not message text.

## Bounded quality collection

The existing bilingual collector accepts repeated `--case-id` values to preselect a pilot before any model call. Omitted selection runs all nine cases. Every report states selected and available case IDs and whether coverage is complete; failed/blocked attempts remain counted. Example:

```sh
crewloom evaluate-bilingual --understanding --project /absolute/project \
  --output .crewloom/private/evaluations/new-study --host codex --model codex=MODEL \
  --case-id latest-correction --case-id deployment-needs-target
```

The requested model is explicit; a host that does not report its actual backend identity cannot establish that identity. A small synthetic pilot does not rank model intelligence, agency delivery or billing. Preserve unavailable models as failures rather than silently substituting another model within the same run.

## Coordinator worktree delivery

Before generation, the coordinator transfers only the selected workflow's contract and current user records into its distinct checkout of the same repository and project. Source bytes remain private and are hash checked; unrelated tasks are excluded. A private receipt binds parent and child identities and both selections. The coordinator rechecks it after execution and during resumption. A changed parent correction, modified child source or missing receipt refuses reuse and requires a fresh batch. Existing child context is never silently overwritten. This is context delivery, not permission or proof of speaker identity.
