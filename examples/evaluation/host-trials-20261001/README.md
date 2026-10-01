# Recorded provider-trial evidence

Ten fresh Codex generations were scored on the frozen Unicode slug contract: five with the full-stack role and five without it. Each submission passed all nine acceptance cases. This is a tie on this task; it does not demonstrate a role-quality improvement.

Claude was requested for five trials per condition. Two actual generation attempts failed because the local CLI was unauthenticated; the remaining eight calls were skipped by the failure budget. No Claude acceptance score exists and cross-host evaluation is incomplete.

`protocol.json` was saved before provider calls; it records task/scorer/case fingerprints and randomized trial order. `mapping.json` contains treatment labels separately from anonymized submission scores. Each submission folder contains generated source, generation metadata and deterministic Docker scoring. Unreported Codex cost and actual built-in model identity remain unknown.

The runner coordinated and inspected this experiment; there is no independent human reviewer. The public task/cases and small single-function scope limit inference. See the [reproduction procedure](../unicode-slug/HOST_TRIALS.md).
