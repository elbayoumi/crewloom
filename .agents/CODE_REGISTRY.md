# Reusable code registry

Core Python tools use the standard library. Commands run from the checkout root. Host tools for specialist tasks are not bundled.

| Path | Purpose | Command |
| --- | --- | --- |
| [scripts/crewloom.py](../scripts/crewloom.py) | Role discovery, validation, and context CLI | `python3 scripts/crewloom.py list` |
| [scripts/check_repository.py](../scripts/check_repository.py) | Public checkout structure, syntax, links, and regressions | `python3 scripts/check_repository.py` |
| [.agents/skills/skill-forge-recruiter/scripts/validate_skill.py](../.agents/skills/skill-forge-recruiter/scripts/validate_skill.py) | Bilingual procedure structure | `python3 .agents/skills/skill-forge-recruiter/scripts/validate_skill.py --skill context-guardian` |
| [.agents/skills/skill-forge-recruiter/scripts/test_validate_skill.py](../.agents/skills/skill-forge-recruiter/scripts/test_validate_skill.py) | Bilingual validator regressions | `python3 -m unittest discover -s .agents/skills/skill-forge-recruiter/scripts -p test_validate_skill.py` |
| [.agents/skills/context-guardian/scripts/context_pack.py](../.agents/skills/context-guardian/scripts/context_pack.py) | Bounded English / Arabic context packs | `python3 scripts/crewloom.py context context-guardian --out /tmp/crewloom.md --language en` |
| [.agents/skills/context-guardian/scripts/test_context_pack.py](../.agents/skills/context-guardian/scripts/test_context_pack.py) | Context completeness and language regressions | `python3 -m unittest discover -s .agents/skills/context-guardian/scripts -p test_context_pack.py` |
| [.agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py](../.agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py) | Heuristic resource-pattern scan | `python3 .agents/skills/ultra-light-optimizer/scripts/check_resource_budget.py --project-dir /path/to/project` |
| [scripts/test_public_core.py](../scripts/test_public_core.py) | CLI and public checker regressions | `python3 -m unittest discover -s scripts -p test_public_core.py` |
| [.agents/skills/automation-ops-engineer/scripts/check_workflow_contract.py](../.agents/skills/automation-ops-engineer/scripts/check_workflow_contract.py) | Validate an n8n export; reject embedded literal secret fields | `python3 scripts/crewloom.py run workflow-contract -- {input}` |
| [.agents/skills/seo-growth-engineer/scripts/check_seo_content_packet.py](../.agents/skills/seo-growth-engineer/scripts/check_seo_content_packet.py) | Validate article metadata, length, canonical and internal links | `python3 scripts/crewloom.py run seo-packet -- --packet {input}` |
| [.agents/skills/mcp-integration-builder/scripts/validate_mcp_config.py](../.agents/skills/mcp-integration-builder/scripts/validate_mcp_config.py) | Check MCP server configuration and suspicious credential literals | `python3 scripts/crewloom.py run mcp-config -- --config {input}` |
| [.agents/skills/video-script-architect/scripts/validate_script_pacing.py](../.agents/skills/video-script-architect/scripts/validate_script_pacing.py) | Measure script word pacing for a selected duration | `python3 scripts/crewloom.py run script-pacing -- --file {input} --duration 30` |
| [.agents/skills/paid-media-buyer/scripts/budget_pacer.py](../.agents/skills/paid-media-buyer/scripts/budget_pacer.py) | Compare actual campaign spend with approved expected pacing | `python3 scripts/crewloom.py run budget-pacing -- --daily-budget 100 --days-elapsed 3 --actual-spend 300` |
| [.agents/skills/frontend-ux-auditor/scripts/check_ui_quality.py](../.agents/skills/frontend-ux-auditor/scripts/check_ui_quality.py) | Static UI hints; exit 2 requests rendered review rather than claiming acceptance | `python3 scripts/crewloom.py run ui-hints -- --project-dir {input} --json` |
| [.agents/skills/frontend-ux-auditor/scripts/check_responsive_grid_safety.py](../.agents/skills/frontend-ux-auditor/scripts/check_responsive_grid_safety.py) | Find fixed-pixel grid floors without viewport bounds | `python3 scripts/crewloom.py run grid-safety -- --project-dir {input} --json` |
| [.agents/skills/frontend-ux-auditor/scripts/check_layout_overlap.py](../.agents/skills/frontend-ux-auditor/scripts/check_layout_overlap.py) | Check geometric sibling overlap from supplied browser snapshot JSON | `python3 scripts/crewloom.py run layout-overlap -- --snapshot {input} --json` |
| [.agents/skills/qa-test-automation-engineer/scripts/check_delivery_packet.py](../.agents/skills/qa-test-automation-engineer/scripts/check_delivery_packet.py) | Verify evidence bookkeeping, revision and hashes; not evidence truth | `python3 scripts/crewloom.py run delivery-evidence -- --help` |
| [.agents/skills/frontend-ux-auditor/scripts/test_ui_quality.py](../.agents/skills/frontend-ux-auditor/scripts/test_ui_quality.py) | Domain regressions | `python3 -m unittest discover -s .agents/skills/frontend-ux-auditor/scripts -p test_ui_quality.py` |
| [.agents/skills/frontend-ux-auditor/scripts/test_responsive_grid_safety.py](../.agents/skills/frontend-ux-auditor/scripts/test_responsive_grid_safety.py) | Domain regressions | `python3 -m unittest discover -s .agents/skills/frontend-ux-auditor/scripts -p test_responsive_grid_safety.py` |
| [.agents/skills/qa-test-automation-engineer/scripts/test_delivery_packet.py](../.agents/skills/qa-test-automation-engineer/scripts/test_delivery_packet.py) | Domain regressions | `python3 -m unittest discover -s .agents/skills/qa-test-automation-engineer/scripts -p test_delivery_packet.py` |

