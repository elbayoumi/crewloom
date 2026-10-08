# Challenges

No local incidents have been recorded. Record the cause, attempted solution, result, and remaining blocker.

### 2026-10-05 — Separate metadata and placement checks
- Cause: an external safe-zone checker may only probe export metadata and print layout guidance.
- Solution: inspect its actual implementation and verify visible content boundaries separately; retain the sampling resolution and pixel threshold in the evidence.
