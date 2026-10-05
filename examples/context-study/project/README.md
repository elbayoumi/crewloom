# Context-study source fixture

A small synthetic Python project used as the *candidate's* side of the
controlled context study in `documentation/CONTEXT_STUDY.md`. It exists so a host
receives the same real integration dependencies in both conditions of a trial,
and so the study measures a changed implementation rather than an empty artifact.

Nothing in this tree is an example of production Crewloom code, and no file here
is imported by the toolkit at runtime.

## Modules

| Module | Role in the study |
| --- | --- |
| `src/money.py` | REQUIRED helper for the invoice task: exact decimal parsing, one group rounding, fixed formatting. |
| `src/scheduling.py` | REQUIRED helper for the scheduler task: identifier, priority and dependency validation. |
| `src/pathutil.py` | REQUIRED helper for the path task: relative-path component rules, link and hardlink detection. |
| `src/invoicing.py` | Relevant, not required: stored invoice records that already reuse the money helpers. |
| `src/workqueue.py` | Relevant, not required: the FIFO run queue a scheduler change would touch. |
| `src/project.py` | Relevant, not required: declared layout that a path resolver change would touch. |
| `src/telemetry.py` | Unrelated: worker counters. |
| `src/reporting.py` | Unrelated: CSV and Markdown rendering for the export job. |
| `src/notifications.py` | Unrelated: operator message text. |

The three tasks each produce exactly one new file that does not exist here:
`src/ledger.py`, `src/scheduler.py` and `src/paths.py`.

## What is deliberately absent

The held-out acceptance cases, their expected values and the grader never appear
in this tree or in any study prompt. They live in the frozen supervisor contract
`.crewloom/production-foundation/STUDY_TASK_CONTRACTS.json` and are loaded by the
trusted controller only.

## Limitations

The fixture is small on purpose. Three small synthetic tasks over nine short
modules support a controlled paired comparison inside this repository; they do not
support any claim about model quality, provider superiority or savings outside it.