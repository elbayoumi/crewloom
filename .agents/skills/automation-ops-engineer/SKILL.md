---
name: automation-ops-engineer
description: Identify the workflow, triggers, credentials by reference, and expected outputs. Use for automation ops engineer tasks.
---

# Automation Ops Engineer

## When to use

Use this role for automation ops engineer work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Identify the workflow, triggers, credentials by reference, and expected outputs.
2. Inspect recent executions and isolate the failing step without exposing secrets.
3. Validate input contracts and idempotency before a bounded retry.
4. Record the change, run result, and rollback or recovery procedure.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the English procedure](references/PLAYBOOK.en.md) for project execution. Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.

## Included executable tools

- [workflow-contract](scripts/check_workflow_contract.py): Validate an n8n export; reject embedded literal secret fields.

See the [tool catalog](../../../documentation/TOOLS.md) for commands, inputs, side effects and exit behavior.
