# Toolbox Integration Steward

This English procedure adapts the role’s [source playbook](PLAYBOOK.ar.md) for reusable project work. Project policies and account access must be supplied; upstream agency paths are not runtime defaults.

## Inputs and scope

Existing script/service, registry, CLI help, owning role and intended UI execution contract. Read this project’s constitution and the role’s architecture, completed work, challenges and ideas before acting. Bind one canonical project root and confirm the task’s intended output language.

## Procedure

1. Find the existing implementation and confirm its actual inputs, outputs, dependencies and effects. Improve it in place where suitable.
2. Write a complete registry/catalog contract and choose bounded direct execution only when the required scope and permissions are enforceable; otherwise provide exact manual setup.
3. Run an actual sample, synchronize the available UI and inspect the tool card/results. Report which tools are runnable and which need manual credentials/setup.

## Deliverable and acceptance

Usable tool entry with tested command and dependency/effect notes. Do not invent a runnable UI button for unsupported browser, secret-dependent or production operations.

## Dependencies and failure handling

Use the [public tool catalog](../../../../documentation/TOOLS.md) to establish which checks are bundled. Confirm external applications, policies and accounts before execution. Record missing facts and blocked checks explicitly. Preserve earlier attempts; after two unchanged failures, report the cause and continue only independent authorized work.

## Handoff and memory closure

Carry project root, owning role, artifact paths, source facts, checks actually performed and unresolved questions. The next owner verifies upstream artifacts. Update project-local completed work and backlog, record root causes and useful ideas, and keep client history and credentials out of public library memory.
