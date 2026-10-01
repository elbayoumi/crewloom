# Challenges

No local incidents have been recorded. Record the cause, attempted solution, result, and remaining blocker.

### 2026-10-01 — Generation events are not equivalent
- Cause: A successful host turn can include nonfatal diagnostic items.
- Fix: Require completed structured output; keep diagnostics separate from tool events and reject undeclared artifacts.
- Check: Parser regression and real generated-feature workflow pass.
