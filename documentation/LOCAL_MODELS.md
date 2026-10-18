# OpenCode model selection and local providers

Crewloom keeps model selection explicit. An OpenCode model step uses `host: "opencode"` and a `model` identifier in `provider/model` form. Built-in providers use their existing operator authentication. Crewloom does not silently replace the selected model during repair.

For a local OpenAI-compatible server, create an owner-only profile at `.crewloom/private/providers/local.json` inside the bound project:

```json
{
  "schema_version": 1,
  "provider_id": "local",
  "base_url": "http://127.0.0.1:11434/v1",
  "models": ["YOUR_MODEL_ID"],
  "prompt_budget_bytes": 65536
}
```

Set these fields on the existing model step, retaining its role, source inputs, output paths and verification step:

```json
{
  "host": "opencode",
  "model": "local/YOUR_MODEL_ID",
  "opencode_provider": ".crewloom/private/providers/local.json"
}
```

The step fragment is not a complete workflow. Replace `YOUR_MODEL_ID` with an actual model served by your endpoint. Model IDs may contain additional slashes. You can declare up to 64 model IDs and select one per step. The server must already be running; Crewloom does not download models or change server settings. Loopback endpoints with explicit ports are supported, including Ollama and LM Studio when configured for the OpenAI-compatible API. See the [OpenCode provider documentation](https://opencode.ai/docs/providers/).

Create the private directory with owner-only permissions and save the profile with mode `600`. On POSIX systems, the reader rejects group/other permissions and files owned by another user; non-POSIX ACL ownership is not verified. Keep it in `.crewloom/private/`, which the existing [privacy guard](PRIVACY.md) ignores and rejects from staged publication. The profile accepts only the five documented fields. It cannot import plugins, MCP servers, tools, arbitrary SDK packages or general OpenCode configuration. The adapter retains its existing tool-denial profile and enables only the declared local provider for this call.

`prompt_budget_bytes` bounds Crewloom's assembled task prompt, including repair feedback. It is a byte limit, not a tokenizer measurement or a promise about the model's usable context. OpenCode adds its own system/schema instructions; leave headroom for those and generated output in the server's token budget. Adapter/platform limits may be stricter. Oversized prompts are refused before inference; source files and acceptance requirements are never silently truncated to fit.

The profile hash enters the task prompt fingerprint and generation record. Changes during generation reject publication; changes after successful generation reject reuse. Repair requires the original profile, model and verification contract to remain unchanged. Start a separately reviewed task to change them.

Run through the existing compatibility path:

```sh
crewloom workflow run --project /path/to/project --plan workflow.json --allow-host-cli
```

After a recorded verification failure, use the [bounded repair commands](WORKFLOWS.md). Native CLI execution remains an explicit [host compatibility exception](ENFORCEMENT.md), not an OS sandbox.

Acceptance checks cover model/profile forwarding, endpoint and path refusal, prompt budgets, publication freshness and reuse. An opt-in integration test runs the installed OpenCode CLI against a deterministic loopback protocol fixture:

```sh
CREWLOOM_OPENCODE_LOCAL_TESTS=1 python3 -m unittest discover -s scripts -p test_model_host.py
```

The protocol fixture is not a real local language model. It demonstrates adapter compatibility, not model intelligence. Measure quality on fixed independent tasks with the chosen real model, reporting baseline and repaired success alongside total requests, latency, cost and user interventions. No universal weak-model improvement or Claude equivalence is established by these checks.
