# MCP configuration structure

This example is a **structure** fixture, not a running integration. It shows the shape the bundled checker accepts and nothing more.

```bash
crewloom run mcp-config -- --config examples/mcp/config.json
```

The checker confirms a top-level `mcpServers` object, a `command` per server, a known `transport`, and an `env` object whose values are placeholders rather than embedded credentials. It does not start `server.py`, resolve the command on `PATH`, or perform an MCP handshake.

## Wire a real server

1. Copy the structure and replace the placeholder values with your own server's command, arguments, transport and environment variable names.
2. Keep secrets in environment placeholders such as `${SERVICE_TOKEN}` and supply the value from the environment. A value that looks like a real token fails the checker.
3. Register the entry in your agent host's own MCP configuration. Crewloom does not ship an MCP client.
4. Run the server, complete `initialize`, then `notifications/initialized`, then `tools/list`, then one bounded `tools/call`, and record what actually happened.
5. Treat a passing check, a completed handshake and a produced artifact as three separate claims.

Read [the application MCP guide](../../documentation/MCP.md) for the full procedure, for driving a running application through a bridge, and for removal.

## Removal

Remove the entry from the host configuration, stop the server process, and delete local configuration and token files. Revoke any credential that was issued elsewhere separately; removing a client entry does not revoke it.