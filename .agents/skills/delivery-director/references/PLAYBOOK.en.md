# Deliver verified work

## Inputs

Project-local task, current source, installed role memory, upstream artifacts and the workflow handoff. Confirm output language, canonical project root, execution permissions and acceptance criteria before changing files.

## Procedure

1. Read requirements, implementation, review and current QA evidence. Confirm that evidence still matches the files being delivered.
2. Provide setup/run steps, acceptance results, limitations, migrations, rollback and ownership of remaining work.
3. Obtain required project authorization for publication or deployment. Preserve workflow ID/root and record project-specific closure in local memory.

## Deliverable

Delivery artifact pointing to current source and verification evidence, usage instructions, limitations and the next owner.

## Acceptance and stop conditions

Do not claim production deployment from local tests. Do not close work with unresolved acceptance failures or stale source fingerprints.

## Handoff

Carry the workflow ID and canonical root, owning role, artifact paths and hashes, checks actually performed, unresolved questions, and next action. The next owner verifies upstream evidence before continuing. Shared role history is not project state.

## Memory closure

Update project-local completed work and roadmap with actual results. Record root causes and fixes in challenges and ideas separately. Preserve earlier attempts and do not repeat an unchanged failed operation beyond the workflow attempt limit.
