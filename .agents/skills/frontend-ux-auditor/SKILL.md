---
name: frontend-ux-auditor
description: Inspect the relevant UI code, approved tokens, user flow, and supported viewports. Use for frontend ux auditor tasks.
---

# Frontend Ux Auditor

## When to use

Use this role for frontend ux auditor work. Match the task scope before activation; do not assume the host has external tools or account permissions.

## Brain and preflight

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, input facts, authority, dependencies, and acceptance criteria.

## Procedure

1. Inspect the relevant UI code, approved tokens, user flow, and supported viewports.
2. Check usability, accessibility, responsive layout, and Arabic RTL behavior where applicable.
3. Fix issues in the existing components and choose behavior tests appropriate to the change.
4. Inspect rendered results and distinguish local validation from deployed behavior.

## Deliverable and verification

Deliver the concrete artifact or findings, the evidence used, checks performed, and remaining limitations. Use Arabic or English as requested. Identify missing tools or facts explicitly; do not fill gaps with invented results.

## Closure

Update completed work, challenges, ideas, and backlog with concise records. Keep credentials and private customer records out of shared memory.

## Detailed procedures and specialist references

Read [the full Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, step-by-step procedures, acceptance conditions, and handoff requirements. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when selecting tools and project inputs. The English entry point and shared constitution govern public task execution. Source-specific external documents are [project inputs](../../../documentation/PROJECT_INPUTS.md), not bundled private records.

## Included executable tools

- [ui-hints](scripts/check_ui_quality.py): Static UI hints; exit 2 requests rendered review rather than claiming acceptance.
- [grid-safety](scripts/check_responsive_grid_safety.py): Find fixed-pixel grid floors without viewport bounds.
- [layout-overlap](scripts/check_layout_overlap.py): Check geometric sibling overlap from supplied browser snapshot JSON.

See the [tool catalog](../../../documentation/TOOLS.md) for commands, inputs, side effects and exit behavior.
