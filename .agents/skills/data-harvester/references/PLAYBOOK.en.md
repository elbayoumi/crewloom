# Data Harvester

This English procedure adapts the role’s [source playbook](PLAYBOOK.ar.md) for reusable project work. Project policies and account access must be supplied; upstream agency paths are not runtime defaults.

## Inputs and scope

Source URLs or discovery query, required fields, output schema and collection scope. Read this project’s constitution and the role’s architecture, completed work, challenges and ideas before acting. Bind one canonical project root and confirm the task’s intended output language.

## Procedure

1. Discover authoritative sources, then choose the lowest-cost suitable extraction method. Use static extraction first and a browser only where rendering or interaction is required.
2. Collect records with source URL, capture date and field provenance. Preserve missing fields and report blocked pages or partial results instead of filling guesses.
3. Validate schema, deduplicate records and save the dataset inside the selected project. Connect every reported number to an identifiable source record.

## Deliverable and acceptance

JSONL/CSV dataset, provenance and coverage/error report. Follow source access rules and do not treat a blocked page as permission to bypass access controls; source-specific scripts may need project-supplied dependencies.

## Dependencies and failure handling

Use the [public tool catalog](../../../../documentation/TOOLS.md) to establish which checks are bundled. Confirm external applications, policies and accounts before execution. Record missing facts and blocked checks explicitly. Preserve earlier attempts; after two unchanged failures, report the cause and continue only independent authorized work.

## Handoff and memory closure

Carry project root, owning role, artifact paths, source facts, checks actually performed and unresolved questions. The next owner verifies upstream artifacts. Update project-local completed work and backlog, record root causes and useful ideas, and keep client history and credentials out of public library memory.
