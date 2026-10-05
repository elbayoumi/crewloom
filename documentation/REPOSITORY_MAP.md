# Project repository maps

A repository map is a navigation index: relative file paths, definition names and line numbers. Crewloom can build one locally without sending source code to a service or executing project code. Python uses the standard-library AST. With `pip install ".[syntax]"`, pinned Tree-sitter grammars parse JavaScript and TypeScript syntax, imports and re-exports; without the extra, the index explicitly reports approximate pattern extraction. Neither mode supplies semantic retrieval or a complete call graph. Imports rank neighbouring files.

Existing approaches include [Aider’s repository map](https://aider.chat/docs/repomap.html), which ranks repository symbols and dependencies within a token budget, and [Repomix compression](https://repomix.com/guide/code-compress), which uses Tree-sitter to preserve code structure while removing implementation detail. Crewloom keeps its Python core dependency-free and makes the pinned syntax backend optional.

## Usage

```bash
crewloom map --project /absolute/path/to/git-project --query 'login authentication' --budget 8192
```

Without an installed CLI, use `python3 /path/to/crewloom/scripts/crewloom.py map ...`. An explicit existing Git project root is required, and that root must own a Git work tree. The JSON response contains the map and scan/selection statistics. Read this map first, then inspect only relevant source files and line ranges. Before editing, verify the actual implementation and dependencies: a map omits bodies and may miss definitions.

A managed `model` step can opt in with:

```json
{"repo_map": true, "repo_map_budget_bytes": 8192}
```

These fields supplement a normal model step; they are not a complete plan. The map guides the model but does not grant filesystem tools or silently choose additional input bodies. You still declare the full source files needed in `inputs`. The default is off because enabling it sends selected project symbol/path metadata beyond those input files to the configured provider. Review that scope before enabling it.

## Freshness and isolation

Each canonical project root owns `.crewloom/index/map.json`, a versioned generation carrying the generation, schema and parser versions plus the project and checkout identity. A foreign project or checkout identity is rejected; a corrupt cache is rebuilt explicitly; a legacy unbound cache from before binding adopts the new identity once. The cache stores extracted structure and SHA-256 fingerprints, not source bodies. Created, deleted and renamed files are reconciled, and branch switches are detected. Unchanged hashes reuse parsing results, while a parser version change forces a full reparse. Every refresh still reads candidate bytes to verify their fingerprints; this saves repeated parsing and model context, not all local disk reads.

Git lists tracked and nonignored untracked files and nominates changed, untracked, deleted and renamed paths; hashes decide freshness, never modification time or size. `.gitignore` applies to untracked files; tracked files can remain visible even if later ignored. `source_roots` and `exclude` in `crewloom.project.json` control the scan, and root aliases, symlinked roots and paths escaping the canonical root are rejected. Only Python/JS/TS extensions are indexed. Role installations, runtime metadata, dependencies and build directories are excluded; symlinked or hardlinked source files are rejected. This is not a secret scanner: symbol names and filenames can be sensitive even though source bodies and constant values are not emitted.

Git discovery follows the selected root, not the environment of the process that started it. Every Git child runs without `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_CEILING_DIRECTORIES`, `GIT_CONFIG`, `GIT_CONFIG_PARAMETERS` and the `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_n`/`GIT_CONFIG_VALUE_n` block, because a commit hook exports exactly those and an inherited override otherwise redirects discovery, fixtures and commits into the repository being committed. Author and committer identities, `PATH`, locale and time zone are preserved. The discovered repository must be the one the root's own `.git` marker names, with its work tree at that root: an inherited repository, a subdirectory of another checkout, a bare repository and a plain directory are all refused instead of mapped. Repository fixtures in the test suite start Git from the same cleared environment, so a fixture commit cannot land outside its temporary project.

Python extraction resolves relative and absolute imports inside the indexed layout. The optional JavaScript/TypeScript syntax backend resolves local imports, re-exports and aliases from supported project configuration. Configuration fingerprints participate in cache freshness. External packages, computed imports, unsupported resolution and syntax errors remain explicitly classified; approximate fallback is labelled and never reports complete syntax coverage. The map never claims a comprehensive graph. Seed files always appear as paths even when their symbol list exceeds the byte budget, and omitted or truncated records are counted.

Limits: 5000 source files, 1 MiB per file (larger files skipped and counted), 32 MiB total scanned content, 8 MiB cache and 1024–65536 bytes per rendered map. Oversized scans fail; rendered maps report omitted files. Use `source_roots` to scope a very large repository rather than dividing it. The map is advisory and does not replace project path enforcement or full rules.

## Local evidence

Regression cases cover generation and parser versions, equal-size edits, branch switches, renames, deletions, corrupt and foreign caches, unbound legacy caches, Python and JavaScript import resolution, standard-library imports treated as external rather than unresolved, syntax-error visibility, seed visibility under an oversized symbol block, budgets, unsupported roots, an exported foreign Git environment from either direction, nested and bare roots, linked worktrees, and explicit prompt opt-in. A source-level regression also refuses any test fixture that starts Git without an explicit environment. A reproducible cold/warm pilot reports measured index reuse, durations and context bytes; see [project context](PROJECT_CONTEXT.md). These comparisons show map size and parsing reuse, not measured token charges, end-to-end latency or answer quality.

Freshness checks recompute the candidate inventory with the same scope, exclusions, size caps, decodability and scan budgets this scan uses, so an out-of-scope or skipped file never invalidates a frozen generation while an in-scope create, delete, rename or budget change always does. Caps are enforced before a candidate is read and every candidate byte counts against the aggregate budget, including bytes a failing UTF-8 decode later discards.
