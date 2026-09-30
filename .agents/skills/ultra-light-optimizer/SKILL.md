---
name: ultra-light-optimizer
description: Inspect the code path and measure relevant query, payload, bundle, and event costs. Use for ultra light optimizer tasks.
---

# Ultra Light Optimizer

## When to use

Use this role for ultra light optimizer work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Inspect the code path and measure relevant query, payload, bundle, and event costs.
2. Identify over-fetching, looped requests, missing pagination, and heavy dependencies.
3. Apply bounded changes that preserve behavior and use existing efficient patterns.
4. Run the supplied resource-pattern checker and relevant measurements; document false positives and exceptions.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.

## Included executable tools

- [resource-budget](scripts/check_resource_budget.py): Heuristic resource-waste pattern scan.

See the [tool catalog](../../../documentation/TOOLS.md) for commands, inputs, side effects and exit behavior.
