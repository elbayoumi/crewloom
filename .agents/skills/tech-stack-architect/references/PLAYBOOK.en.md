# Architecture and reuse

## Inputs

Project-local task, current source, installed role memory, upstream artifacts and the workflow handoff. Confirm output language, canonical project root, execution permissions and acceptance criteria before changing files.

## Procedure

1. Inspect the existing stack, dependencies, persistence and deployment model. Prefer the current architecture unless a measured constraint requires change.
2. Describe the delta in pages, data, integrations, branding and permissions. Map proposed changes to existing files and ownership.
3. Record dependency/runtime requirements for the offline execution image, migrations, rollback and verification commands.

## Deliverable

Architecture artifact with decisions, alternatives, selected project paths, reuse analysis and acceptance checks.

## Acceptance and stop conditions

Do not present an unimplemented integration as an existing capability. Missing image dependencies must fail readiness rather than trigger a local execution fallback.

## Handoff

Carry the workflow ID and canonical root, owning role, artifact paths and hashes, checks actually performed, unresolved questions, and next action. The next owner verifies upstream evidence before continuing. Shared role history is not project state.

## Memory closure

Update project-local completed work and roadmap with actual results. Record root causes and fixes in challenges and ideas separately. Preserve earlier attempts and do not repeat an unchanged failed operation beyond the workflow attempt limit.
