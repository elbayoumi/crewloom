# Backlog

- [x] Provide English public role procedures and Arabic / English context labels.
- [x] Separate public memory from upstream operational history.
- [ ] Evaluate representative specialist tasks across supported agent hosts.
- [ ] Package selected external-tool integrations with clean setup and acceptance evidence.
- [ ] Consider a distributable Python package after repository-native interfaces stabilize.

### 2026-10-01 — Toolkit depth refresh ✅
- Artifact: Detailed references, tool discovery, examples and README navigation.
- Status: Implemented and locally validated.
- Next: Provider-specific end-to-end evaluations remain future work.

- [ ] Add role-level run history charts to the dashboard — priority: medium
- [ ] Add optional auth before any non-localhost dashboard use — priority: high

- [ ] Publish before/after evidence for 2-3 real tasks with full outputs — priority: high
- [ ] Set GitHub social preview image (manual in repo settings) and add good-first-issue tasks — priority: medium
- [ ] Add dashboard token authentication — priority: high

- [x] Make grid-safety skip pixel floors behind a breakpoint prefix that already fits them (2 false positives, see documentation/EVIDENCE.md) — priority: medium

- [x] Ship a real token-drift check (palette vs design-tokens.json); the playbook's check_palette_drift.py is not included — priority: high
- [ ] Third evaluation: defects a generic review tends to miss (non-obvious drift, cross-file issues), blind grading by a separate agent, 5+ runs — priority: medium

### 2026-10-01 — Project path isolation
- Artifact: Project isolation fix ✅.
- Status: CLI/dashboard scope covered by regressions.
- Remaining: Arbitrary host tools need project-scoped permissions; no sandbox claim.

### 2026-10-01 — Role installation memory isolation
- Artifact: Safe project role updates ✅.
- Status: Local memory preserved and first-install history clean.
- Remaining: Arbitrary host filesystem access still needs host-specific permissions.

### 2026-10-01 — Executable software workflows
- Artifact: Software execution foundation ✅; six detailed English contracts and objective feature grading.
- Status: Runnable fixture, Docker isolation, resume/handoff, host-layout setup and readiness implemented.
- Remaining: Real independently coordinated provider trials; remaining detailed role translations; authenticated review and external-model adapters.
