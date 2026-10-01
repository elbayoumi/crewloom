# Review changed behavior

## Inputs

Project-local task, current source, installed role memory, upstream artifacts and the workflow handoff. Confirm output language, canonical project root, execution permissions and acceptance criteria before changing files.

## Procedure

1. Read the implementation and acceptance cases. Scope review to affected behavior and its interaction with existing components.
2. Use static tools as supporting evidence. Check rendered behavior, keyboard interaction, states, language direction and responsive layout where a renderer is available.
3. Report reproducible findings with severity, file/line, trigger, expected/actual behavior and verification evidence. Separate verified defects from observations.

## Deliverable

Review artifact with actionable findings, evidence, tested viewports/states and explicit unverified areas.

## Acceptance and stop conditions

Syntax parsing and static pattern checks cannot establish rendered quality. Do not request changes to intentional constructs without a concrete failing case.

## Handoff

Carry the workflow ID and canonical root, owning role, artifact paths and hashes, checks actually performed, unresolved questions, and next action. The next owner verifies upstream evidence before continuing. Shared role history is not project state.

## Memory closure

Update project-local completed work and roadmap with actual results. Record root causes and fixes in challenges and ideas separately. Preserve earlier attempts and do not repeat an unchanged failed operation beyond the workflow attempt limit.
