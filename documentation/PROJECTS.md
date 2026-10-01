# Project isolation

The Crewloom checkout supplies reusable code and role procedures. Each target project supplies its own installed role memory, relative inputs, outputs, and `.crewloom/runs.jsonl` history.

```bash
crewloom install --host agents --target /path/to/project --skill context-guardian
crewloom run --project /path/to/project workflow-contract -- workflow.json
crewloom context --project /path/to/project context-guardian --out /path/to/project/.crewloom/context.md
crewloom dashboard --project /path/to/project --port 4317
```

Without the installed CLI, substitute `python3 /path/to/crewloom/scripts/crewloom.py` for `crewloom`.

- `run` resolves inputs from the selected project (default: current directory), records its canonical root, and writes only that project's run history. Registered path arguments outside the project are rejected, including symlink redirects.
- `context --project` requires exactly one installed role under `.agents/skills` or `.claude/skills`, reads its local memory, and keeps output inside that project. It does not fall back to shared memory. The command without `--project` remains a library-role preview.
- A dashboard process monitors one project. `CREWLOOM_ROOT` selects the library checkout; `CREWLOOM_PROJECT` selects the project. Use separate ports for simultaneous projects. The current project is shown above the totals.
- Project role memory has no fallback to library memory. Repository checks still validate the library, as labeled.
- Installation refuses paths redirected outside the project. Keep project-specific state out of shared public role memory.

Existing unlabelled shared run records are not migrated into client histories: their project identity cannot be safely inferred. Older dashboard processes must be restarted with the project selected explicitly.

These guards apply to the CLI and dashboard entry points. Direct scripts, arbitrary agent tools, files referenced inside supplied packets, and external integrations require their own project-scoped permissions; this is not a filesystem sandbox.

Verification: two-project CLI and dashboard fixtures with identical relative filenames, separate run histories and memories, and rejected cross-project/context/symlink paths. See [the evidence log](EVIDENCE.md).

## Installing and updating roles

Fresh installations copy reusable architecture guidance and initialize empty project records. `install --force` refreshes role procedures/tools while preserving all existing brain files and project-local custom files. It does not import completed work, incidents, ideas, or task history from the library. Resolved destination files are checked before copying to prevent nested symlink redirects.
