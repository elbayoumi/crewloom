# Model Context Protocol (MCP) Configuration Examples

Crewloom connects specialist agent roles, project context, and coordinated workflows to modern AI developer environments using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).

The Crewloom MCP server runs locally as a standard input/output (`stdio`) process bound to a specific project checkout, task reservation, and optional workflow plan. It does not run background daemons, expose network ports, or require external API keys.

For detailed architecture, capabilities, and tool contracts, see the [MCP Bridge Documentation](../../documentation/MCP_BRIDGE.md). For confidentiality boundaries, private layout conventions, and commit guards, see [Privacy Boundaries and Guardrails](../../documentation/PRIVACY.md).

---

## Fixture Directory

This directory contains tested, production-ready MCP configuration templates:

| Configuration File | Target Host / Purpose | Transport | Description |
|---|---|---|---|
| [`cursor.json`](cursor.json) | Cursor AI IDE | `stdio` | Connects Cursor Composer and chat agents to the Crewloom task bridge. |
| [`windsurf.json`](windsurf.json) | Windsurf Cascade IDE | `stdio` | Connects Codeium Windsurf Cascade to the Crewloom task bridge. |
| [`rea.json`](rea.json) | Reverse-Engineering Analyst | `stdio` | Reference fixture running `rea-agents@6.5.0` via `npx`. |
| [`crewloom-task.json`](crewloom-task.json) | Task Bridge Reference | `stdio` | Canonical task bridge configuration binding project, task, and workflow plan. |
| [`playwright-isolated.json`](playwright-isolated.json) | Isolated Browser Testing | `stdio` | Runs `@playwright/mcp@0.0.83` with local artifact routing in `.crewloom/private/browser`. |
| [`config.json`](config.json) | Generic Stdio Example | `stdio` | Minimal template illustrating schema structure and safe `${VAR}` environment placeholders. |

---

## IDE Setup Instructions

### 1. Cursor Setup

Cursor supports MCP configurations at both project and user levels.

#### Option A: Workspace Setup (Recommended)
1. In your project repository root, create the `.cursor` directory if it does not exist:
   ```bash
   mkdir -p .cursor
   ```
2. Copy `examples/mcp/cursor.json` to `.cursor/mcp.json`:
   ```bash
   cp examples/mcp/cursor.json .cursor/mcp.json
   ```
3. Open `.cursor/mcp.json` and update the argument placeholders with your canonical project settings:
   - `--project`: Absolute path to your project root (e.g. `/Users/username/workspace/my-project`). Symlinks are rejected.
   - `--project-id`: The registered project ID in `.crewloom/config.json`.
   - `--task-id`: Your active kebab-case task identifier (e.g. `feature-auth`).
   - `--plan`: (Optional) Path to your reviewed workflow plan file (e.g. `workflow.json`).
4. Reload Cursor window (`Cmd+Shift+P` / `Ctrl+Shift+P` -> `Developer: Reload Window`) to initialize the connection.

#### Option B: Global User Setup
Merge the `"crewloom"` server entry from `examples/mcp/cursor.json` into your global configuration file:
- **macOS / Linux**: `~/.cursor/mcp.json`
- **Windows**: `%USERPROFILE%\.cursor\mcp.json`

---

### 2. Windsurf Setup (Cascade)

Windsurf manages MCP servers centrally for the Cascade assistant.

#### Configuration Path
- **macOS / Linux**: `~/.codeium/windsurf/mcp_config.json`
- **Windows**: `%USERPROFILE%\.codeium\windsurf\mcp_config.json`
- **Windsurf VS Code Extension**: `~/.codeium/mcp_config.json`

#### Setup Walkthrough
1. Open Windsurf.
2. Open the **Cascade** panel (side toolbar).
3. Click the **Hammer / MCP icon** in the Cascade toolbar and select **"View raw config (JSON)"**, or open `~/.codeium/windsurf/mcp_config.json` in your editor.
4. Merge the `"crewloom"` entry from `examples/mcp/windsurf.json` into the top-level `"mcpServers"` object:
   ```json
   {
     "mcpServers": {
       "crewloom": {
         "command": "crewloom",
         "transport": "stdio",
         "args": [
           "mcp",
           "--project",
           "/absolute/path/to/project",
           "--project-id",
           "example-project",
           "--task-id",
           "feature-task",
           "--plan",
           "workflow.json"
         ],
         "env": {}
       }
     }
   }
   ```
5. Replace `/absolute/path/to/project`, `example-project`, `feature-task`, and `workflow.json` with your verified project parameters.
6. Save the file.
7. Click the **"Refresh"** button (circular reload icon) in the Cascade MCP panel. Cascade will perform the handshake and display discovered tools.

---

## Three-Tier Verification Model

Crewloom enforces a strict three-tier verification doctrine:

> *A valid configuration proves structure; a handshake proves reachability; a bounded tool call proves effectiveness. Never collapse these three claims.*

