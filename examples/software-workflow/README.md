# Unicode software feature workflow

Copy `project/` into a fresh project directory and follow [the execution guide](../../documentation/EXECUTION.md). The supplied implementation normalizes Unicode slugs, preserves Arabic letters, rejects invalid types, and has five executable acceptance cases.

The six stages demonstrate discovery artifacts, architecture, implementation, syntax review, QA and delivery evidence. They are deterministic demonstration commands, not an agent benchmark. Run them with:

```bash
python3 scripts/crewloom.py workflow run --project /path/to/copied/project
```

After completion, rerun to verify fingerprints and skip completed work. Modify a completed input or output and the old workflow refuses stale evidence. Use a new ID after reviewing changes.