| [scripts/test_domain_tools.py](../scripts/test_domain_tools.py) | CLI examples and malformed-input regressions | `python3 -m unittest discover -s scripts -p test_domain_tools.py` |
| [scripts/test_run_log.py](../scripts/test_run_log.py) | Run-log append and opt-out regressions | `python3 -m unittest discover -s scripts -p test_run_log.py` |
| [dashboard/](../dashboard/README.md) | Live monitoring web app: roles, memory, tools, runs | `cd dashboard && npm install && npm run dev` |
| [scripts/test_install.py](../scripts/test_install.py) | `crewloom install` copy, overwrite-refusal, and validation regressions | `python3 -m unittest discover -s scripts -p test_install.py` |
| [.agents/skills/frontend-ux-auditor/scripts/check_palette_drift.py](../.agents/skills/frontend-ux-auditor/scripts/check_palette_drift.py) | Find literal colors in UI source that are absent from the approved design tokens | `python3 scripts/crewloom.py run palette-drift -- --project-dir {input} --tokens design-tokens.json` |
| [.agents/skills/frontend-ux-auditor/scripts/test_palette_drift.py](../.agents/skills/frontend-ux-auditor/scripts/test_palette_drift.py) | Palette drift regressions | `python3 -m unittest discover -s .agents/skills/frontend-ux-auditor/scripts -p test_palette_drift.py` |
| [scripts/workflow.py](../scripts/workflow.py) | Project-bound Docker workflows, state, handoff, and readiness; context-guardian / delivery-director | `python3 scripts/crewloom.py workflow doctor` |
| [scripts/test_workflow.py](../scripts/test_workflow.py) | Workflow invariants and opt-in real Docker acceptance | `CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p test_workflow.py` |
| [examples/software-workflow/project/stages.py](../examples/software-workflow/project/stages.py) | Executable software workflow demonstration stages; fullstack-mvp-engineer / QA | `python3 scripts/crewloom.py workflow run --project /path/to/copied/example` |
| [examples/software-workflow/project/solution/slug.py](../examples/software-workflow/project/solution/slug.py) | Unicode slug acceptance fixture implementation; fullstack-mvp-engineer | `python3 -m unittest discover -s tests` from the executed example project |
| [examples/software-workflow/project/tests/test_slug.py](../examples/software-workflow/project/tests/test_slug.py) | English/Arabic Unicode feature acceptance; QA | `python3 -m unittest discover -s tests` from the executed example project |
| [scripts/evaluate_feature.py](../scripts/evaluate_feature.py) | Label-free held-out Unicode feature acceptance; QA | `python3 scripts/evaluate_feature.py --project /path/to/submission --repeats 3` |
| [scripts/test_evaluate_feature.py](../scripts/test_evaluate_feature.py) | Objective grader error and acceptance regressions | `python3 -m unittest discover -s scripts -p test_evaluate_feature.py` |
| [examples/evaluation/unicode-slug/seeded-baseline/src/slug.py](../examples/evaluation/unicode-slug/seeded-baseline/src/slug.py) | Intentionally incomplete benchmark reference | `python3 scripts/evaluate_feature.py --project examples/evaluation/unicode-slug/seeded-baseline --repeats 3` |

