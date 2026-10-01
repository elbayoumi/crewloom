# Verify acceptance independently

## Inputs

Project-local task, current source, installed role memory, upstream artifacts and the workflow handoff. Confirm output language, canonical project root, execution permissions and acceptance criteria before changing files.

## Procedure

1. Read the requirements and changed source, then select tests for observable behavior rather than mirroring implementation details.
2. Cover valid and invalid inputs, state transitions, authorization boundaries, regressions and the selected Arabic/English behavior.
3. Run the real test commands. Record argv, environment/image, exit codes, revision or source hashes, outputs and unresolved failures. Verify evidence again before handoff.

## Deliverable

Verification JSON or report with exact checks, outcomes, artifact hashes, failures and scope limitations.

## Acceptance and stop conditions

A zero exit from an empty/no-op command is not acceptance. Reviewer identity and evidence truth require external review; hashes prove file consistency only.

## Handoff

Carry the workflow ID and canonical root, owning role, artifact paths and hashes, checks actually performed, unresolved questions, and next action. The next owner verifies upstream evidence before continuing. Shared role history is not project state.

## Memory closure

Update project-local completed work and roadmap with actual results. Record root causes and fixes in challenges and ideas separately. Preserve earlier attempts and do not repeat an unchanged failed operation beyond the workflow attempt limit.
