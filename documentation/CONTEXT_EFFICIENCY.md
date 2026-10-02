# Context efficiency and accumulated lessons

Model steps use `memory_mode: focused` by default. The role procedure, playbook, project constitution, architecture, roadmap and declared input files remain complete. Completed work, challenges and ideas are selected as whole Markdown records: records matching task words and input filenames rank first, with recent records breaking ties. Selection is lexical, supports Unicode words, and is not semantic retrieval or model training. History on disk is never rewritten.

Each historical memory file has an 8192-byte selection budget. Set `memory_budget_bytes` to an integer from 1024 to 65536 to change it, or `memory_mode: full` when a task needs the complete history. Oversized records are omitted whole; prompt guidance reports `omitted_records`. Review the full project memory for high-context tasks. The combined prompt must fit 256 KiB; excess is rejected before a provider request rather than silently truncating code or rules. Compact JSON removes serialization whitespace. Stable role guidance precedes task-specific fields; provider caching benefits are not measured or guaranteed.

Relevant recorded solutions can help avoid repeating an error, but must match the current problem. Ideas are not verified solutions. Quality gains require controlled evaluations; this feature does not train a model or establish increasing intelligence.

## Reuse without stale evidence

Completed model steps reuse their existing project artifacts without another provider request only after artifact/input fingerprints and the current prompt hash match. A changed selected role, rule or memory record rejects reuse and requires review plus a new workflow ID. Older completed model records lacking a context hash require the same migration. Reuse stays within the selected project and workflow; there is no shared cross-project response cache. State records `context_bytes`, `context_sha256` and `memory_mode`; provider usage remains separate and is recorded when reported.

## Measurement

[Local measurement](CONTEXT_MEASUREMENT.json) compares full and focused context for 100 synthetic historical completion records, with identical task, rules and inputs: 63,107 bytes versus 9,439 bytes, an 85.04% reduction. This measures UTF-8 bytes, not billed tokens, provider cache hits or improved correctness. Actual savings depend on project history and tokenizer. Small memories remain unchanged.

Regression cases cover Arabic/English relevance, old relevant lessons amid recent noise, unchanged small memories, complete-record omission, untouched architecture/input data, malformed budgets, context-change rejection and unchanged-resume avoiding another generation call.

The resource-budget scanner initially reported five hard findings in existing scanner definitions or intentional SQL rejection fixtures. Reviewed exceptions are in [resource exceptions](RESOURCE_EXCEPTIONS.txt): no production database/network calls occur at those sites. With those exceptions the scanner passes; two soft findings remain in intentionally defective evaluation fixtures. DB, browser bundle and realtime budgets do not apply to this standard-library prompt change; resource owner: ultra-light-optimizer.
