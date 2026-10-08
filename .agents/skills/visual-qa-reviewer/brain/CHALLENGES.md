# Challenges

No local incidents have been recorded. Record the cause, attempted solution, result, and remaining blocker.

### 2026-10-05 — Markdown sanitization and mobile artwork
- Cause: intended direction isolation can disappear when a hosting renderer strips bdi; a wide SVG can scale its text below readable sizes.
- Solution: verify retained directional markup in rendered output, use a narrow-layout asset and measure effective text size. Keep inventory counters in document text rather than artwork.
