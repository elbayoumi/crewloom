# Specialist workflow recipes

## Ship a bounded product feature

1. `business-analyst-discovery`: unresolved decisions and acceptance criteria.
2. `tech-stack-architect`: architecture and differences from an existing base.
3. `fullstack-mvp-engineer`: implementation and error handling.
4. `frontend-ux-auditor`: static hints, grid checks, rendered layout and accessibility review.
5. `qa-test-automation-engineer`: tests and hashed delivery evidence tied to the current revision.
6. `delivery-director`: verified handoff and remaining work.

Use one owner per artifact. Architecture review does not stand in for implementation, and static hints do not stand in for browser evidence.

## Produce a short video

`creative-director` → `viral-hook-architect` → `video-script-architect` → `ai-voice-audio-engineer` → `video-assembly-editor` → `visual-qa-reviewer`.

Confirm the audience and approved claims. Use the script-pacing tool before voice recording. Voice and editing need separately configured media tools; no publishing occurs from these role instructions alone.

Use [the short-form reel plan](../workflows/social-reel.json) to make the same chain resumable project work: it pauses for the script, measures narration pacing with the bundled `script-pacing` tool as a command step, and records key frames, an assembly brief and a visual review. The plan produces assets and briefs; it does not record voice, assemble video or publish to a platform.

## Prepare organic content

`seo-growth-engineer` creates the keyword / intent brief and article packet. Run the packet gate, inspect the actual article and links, then obtain publishing authorization. The included packet example demonstrates schema checks, not search performance.

## Diagnose automation

`automation-ops-engineer` inspects the export and execution evidence. Run the workflow contract tool before importing changes. Keep credential references separate from exported data. Validate idempotency and recovery before rerunning work.

## Prompt template

> Read AGENTS.md, the chosen role, its detailed playbook, and relevant memory. Use English. The task is [concrete output]. Inputs are [real files]. Acceptance is [observable checks]. External actions are [explicit authority]. Verify the result and update memory.

> اقرأ AGENTS.md والمهارة ودليلها التفصيلي والبرين. استخدم العربية. المطلوب [مخرج محدد] والمدخلات [ملفات فعلية] وشروط القبول [فحوص واضحة]. التصرفات الخارجية المصرح بها [نطاق صريح]. افحص النتيجة وحدّث الذاكرة.

## Wire an application MCP server

`mcp-integration-builder` identifies the host, server purpose and tool contracts, configures the server, validates the client configuration with the bundled checker, exercises discovery plus one bounded tool call, and documents setup and removal. Use [the MCP integration plan](../workflows/mcp-integration.json) with the [application MCP guide](MCP.md). Configured, reachable and effective are separate claims; role steps cannot grant credentials or widen a server's filesystem authority.

## Executable software path

Use [the task plan](../workflows/software-feature.json) for host-produced work, or [the supplied feature example](../examples/software-workflow/README.md) to exercise six command stages. Both use the [same execution and handoff contract](EXECUTION.md). Task acceptance is not an authenticated review system.

## Evidence-driven repair workflows

A model step may declare `repair_from` with `plan`, `failed_step`, `model_step` and `candidates`. The source plan must have a finished failed command in the same bound project and checkout; its preceding model candidate must have been consumed by that verifier. `candidates` maps each original output to a separate, immutable input copy whose bytes match the failed execution. Include those copies and original source inputs in the repair model step's inputs. Keep the original role, host, model and output scope. The repair workflow has exactly that model step followed by the unchanged verifier step, with the same criteria and language.

The runner appends the bounded failure diagnostic as explicitly untrusted input, hashes the resulting prompt and rechecks the evidence before publishing generated files. Original inputs and verifier dependencies must remain unchanged; stale/cross-project references, modified candidate copies, changed verification and ancestry deeper than two repairs are rejected. Verification reuses the recorded Docker image digest, and the complete prompt including feedback remains within the existing 256 KiB input budget. Criteria, when supplied, must be a recorded producer or verifier input. Existing model-request and shared admission budgets still apply. Repair does not grant publication permission or change reviewer requirements.

Use a fresh workflow ID and explicitly name the original producer and failed verifier:

```sh
crewloom workflow prepare-repair --project /path/to/project --plan workflow.json --repair-id repair-one --model-step generate --step verify
```

This prepares owner-only candidate copies and a new plan under the project's `/.crewloom-repairs/` directory. The existing privacy guard ignores this namespace and rejects forced staged additions. Preparation refuses an active competing task; finish or cancel it through the normal flow first. Existing preparations and execution history are never overwritten. A rejected preparation may leave private files for inspection; use a fresh ID after fixing its cause.

To prepare and execute in one command, use `repair` instead of `prepare-repair`. Installed CLI providers retain the explicit `--allow-host-cli` requirement. API providers retain their normal credential requirements. The repair uses the same model and verifier image as the failed execution; it never silently substitutes a stronger model. A second repair can reference the preceding prepared plan. A third repair is refused. The shared project ledger also limits repair model requests to two per original workflow, including failed requests and branches with new IDs. Ordinary `run` does not start paid repairs automatically.

Deterministic provider fixtures verify failure-feedback delivery, original-journal preservation, retry limits and reuse; real Docker verification tests the failed-to-passing artifact cycle. These tests do not establish improvement for a particular live model. The checks do not authenticate arbitrary host tools or make state files tamper-proof.
