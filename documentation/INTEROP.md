# Cross-framework execution adapters

Crewloom ships standard-library adapter code for CrewAI, AutoGen and LangGraph in
`adapters.interop`. Source installs, wheels and rebuilt sdists provide the same
imports. Framework packages themselves are optional and installed separately.
Docker, Linux/macOS/WSL and a locally available image are required for execution.

## Read and write boundaries

The canonical project root is mounted read-only at `/workspace`. Omitting
`writable`, passing `None`, or passing an empty sequence all prohibit project writes.
Explicit file/directory grants overlay writable bind mounts, e.g. `writable=["out"]`.
New grant paths are created as directories after the entire write set is validated.
At most 128 nonoverlapping grants and 10,000 inspected entries are accepted.

Project control paths (`.git`, `.crewloom`, native-host configuration and project
identity/scope files) cannot be grants or occur inside a granted tree. Symlinks,
hardlinked files, special files and project escapes are refused. Arbitrary
concurrent host mutations remain outside this boundary.

The whole project is readable except `.crewloom`, which is masked with read-only
tmpfs. This includes source and Git metadata; it is not a declared-input snapshot.
Explicit grants write directly to the host project. These adapters do not provide
workflow artifact validation, transactional publication or rollback. Use the
[managed workflow](ENFORCEMENT.md) when those guarantees are required.

Containers have networking disabled, read-only roots, non-root users, all
capabilities dropped and `no-new-privileges`. Limits are 1 GiB RAM, two CPUs,
128 PIDs, 128 MiB temporary storage and 4 MiB per file. Per-file limits do not cap
aggregate disk usage in writable directories. Normal output capture is bounded
at 64 KiB of returned UTF-8, including replacement characters and timeout/cancellation
diagnostics. Decoding cannot expand the returned text beyond that budget; truncation
is reported and cannot return a successful exit. One-shot containers are removed after execution. Docker and the OS
remain trusted; these restrictions do not establish protection from every escape.

## Interfaces

```python
from adapters.interop import CrewloomSandboxTool, CrewloomAutoGenExecutor, CrewloomLangGraphNode

tool = CrewloomSandboxTool(workspace_root="./repo", writable=["out"])
result = tool.execute("from pathlib import Path; Path('out/value.txt').write_text('42')")
```

Use `tool.to_crewai_tool()` if CrewAI expects its native `BaseTool`. AutoGen exposes
`execute_code_blocks` (sync), `a_execute_code_blocks` (async convenience), and
`as_async_executor()` for the awaited AutoGen 0.4 agent interface. Actual agent
acceptance uses `autogen-agentchat==0.4.9`; framework serialization is unsupported.
LangGraph exposes a state-delta
callable and `create_crewloom_sandbox_node`. Check your framework version's expected
protocol. See [adapter examples](../adapters/interop/README.md) and
[runnable demos](../examples/interop/README.md).

## Stateful AutoGen Python

```python
from adapters.interop import CrewloomAutoGenExecutor, CodeBlock

with CrewloomAutoGenExecutor("./repo", stateful=True) as executor:
    executor.execute_code_blocks([CodeBlock("python", "x=42")])
    result = executor.execute_code_blocks([CodeBlock("python", "print(x)")])
    print(result.output)
```

State lives in a Python interpreter inside its own isolated container. Blocks run
once; functions and imports remain usable without replay. No host pickle or
executable history restores state; legacy JSON history is ignored. Separate objects
have separate sessions unless an explicit `session_id` is supplied. `close()` frees
the container; `restart()` discards state before the next block starts a new one.
Exceptions are failures, but partial interpreter or authorized file changes are
not rolled back. Shell blocks remain one-shot and do not share Python variables.

CLI `--stateful --session <name>` reuses a named container across invocations for the
same canonical project and OS user. Image and write policy must match; changed
policies require `--session <name> --reset`. Named containers consume their bounded
resources until reset. Identity/policy labels are checked before reuse or removal;
unrelated containers are refused. Simultaneous creation may require retry after
the first creator finishes; blocks in one interpreter execute serially.

Stateful source is limited to 64 KiB UTF-8 and capture to 32 KiB per request,
including child processes and raw stdout/stderr writes. Excess output fails the
request with a bounded diagnostic; Python state remains available. Persistent
containers disable Docker logging. Child processes retaining capture descriptors
after the request cannot hold the response open indefinitely; their late output
is discarded. Background jobs are not a supported way to return later results.
Timeout (exit 124) or cancellation (exit 130) destroys the session. A surviving
object reports lost state and requires explicit restart; it never reconstructs
variables by replay. Daemon/container loss also loses state. Durable interpreter
snapshots are not provided.

## Acceptance

`CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p test_interop_adapters.py`
checks actual default-write refusal, allowed outputs, masked runtime, state without
replay, timeout/reset, cancellation and named CLI persistence.
`CREWLOOM_DISTRIBUTION_TESTS=1 python3 -m unittest discover -s scripts -p test_distribution.py`
checks imports from installed wheel and rebuilt sdist outside the checkout.
CI pulls `python:3.14-slim` first; explicit missing prerequisites fail acceptance.


For the pinned real AutoGen agent acceptance, install `autogen-agentchat==0.4.9`
and run the same suite with both `CREWLOOM_DOCKER_TESTS=1` and
`CREWLOOM_AUTOGEN_TESTS=1`. An explicitly requested SDK test fails if its dependency
is unavailable. No model or API key is needed.

Write grants must be a list or tuple of relative path strings, never a bare
string. An alternate policy selected by a valid local project binding is protected
as a file and as part of a directory grant; malformed/foreign bindings are refused
when granting writes. Adapter imports do not resolve consumer `workflow.py` modules.


Unsupported languages return a nonzero refusal. AutoGen validates the complete block
batch before executing a supported prefix; LangGraph never silently interprets an
unknown language as Python.

Cancelling an asyncio task running the async executor signals its worker and waits
for owned cleanup before propagating `CancelledError`. A call cancelled while waiting
for an occupied Python session does not interrupt that session's current block.
Explicit framework cancellation tokens still return exit 130. Docker control calls
have bounded timeouts; cleanup can take several seconds if the daemon is slow.
Concurrent automatic removal is tolerated only after ownership verification and
observing that the session disappeared; daemon failures and foreign labels remain errors.

The [adapter examples](../examples/interop/README.md) are previews by default.
`--require-execution` requires real container execution and fails on missing Docker,
daemon or image prerequisites. They do not establish framework SDK integration.
