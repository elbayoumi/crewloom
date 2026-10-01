# Implement a bounded feature

## Inputs

Project-local task, current source, installed role memory, upstream artifacts and the workflow handoff. Confirm output language, canonical project root, execution permissions and acceptance criteria before changing files.

## Procedure

1. Read the approved requirements and architecture plus current source/tests. Bind one project root and preserve it across every command.
2. Implement the feature with input validation, authorization, explicit failure behavior and persistence semantics appropriate to this project.
3. Run actual project checks through command steps where possible. Report changed files, migrations/configuration, rollback and remaining work.

## Deliverable

Working source changes and an implementation report referencing the exact changed files and real command evidence.

## Acceptance and stop conditions

A success response without implementing the requested behavior is not completion. Do not create a parallel copy of an existing module or fabricate passing test output.

## Handoff

Carry the workflow ID and canonical root, owning role, artifact paths and hashes, checks actually performed, unresolved questions, and next action. The next owner verifies upstream evidence before continuing. Shared role history is not project state.

## Memory closure

Update project-local completed work and roadmap with actual results. Record root causes and fixes in challenges and ideas separately. Preserve earlier attempts and do not repeat an unchanged failed operation beyond the workflow attempt limit.
