---
name: network-infra-engineer
description: Confirm domain, target host, intended exposure, and authorized network changes. Use for network infra engineer tasks.
---

# Network Infra Engineer

## When to use

Use this role for network infra engineer work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Confirm domain, target host, intended exposure, and authorized network changes.
2. Inspect DNS, routing, TLS, reverse proxy, and firewall configuration before mutation.
3. Apply bounded changes with rollback and least exposure appropriate to the service.
4. Verify reachability and certificate behavior from the relevant network vantage point.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the English procedure](references/PLAYBOOK.en.md) for project execution. Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.
