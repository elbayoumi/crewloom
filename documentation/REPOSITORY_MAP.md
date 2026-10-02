# Project repository maps

A repository map is a navigation index: relative file paths, definition names and line numbers. Crewloom can build one locally without sending source code to a service or executing project code. Python uses the standard-library AST; JavaScript and TypeScript use approximate pattern extraction. This is not Tree-sitter, semantic retrieval or a complete call graph. Imports provide a basic ranking hint for neighbouring files.

Existing approaches include [Aider’s repository map](https://aider.chat/docs/repomap.html), which ranks repository symbols and dependencies within a token budget, and [Repomix compression](https://repomix.com/guide/code-compress), which uses Tree-sitter to preserve code structure while removing implementation detail. Crewloom’s initial implementation keeps the core dependency-free; these tools are alternatives when richer language analysis is needed.

## Usage

```bash
crewloom map --project /absolute/path/to/git-project --query 'login authentication' --budget 8192
```

Without an installed CLI, use `python3 /path/to/crewloom/scripts/crewloom.py map ...`. An explicit existing Git project root is required. The JSON response contains the map and scan/selection statistics. Read this map first, then inspect only relevant source files and line ranges. Before editing, verify the actual implementation and dependencies: a map omits bodies and may miss definitions.

A managed `model` step can opt in with:

```json
{"repo_map": true, "repo_map_budget_bytes": 8192}
```

These fields supplement a normal model step; they are not a complete plan. The map guides the model but does not grant filesystem tools or silently choose additional input bodies. You still declare the full source files needed in `inputs`. The default is off because enabling it sends selected project symbol/path metadata beyond those input files to the configured provider. Review that scope before enabling it.

## Freshness and isolation

Each canonical project root owns `.crewloom/repo-map.json`. A root mismatch or redirected map path is rejected. The cache stores extracted structure and SHA-256 fingerprints, not source bodies. New and changed files are parsed; removed files are dropped. Unchanged hashes reuse parsing results. Every refresh still reads candidate bytes to verify their fingerprints; this saves repeated parsing and model context, not all local disk reads. Refresh before relying on line numbers after edits.

Git lists tracked and nonignored untracked files. `.gitignore` applies to untracked files; tracked files can remain visible even if later ignored. Only Python/JS/TS extensions are indexed. Role installations, runtime metadata, dependencies and build directories are excluded; symlinked or hardlinked source files are rejected. This is not a secret scanner: symbol names and filenames can be sensitive even though source bodies and constant values are not emitted.

Limits: 5000 source files, 1 MiB per file (larger files skipped and counted), 32 MiB total scanned content, 8 MiB cache and 1024–65536 bytes per rendered map. Oversized scans fail; rendered maps report omitted files. Use narrower Git project roots or divide very large projects. The map is advisory and does not replace project path enforcement or full rules.

## Local evidence

On Crewloom’s current development checkout, 55 code files totalled 178,673 source bytes. A 4096-byte budget rendered 19 file summaries in 4076 bytes. A second unchanged scan reused all 55 parsing results with zero parses. This comparison shows map size and parsing reuse, not measured token charges, end-to-end latency or answer quality. Seven regression cases cover freshness, deletion/addition, ignore rules, symlinks, project mismatch, bounded relevance, CLI flags and explicit prompt opt-in.
