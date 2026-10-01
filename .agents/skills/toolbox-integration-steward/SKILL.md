---
name: toolbox-integration-steward
description: Inspect the reusable tool registry and the actual script inputs and outputs. Use for toolbox integration steward tasks.
---

# Toolbox Integration Steward

## When to use

Use this role for toolbox integration steward work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Inspect the reusable tool registry and the actual script inputs and outputs.
2. Define a concrete usage contract including arguments, environment, timeout, and side effects.
3. Connect only supported execution paths to the catalog or UI.
4. Exercise the contract and report unavailable dependencies rather than implying readiness from registration.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the English procedure](references/PLAYBOOK.en.md) for project execution. Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.
