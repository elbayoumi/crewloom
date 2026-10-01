# Executable tool catalog

Run `python3 scripts/crewloom.py tools` to list these tools. `run` dispatches only registered paths; arguments after `--` go to the selected tool. Core tools use the Python standard library.

| Tool | Purpose | Arguments |
| --- | --- | --- |
| [workflow-contract](../.agents/skills/automation-ops-engineer/scripts/check_workflow_contract.py) | Validate an n8n export; reject embedded literal secret fields | `{input}` |
| [seo-packet](../.agents/skills/seo-growth-engineer/scripts/check_seo_content_packet.py) | Validate article metadata, length, canonical and internal links | `--packet {input}` |
| [mcp-config](../.agents/skills/mcp-integration-builder/scripts/validate_mcp_config.py) | Check MCP server configuration and suspicious credential literals | `--config {input}` |
| [script-pacing](../.agents/skills/video-script-architect/scripts/validate_script_pacing.py) | Measure script word pacing for a selected duration | `--file {input} --duration 30` |
| [budget-pacing](../.agents/skills/paid-media-buyer/scripts/budget_pacer.py) | Compare actual campaign spend with approved expected pacing | `--daily-budget 100 --days-elapsed 3 --actual-spend 300` |
| [ui-hints](../.agents/skills/frontend-ux-auditor/scripts/check_ui_quality.py) | Static UI hints; exit 2 requests rendered review rather than claiming acceptance | `--project-dir {input} --json` |
| [grid-safety](../.agents/skills/frontend-ux-auditor/scripts/check_responsive_grid_safety.py) | Find fixed-pixel grid floors without viewport bounds | `--project-dir {input} --json` |
| [palette-drift](../.agents/skills/frontend-ux-auditor/scripts/check_palette_drift.py) | Find literal colors in UI source that are absent from the approved design tokens; exit 1 drift, 2 unverified | `--project-dir {input} --tokens design-tokens.json` |
| [layout-overlap](../.agents/skills/frontend-ux-auditor/scripts/check_layout_overlap.py) | Check geometric sibling overlap from supplied browser snapshot JSON | `--snapshot {input} --json` |
| [delivery-evidence](../.agents/skills/qa-test-automation-engineer/scripts/check_delivery_packet.py) | Verify evidence bookkeeping, revision and hashes; not evidence truth | `--help` |
| [context](../.agents/skills/context-guardian/scripts/context_pack.py) | Bounded English or Arabic context pack | `--skill context-guardian --out /tmp/context.md` |
| [validate-skill](../.agents/skills/skill-forge-recruiter/scripts/validate_skill.py) | Validate role structure | `--skill context-guardian` |
| [resource-budget](../.agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py) | Heuristic resource-waste pattern scan | `--project-dir {input}` |

`{input}` means a real path supplied by you. Start with [the runnable examples](../examples/README.md). Commands do not install dependencies or authorize external operations. Tool messages may be English or Arabic.

For exact JSON contracts inspect the tool docstring and validation function. The source is linked directly above so the input contract is reviewable.

| [workflow](../scripts/workflow.py) | Isolated software workflows and role handoff | `python3 scripts/crewloom.py workflow doctor` |

Workflow execution requires Docker and a locally available image. See [execution](EXECUTION.md). Feature evaluation has a separate [benchmark contract](../examples/evaluation/unicode-slug/README.md).
