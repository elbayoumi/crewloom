# Requirements and acceptance

## Inputs

Project-local task, current source, installed role memory, upstream artifacts and the workflow handoff. Confirm output language, canonical project root, execution permissions and acceptance criteria before changing files.

## Procedure

1. Read the task, existing behavior and project-local decisions. Separate confirmed facts from unresolved questions.
2. Describe the trigger, user, expected output, failure cases and authorized scope. Link each requirement to observable acceptance evidence.
3. Inspect existing implementation and tests before requesting another component. Record project paths and the next owner in the handoff.

## Deliverable

Requirements artifact with acceptance cases, source references, unresolved decisions and an explicit project root.

## Acceptance and stop conditions

Do not mark an unknown requirement as confirmed. Stop implementation where missing decisions change behavior, permissions or data contracts.

## Handoff

Carry the workflow ID and canonical root, owning role, artifact paths and hashes, checks actually performed, unresolved questions, and next action. The next owner verifies upstream evidence before continuing. Shared role history is not project state.

## Memory closure

Update project-local completed work and roadmap with actual results. Record root causes and fixes in challenges and ideas separately. Preserve earlier attempts and do not repeat an unchanged failed operation beyond the workflow attempt limit.
