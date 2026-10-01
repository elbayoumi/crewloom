# Mcp Integration Builder

This English procedure adapts the role’s [source playbook](PLAYBOOK.ar.md) for reusable project work. Project policies and account access must be supplied; upstream agency paths are not runtime defaults.

## Inputs and scope

Required tool capabilities, selected host configuration, official server docs and credential variable names. Read this project’s constitution and the role’s architecture, completed work, challenges and ideas before acting. Bind one canonical project root and confirm the task’s intended output language.

## Procedure

1. Choose an existing server when it covers the need; document why a custom server is necessary otherwise. Check actual host transport/version compatibility.
2. Validate the config with the bundled MCP-config tool. Use environment placeholders and wire only the selected server with authorized credentials.
3. For a custom server define tool inputs, outputs and errors explicitly. Start it and exercise representative tool calls before claiming integration completion.

## Deliverable and acceptance

Validated config, exact startup command and live tool evidence. A valid JSON configuration does not prove server connectivity or model tool discovery; never place real secrets in config or role files.

## Dependencies and failure handling

Use the [public tool catalog](../../../../documentation/TOOLS.md) to establish which checks are bundled. Confirm external applications, policies and accounts before execution. Record missing facts and blocked checks explicitly. Preserve earlier attempts; after two unchanged failures, report the cause and continue only independent authorized work.

## Handoff and memory closure

Carry project root, owning role, artifact paths, source facts, checks actually performed and unresolved questions. The next owner verifies upstream artifacts. Update project-local completed work and backlog, record root causes and useful ideas, and keep client history and credentials out of public library memory.
