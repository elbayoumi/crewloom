---
name: context-guardian
description: Define one task owner, output, scope, and acceptance criteria. Use for context guardian tasks.
---

# Context Guardian

## When to use

Use this role for context guardian work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Define one task owner, output, scope, and acceptance criteria.
2. Build a bounded context pack from the chosen skill and relevant memory.
3. Use complete sources or explicit read references; never silently truncate requirements.
4. Track failure signatures and previous attempts across handoffs, then verify and sync memory.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the English procedure](references/PLAYBOOK.en.md) for project execution. Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.

## Included executable tools

- [context](scripts/context_pack.py): Bounded English or Arabic context pack.

See the [tool catalog](../../../documentation/TOOLS.md) for commands, inputs, side effects and exit behavior.
