# Scoped native AX acceptance

Crewloom includes an optional CuaDriver client for one explicitly selected macOS application window. It is separate from the project task MCP server. The exposed tools observe one configured application window and press explicitly allowed accessibility buttons. The current acceptance target is `com.crewloom.NativeFixture`, with the title `Crewloom Native Acceptance` and the buttons `Increment` and `Reset`.

## Contract and dependencies

Inputs: one bound canonical project/task, an owner-only private policy and its unchanged manifest, an existing private CuaDriver socket, an explicitly observed target PID, and a freshly observed button handle. Outputs: scoped AX observations, private action records and an observation after delivery. Dependencies: macOS, the optional `crewloom[mcp]` extra, CuaDriver 0.28.2, and human-granted Accessibility permission. The synthetic fixture needs Apple's Swift compiler. No model provider is required.

The client never launches the driver, requests OS permissions, uses screen coordinates, switches focus, types arbitrary text or executes a command received through MCP. It connects with `mcp --embedded --socket` and has no broad-daemon fallback. `check_permissions` always receives `prompt:false`. Missing access, malformed structured output, a foreign or missing app/window, changed binding/policy/manifest, expired handles and unresolved captured task questions refuse the action. Transport errors preserve an uncertain action and consume its handle; there is no automatic retry. Re-observation does not by itself prove the user's postcondition.

## Prepare and review

```sh
crewloom native prepare --project /absolute/project --project-id example-project --task-id acceptance-task
```

Preparation writes an owner-only manifest and policy under `.crewloom/private/native/`. Existing policies cannot be overwritten. The private Unix socket path must be below macOS's 104-byte limit; a longer project path is refused explicitly. Preparation grants no authority and does not start a process.

For a real application, prepare an explicit target instead of the default fixture:

```sh
crewloom native prepare --project /absolute/project --project-id example-project \
  --task-id calculator-task --bundle-id com.apple.calculator --window-title Calculator \
  --button 7 --button Add --button 5 --button Equals --button 'All Clear'
```

Every custom scope needs the exact bundle ID, window title and unique allowed button labels. Use `--read-only` with no buttons to omit both driver click authority and the MCP click tool. Serving cannot change a prepared target. Preparation does not establish compatibility: record actual AX observations and results for each application and OS version. Arbitrary typing, coordinates, menus and commands remain outside this adapter.

Read the resulting manifest. [CuaDriver bounded mode](https://cua.ai/docs/cua-driver/guides/permissions) requires human approval of the exact manifest before starting with `--approve-capability-manifest`. Do not assert approval on behalf of the human or fall back to standard mode. If macOS requires Accessibility setup, the human grants it; Crewloom does not click system permission controls. The prepared manifest limits driver tools, expires after one hour, times out when idle, allows only the selected application and denies desktop display access.

After that review and approval, the operator starts the bounded daemon:

```sh
open -n -g -a CuaDriver --args serve --embedded --no-permissions-gate --no-overlay \
  --permission-mode bounded \
  --capability-manifest /absolute/project/.crewloom/private/native/HASH/capabilities.yaml \
  --approve-capability-manifest \
  --socket /absolute/project/.crewloom/private/native/HASH/driver.sock
```

The startup flags suppress onboarding and overlay UI; they do not grant or bypass OS access. A one-hour session that expires while work is paused must not be treated as active approval of a running session. Preserve its refusal and follow the human’s authorized continuation with the same reviewed manifest.

Use the exact generated paths in place of `HASH`. Build [the fixture source](../examples/native/Fixture.swift) into a private `.app` bundle with bundle ID `com.crewloom.NativeFixture`, and launch it in the background. The fixture contains only a counter and two buttons; it has no network or account operations.

```sh
crewloom native serve --project /absolute/project --project-id example-project \
  --task-id acceptance-task --policy .crewloom/private/native/HASH/policy.json --pid OBSERVED_PID
```

The stdio server exposes `crewloom_native_snapshot` and `crewloom_native_click(handle)`. Observe first, choose a returned button handle, press it once, then inspect the returned fresh state to verify the expected counter. All handles are invalidated by a new snapshot or action. Concurrent calls serialize within this connection. The supplied PID stays fixed for the connection; the bounded driver validates its application identity and the client rechecks exact window ownership before acting. Global application discovery is never requested. Structured rows and static text are restricted to the selected window; app menu rows and raw driver tokens are excluded. Missing identity, ambiguous rows and potentially truncated window text are refused.

## Evidence boundary

Driver-independent tests prove refusal of foreign applications, modified manifests, permissive policy files, stale/consumed handles and failed refreshes; they also verify background-only arguments and observe/act/reobserve sequencing. A successfully built fixture and these tests do not prove real Accessibility control. Record real driver tool calls, observed counter changes, actual permission status and negative target cases separately before claiming native execution. This client is an AX button acceptance surface, not general desktop automation or a sandbox for arbitrary host tools.

## Opt-in live acceptance

After human approval and bounded startup, record the fixture PID from its actual launch and use it below. The fixture must begin at zero. The test presses Increment and Reset, verifies `0 → 1 → 0`, rejects stale/unobserved handles and a foreign process, and preserves each attempt in a unique private JSON receipt. It is skipped by the ordinary repository suite. Use a Python environment containing the optional MCP SDK.

```sh
CREWLOOM_NATIVE_LIVE=1 \
CREWLOOM_NATIVE_PROJECT=/absolute/project \
CREWLOOM_NATIVE_PROJECT_ID=example-project \
CREWLOOM_NATIVE_TASK_ID=acceptance-task \
CREWLOOM_NATIVE_POLICY=.crewloom/private/native/HASH/policy.json \
CREWLOOM_NATIVE_PID=OBSERVED_PID \
python3 -m unittest discover -s scripts -p test_native_desktop.py
```

Live acceptance on 2026-10-14 passed with CuaDriver 0.28.2 and the synthetic fixture. The initial expired session and denied global discovery attempt were retained. This proves the scoped fixture flow only; arbitrary apps and general desktop workflows remain outside this acceptance.

### Additional application acceptance, 2026-10-15

Exact-target preparation was exercised on Calculator (`7 + 5`, exact static result `12`, stale handle refused) and TextEdit (one owned test document, snapshot tool only, unchanged file bytes). Their independently approved bounded sessions were stopped after verification. These are per-application acceptance results, not compatibility with every macOS application. The real Chrome profile separately passed extension 2.3.0 index/click/vision capture and was returned to disabled after the test.

The 2026-10-16 browser follow-up verified the actual profile upgrade to2.3.1 with the same permissions: index, click, capture and clear passed; the companion was disabled afterward. The earlier2.3.0 evidence remains historical.
