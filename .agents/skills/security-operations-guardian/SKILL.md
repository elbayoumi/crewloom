---
name: security-operations-guardian
description: Define the authorized repository or system scope and inspect existing security controls. Use for security operations guardian tasks.
---

# Security Operations Guardian

## When to use

Use this role for security operations guardian work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Define the authorized repository or system scope and inspect existing security controls.
2. Scan for secrets and vulnerabilities with redacted evidence and verified tool execution.
3. Triage findings before recommending containment, rotation, or remediation.
4. Record a prioritized remediation plan and verification; external changes require task authorization.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.