| [scripts/model_host.py](../scripts/model_host.py) | Bounded CLI text-generation adapters and validated artifacts; fullstack-mvp-engineer | `crewloom workflow run --project /path/to/model-project` |
| [scripts/test_model_host.py](../scripts/test_model_host.py) | Model artifact paths, host flags, failure budget and project isolation; QA | `python3 -m unittest discover -s scripts -p test_model_host.py` |
| [scripts/evaluate_hosts.py](../scripts/evaluate_hosts.py) | Frozen repeated host trials with label-free scoring; QA | `crewloom evaluate-hosts --host codex --host claude --output /path/to/fresh-evidence` |
| [scripts/test_evaluate_hosts.py](../scripts/test_evaluate_hosts.py) | Balanced trials, frozen protocol, failure budget and anonymous grading; QA | `python3 -m unittest discover -s scripts -p test_evaluate_hosts.py` |
| [examples/model-workflow/project/verify.py](../examples/model-workflow/project/verify.py) | Executes supplied acceptance and records actual output; QA | `python3 verify.py` from the copied project |
| [examples/model-workflow/project/tests/test_slug.py](../examples/model-workflow/project/tests/test_slug.py) | English/Arabic contract acceptance of freshly generated code; QA | `python3 -m unittest discover -s tests` from the copied project |

| [scripts/execution_policy.py](../scripts/execution_policy.py) | Declared artifact broker; context-guardian | `crewloom workflow run --project /path/to/project` |

| [scripts/provider_gateway.py](../scripts/provider_gateway.py) | Tool-free provider RPC; fullstack-mvp-engineer | `crewloom workflow run --project /path/to/project` |

| [scripts/test_execution_policy.py](../scripts/test_execution_policy.py) | Broker rejection and acceptance; QA | `python3 -m unittest discover -s scripts -p test_execution_policy.py` |

| [scripts/test_provider_gateway.py](../scripts/test_provider_gateway.py) | Provider transport and default host denial; QA | `python3 -m unittest discover -s scripts -p test_provider_gateway.py` |

| [scripts/repo_map.py](../scripts/repo_map.py) | Project-local symbol index, versioned generations, SHA-verified reuse and bounded navigation; context-guardian | `crewloom map --project /path/to/git-project --query login` |
| [scripts/test_repo_map.py](../scripts/test_repo_map.py) | Map freshness, generations, seed visibility, import accuracy and CLI regressions; QA | `python3 -m unittest discover -s scripts -p test_repo_map.py` |

| [scripts/project_binding.py](../scripts/project_binding.py) | Portable project identity, local checkout binding, agency ledger validation and lifecycle; context-guardian | `crewloom project status --project /path/to/project --project-id id` |
| [scripts/project_context.py](../scripts/project_context.py) | Frozen per-task context generations with hash-validated code ranges; context-guardian | `crewloom project enter --project /path/to/project --project-id id --task-id task --role context-guardian` |
| [scripts/project_lessons.py](../scripts/project_lessons.py) | Evidence-linked lessons; promotion needs recorded executor evidence; QA | `crewloom lesson list --project /path/to/project` |
| [scripts/context_pilot.py](../scripts/context_pilot.py) | Reproducible cold/warm context pilot and byte comparison; context-guardian | `python3 scripts/context_pilot.py --out /tmp/crewloom-pilot.json` |
| [scripts/test_project_binding.py](../scripts/test_project_binding.py) | Identity, bootstrap, relocation, ledger and reservation regressions; QA | `python3 -m unittest discover -s scripts -p test_project_binding.py` |
| [scripts/test_task_context.py](../scripts/test_task_context.py) | Frozen generation, staleness, range and budget regressions; QA | `python3 -m unittest discover -s scripts -p test_task_context.py` |
| [scripts/test_project_lessons.py](../scripts/test_project_lessons.py) | Forged-success rejection and evidence-gated promotion; QA | `python3 -m unittest discover -s scripts -p test_project_lessons.py` |
| [scripts/test_project_lifecycle.py](../scripts/test_project_lifecycle.py) | Managed enter/checkpoint/publish-gate/finalize integration; QA | `python3 -m unittest discover -s scripts -p test_project_lifecycle.py` |
| [scripts/test_context_pilot.py](../scripts/test_context_pilot.py) | Cold/warm pilot acceptance against measured behaviour, with live acceptance gated on a reachable Docker daemon; QA | `python3 -m unittest discover -s scripts -p test_context_pilot.py` |
| [scripts/test_context_acceptance_boundaries.py](../scripts/test_context_acceptance_boundaries.py) | Independent acceptance regressions for lock ownership, ownership preflight, byte-room bounding, scoped freshness and managed prompt delivery; QA | `python3 -m unittest discover -s scripts -p test_context_acceptance_boundaries.py` |

| [examples/evaluation/project-context-20261003/check.py](../examples/evaluation/project-context-20261003/check.py) | Nine frozen public-project navigation/context acceptance cases; QA / context-guardian | `python3 crewloom-hook-pilot/check.py` inside the documented disposable project workflow |

The public context acceptance checker consumes `crewloom-hook-pilot/{context.json,acceptance.json}` and the explicitly declared seed; it writes `crewloom-hook-pilot/result.json`, exits 0 only when all nine checks pass, and exits non-zero on failed/missing/malformed input. It uses the Python standard library; its recorded workflow additionally requires Docker. It is a verification fixture, not a folder-open adapter or a client-delivery benchmark.
