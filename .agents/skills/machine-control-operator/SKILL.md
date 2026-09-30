---
name: machine-control-operator
description: Identify the authorized task, machine context, input files, and expected side effects. Use for machine control operator tasks.
---

# Machine Control Operator

## When to use

Use this role for machine control operator work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Identify the authorized task, machine context, input files, and expected side effects.
2. Prefer direct file, shell, API, or app interfaces and use GUI automation when appropriate.
3. Execute bounded operations with error handling and an audit record free of secrets.
4. Inspect the actual state after execution; do not claim external actions succeeded from intent alone.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.
