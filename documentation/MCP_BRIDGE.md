# Project task MCP bridge

Crewloom exposes project context and workflow packets through the official Python MCP SDK. The server is a local stdio process with one project, checkout, task and optional plan fixed at launch. It does not generate model replies or provide desktop-control tools. The core CLI still runs without dependencies; the optional bridge requires Python 3.11+.

## Install and bind

```bash
python3 -m pip install 'crewloom[mcp]'
crewloom project setup --project /absolute/project --project-id example-project
crewloom install --host agents --target /absolute/project --skill fullstack-mvp-engineer
crewloom project enter --project /absolute/project --project-id example-project --task-id feature-task --role fullstack-mvp-engineer --seed contract.txt
```

Supply an existing project and real task inputs. For workflow packets, the selected plan must have the same ID as the task. Start it through `crewloom workflow run --project /absolute/project --plan workflow.json`; task steps pause for an agent response. The bridge accepts task/command plans and refuses model steps. Tool arguments cannot select an alternative project, plan or command.

## Connect Codex

Use a dedicated server name for each project/task. This command creates a read-only connection:

```bash
codex mcp add crewloom-example-task -- crewloom mcp --project /absolute/project --project-id example-project --task-id feature-task --plan workflow.json
```

Codex can also use a project-scoped `.codex/config.toml`. See the [official OpenAI MCP configuration guide](https://developers.openai.com/codex/mcp). After changing a connection, restart the host connection. Crewloom cannot inject tools into an already-running chat.

An equivalent client JSON template is in [the example config](../examples/mcp/crewloom-task.json). Replace all project/task placeholders before launch, then validate it with `crewloom run mcp-config -- --config examples/mcp/crewloom-task.json`. The bridge needs no provider credentials or HTTP listener.

## Tools and permissions

| Tool | Behavior |
| --- | --- |
| `crewloom_status` | Read the selected binding, task progress and enabled capabilities |
| `crewloom_context` | Read the task's frozen context; missing, foreign or stale context is refused |
| `crewloom_questions` | Read source-linked capture status and questions even when context is blocked |
| `crewloom_answer` | Available only with `--allow-context-update`; resolve one question against a later captured exact quote |
| `crewloom_task_packet` | Available with `--plan`; read the next awaiting task's prompt, response schema and fingerprints |
| `crewloom_import_reply` | Available only with explicit `--allow-import`; validate and publish exactly the packet's declared candidate files |
| `crewloom_verify` | Available only with explicit `--allow-verify`; run pending command steps through the existing Docker executor |

Enable writes only for a reviewed plan within the operator's authorized task. The tool inventory itself excludes write tools in the default mode. Root, checkout binding, project policy, task reservation and plan are checked on each call. Rebind or change the plan explicitly and restart the server after changing its authority.

The importing agent receives a structured `{ "artifacts": [{ "path": "declared.txt", "content": "candidate text" }] }` contract. A reply must cover every declared output exactly once. It cannot modify project policy, host configuration or runtime state. Input, guidance, context and output fingerprints must still match the packet. An existing owner edit or newly created output invalidates an older packet.

Imports use the same recoverable grouped publication as managed execution. Raw replies and publication references remain under the selected project's `.crewloom/private/agent-replies/` with owner-only permissions. Imported candidates do not complete a workflow step, certify model quality, promote lessons, or bypass the reviewer policy. Review the candidate through `workflow accept`, then run the unchanged verifier. MCP verification stops at outstanding task reviews and never accepts them.

The project lock serializes Crewloom writers. It does not sandbox the host or lock ordinary editors. Provider authentication, host tool permissions and independent reviewer identity remain the operator's responsibility.

## CLI reply import

Hosts without MCP can use the same importer. Save the issued packet and structured response as private project-relative JSON files:

```bash
crewloom workflow agent-packet --project /absolute/project --plan workflow.json > /absolute/project/.crewloom/private/packet.json
crewloom workflow import-reply --project /absolute/project --plan workflow.json --packet-file .crewloom/private/packet.json --response-file .crewloom/private/response.json
```

The explicit import command authorizes only candidate publication. Keep the packet and reply private and retain the separate task review and container acceptance steps.

## Verification

```bash
python3 -m unittest discover -s scripts -p test_mcp_bridge.py
CREWLOOM_MCP_TESTS=1 python3 -m unittest discover -s scripts -p test_mcp_bridge.py
```

The optional live test needs the MCP extra, Docker and the locally available `python:3.14-slim` image. It launches real stdio subprocesses using the legacy MCP handshake used by existing clients, checks both tool inventories, calls every exposed tool, imports a synthetic candidate, keeps review separate, and executes the unchanged verifier in Docker. It uses no paid model generation or user browser session.

Set `CREWLOOM_BROWSER_MCP_TESTS=1` for the separate pinned Playwright MCP acceptance. It needs Node/npm and an installed browser; optionally supply `PLAYWRIGHT_MCP_EXECUTABLE_PATH` for an existing test Chromium binary. The test navigates to its own loopback fixture, takes an accessibility snapshot, clicks the snapshot's current target, verifies the changed page and closes the isolated browser. These four browser tools are checked through real stdio transport.

## Browser and desktop integrations

The [Chrome side panel](CHROME_EXTENSION_SIDE_PANEL.md) remains a manually operated companion. The project task MCP server does not silently turn that panel into a model action channel.

For an agent-controlled test browser, Microsoft's [Playwright MCP server](https://github.com/microsoft/playwright-mcp) is an existing integration. The [isolated browser config](../examples/mcp/playwright-isolated.json) pins the tested server version, keeps the browser profile in memory, disables page-supplied WebMCP tools and routes artifacts into the selected project's private directory. Replace the output path before use, launch from the project root and validate the config through `mcp-config`. The template does not attach to the operator's authenticated browser session.

Configure host permissions separately; Playwright's browser connection is not Crewloom's task/publication boundary. Its origin filters do not sandbox redirects. Desktop accessibility, Screen Recording consent and application targeting require an actual native-host adapter and live verification before desktop control can be claimed.

The separate [scoped native AX acceptance](NATIVE_DESKTOP.md) client requires a reviewed bounded driver manifest and actual Accessibility verification. It does not add desktop tools to the task bridge.
