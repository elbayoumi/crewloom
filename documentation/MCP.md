# Application MCP servers

Crewloom does not ship an MCP client. Your agent host does: Claude Desktop, Claude Code, opencode, Cursor, VS Code, and other MCP hosts start a configured server as a child process and expose its tools to the model. Crewloom's contribution is the surrounding contract — which role owns the integration, what a valid configuration proves, how a bounded tool call is exercised and recorded, and where a server's own filesystem authority stops.

## Choose the path

| Need | Path |
| --- | --- |
| Reason about an app's MCP server from an agent task | Use the host's own MCP client; register the server in that host's configuration |
| Prove a configuration is structurally valid | `crewloom run mcp-config -- --config <config.json>` |
| Record the integration as reviewed project work | [the MCP integration plan](../workflows/mcp-integration.json) with the `mcp-integration-builder` role |
| Execute a server command inside Docker isolation | Declare it as a `command` step in a project plan; see [execution](EXECUTION.md) |

A local configuration file is machine state, not a repository artifact. Keep absolute paths, tokens, roots and account identifiers out of version control; store them under the project's private area described in [privacy](PRIVACY.md).

## Configure the server

A client configuration names each server with a command, its arguments, and a transport. The bundled checker validates that structure and rejects embedded credential literals:

```bash
crewloom run mcp-config -- --config path/to/config.json
```

```json
{
  "mcpServers": {
    "example": {
      "command": "python3",
      "args": ["server.py"],
      "transport": "stdio",
      "env": {"SERVICE_TOKEN": "${SERVICE_TOKEN}"}
    }
  }
}
```

Use environment placeholders for secrets; the checker fails a config whose `env` values look like real tokens. A `PATH`-style structure check is not connectivity: the command may not exist, the package may be missing, or the server may reject the handshake. Report those as unknown until a real handshake runs.

## Exercise discovery and one bounded call

Follow the server's own protocol version rather than guessing. For a stdio JSON-RPC server the order is:

1. `initialize` with the protocol version and client capabilities the server requires.
2. `notifications/initialized`.
3. `tools/list` — record the tool names and their input schemas.
4. One `tools/call` with the smallest bounded input that proves behaviour, such as creating a small document or listing an empty directory.

Record what actually happened: server name and version, tool count, the exact call, and its result or error. A tool list proves discovery only. It does not prove that a write is scoped, that an export lands where you expect, or that a GUI bridge is attached.

## Drive a running application

Some applications run headless while others expose a control port so an MCP server can attach to the live window. When the server documents a bridge mode, start the application with its control address and credential first, then start the MCP server pointed at that address:

- a control token is generated locally and written to a file the application and the MCP server both read;
- the MCP server runs with `--bridge host:port` so calls reach the live application instead of a private headless session;
- an automation read root and write root bound which files the server may touch.

Keep the token out of arguments, logs and version control. When a bridged call reports that an operation needs a headless session, that is a real boundary: export, index selection and format selection belong to the headless path, and a bridged call may only be able to return a window screenshot.

## Prove scope before claiming success

A completed integration states all three facts separately:

- **Configured** — the configuration validates.
- **Reachable** — the handshake completed and `tools/list` returned the documented tools.
- **Effective** — a bounded call produced the expected artifact, and the artifact was inspected at its intended size.

Never collapse these into one claim. Role instructions cannot grant a server credentials, publish to a platform, or widen its own filesystem authority; those require explicit operator authorization in the task.

## Remove an integration

Stop the server process, remove the entry from the host configuration, and delete the local token file and any private configuration. Removing a client entry does not revoke a credential that was issued elsewhere; rotate or revoke that credential separately when it was shared.