```
+-------------------------------------------------------------------+
| Tier 1: Structural & Secret Validation                            |
| Command: python3 scripts/crewloom.py run mcp-config -- --config <f> |
| Validates top-level mcpServers, known transport, placeholder env. |
+---------------------------------+---------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
| Tier 2: Syntax & Parsing Integrity                                |
| Command: python3 -c "import json; json.load(open('<f>'))"         |
| Ensures strict 2-space indented, well-formed JSON.                |
+---------------------------------+---------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
| Tier 3: Runtime Handshake & Live Tool Invocation                 |
| Subprocess initialization, tool discovery, bounded execution.      |
| Verifies read-only tools: crewloom_status, crewloom_context.      |
+-----------------------------------+-------------------------------+
```

### Tier 1: Structural & Secret Validation (Automated CLI)
Verify that your configuration satisfies the MCP schema and credential safety checks:
```bash
python3 scripts/crewloom.py run mcp-config -- --config examples/mcp/cursor.json
python3 scripts/crewloom.py run mcp-config -- --config examples/mcp/windsurf.json
python3 scripts/crewloom.py run mcp-config -- --config examples/mcp/rea.json
python3 scripts/crewloom.py run mcp-config -- --config examples/mcp/crewloom-task.json
python3 scripts/crewloom.py run mcp-config -- --config examples/mcp/playwright-isolated.json
python3 scripts/crewloom.py run mcp-config -- --config examples/mcp/config.json
```
Each command must output `PASS mcp config (N server(s))` with exit code `0`.

### Tier 2: Syntax & Parsing Integrity
Confirm strict JSON parsing without syntax errors or trailing commas:
```bash
python3 -c "import json, glob; [json.load(open(f, encoding='utf-8')) for f in glob.glob('examples/mcp/*.json')]; print('All MCP templates syntax-valid')"
```

### Tier 3: Runtime Handshake & Tool Discovery
When Cursor or Windsurf connects to the server over `stdio`:
1. **Initialize Handshake**: The host sends `initialize` with client capabilities; the server responds with server info and protocol version.
2. **Initialized Notification**: The host sends `notifications/initialized`.
3. **Tool Discovery (`tools/list`)**: The host requests available tools. By default, the bridge exposes safe read-only tools:
   - `crewloom_status`: Read task progress and binding state.
   - `crewloom_context`: Read frozen task context.
   - `crewloom_questions`: Inspect pending source-linked questions.
4. **Bounded Tool Call**: The host executes `crewloom_status` to verify end-to-end communication without modifying project state.

Write and execution tools (`crewloom_answer`, `crewloom_import_reply`, `crewloom_verify`) require explicit launch flags (`--allow-import`, `--allow-verify`) and a reviewed workflow plan.

To run the automated Tier 3 suite:
```bash
python3 -m unittest discover -s scripts -p test_mcp_bridge.py
```

---

## Security & Secret Guardrails

1. **Zero Secret Embedding**: MCP configuration files must **never** contain plaintext API keys, access tokens, private keys, or passwords.
2. **Regex Enforcement**: The validator checks all values against known token patterns:
   - OpenAI keys (`sk-...`)
   - Groq keys (`gsk_...`)
   - GitHub tokens (`ghp_...`)
   - Slack tokens (`xox...`)
   - AWS access keys (`AKIA...`)
   - Private key blocks (`-----BEGIN...`)
   - JWT credentials (`eyJ...`)
   Any matching value triggers immediate validator failure (exit code 2).
3. **Environment Placeholder Syntax**: If a third-party MCP server requires credentials, pass them via environment variable references formatted strictly as `${VARIABLE_NAME}` (as demonstrated in `examples/mcp/config.json`).
4. **Canonical Path Requirement**: The `--project` argument requires an absolute, canonical directory path. Paths containing symlinks or unresolved parent traversals (`..`) are refused at launch.
5. **Private State Isolation**: All temporary task replies, browser snapshots, and candidate publications remain quarantined under `.crewloom/private/`.

---

## Clean Removal & Teardown

To disconnect Crewloom MCP integration cleanly:
1. **Remove Server Entry**: Delete the `"crewloom"` entry from `.cursor/mcp.json` or `~/.codeium/windsurf/mcp_config.json`.
2. **Terminate Processes**: Save the configuration file and restart or reload the IDE. Any child `crewloom mcp` subprocess will terminate automatically when its `stdio` stream closes.
3. **Purge Temporary Data**: Clear any unneeded transient replies or session tokens from `.crewloom/private/agent-replies/`.

---

## Related Documentation

- [Project Task MCP Bridge Specification](../../documentation/MCP_BRIDGE.md) — Comprehensive technical guide for stdio bridge protocol, tool signatures, and permissions.
- [Private Customization and Publication Guardrails](../../documentation/PRIVACY.md) — Privacy conventions, commit guard rules, and secret boundaries.
