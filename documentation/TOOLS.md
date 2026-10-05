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

| [project-context](../scripts/project_binding.py) | Portable project identity, local checkout binding, lifecycle entry and finalization | `python3 scripts/crewloom.py project status --project /path/to/project --project-id id` |
| [context-generations](../scripts/project_context.py) | Frozen per-task context with hash-validated code ranges | `python3 scripts/crewloom.py project enter --project /path/to/project --project-id id --task-id task --role context-guardian` |
| [project-lessons](../scripts/project_lessons.py) | Evidence-linked lessons; promotion needs executor evidence | `python3 scripts/crewloom.py lesson list --project /path/to/project` |
| [navigation-index](../scripts/repo_map.py) | Versioned project symbol index with verified reuse | `python3 scripts/crewloom.py map --project /path/to/git-project --query login` |
| [syntax-resolution](../scripts/js_syntax.py) | Real JS/TS syntax trees and bounded project-local module resolution used by the navigation index | `python3 -c "import js_syntax; print(js_syntax.available())"` |
| [context-pilot](../scripts/context_pilot.py) | Reproducible cold/warm pilot and context byte comparison | `python3 scripts/context_pilot.py --out /tmp/pilot.json` |
| [reviewer-credentials](../scripts/reviewer_credentials.py) | Credential-verified reviewer identities with signed, scoped, revocable approvals | `python3 scripts/crewloom.py reviewer status --project /path/to/project` |
| [resource-resolver](../scripts/crewloom_resources.py) | Resolves roles, documentation and dashboard sources in a checkout or an installed distribution | `python3 scripts/crewloom.py list` |
| [agency-readiness](../scripts/agency_readiness.py) | Read-only evidence and rollout readiness for one explicitly registered project | `python3 scripts/agency_readiness.py --project-id sample-client --project-root /path/to/project --agency-root /path/to/agency --registry .agents/project-control/registry.json` |

The [readiness guide](READINESS.md) explains required evidence, exit statuses and the optional private report directory. Readiness does not reconcile project records or deploy changes.

Project context is opt-in per project and never changes workflow isolation. See [project context](PROJECT_CONTEXT.md).

## Optional syntax extra

Every core tool above runs on the Python standard library alone. The navigation index reads real JS/TS syntax trees and `tsconfig` aliases only when the one optional extra is installed:

```
python3 -m pip install 'crewloom[syntax]'   # tree-sitter 0.23.2, javascript 0.23.1, typescript 0.23.2
```

Without it the same commands still work and the generated map records that approximate extraction was used, so a missing extra is reported rather than hidden. `map --help` and the map metadata name the parser that produced each index.

Native host setup and callback boundaries: [Native host lifecycle](HOST_LIFECYCLE.md).
