# Project-local data and publication privacy

Project code and intentional public deliverables belong in that project's repository. Private project memory, run history, local configuration, snapshots, caches, exports and backup copies belong in that project's canonical root and stay out of Git. Independent projects require independent roots/repositories; ignoring a second application inside the toolkit does not make it an allowed toolkit directory.

## Local organization

| Location | Purpose | Git policy |
| --- | --- | --- |
| `.crewloom/index/`, `.crewloom/context/` | Rebuildable maps, frozen context and generation history | Ignored |
| `.crewloom/tasks/`, `.crewloom/lessons/` | Project task records and verified local learning | Ignored; preserve and back up deliberately |
| `.crewloom/backups/`, `.crewloom/exports/` | Local copies and private exports when a workflow needs them | Ignored; placement policy, not a new automatic backup service |
| `.crewloom/worktrees/<batch>/<task>/` | Coordinator-owned separate task checkouts | Ignored in the parent project |
| `.agents/skills/<role>/brain/` or `.claude/skills/<role>/brain/` | Installed project-local role memory | Ignored in consumer projects |
| `.crewloom/binding.json`, local tokens and host receipts | Machine-local identity, credentials and runtime state | Ignored |
| `crewloom.project.json`, declarative policy configuration | Portable ID and reproducible source/policy settings | Trackable source; keep private payloads and credentials out of it |
| `.codex/hooks.json`, `.claude/settings.json`, `.claude/settings.local.json`, `.opencode/plugins/crewloom-lifecycle.js` | Local host configuration/control | Ignored in consumer projects |
| `.env`, `.env.*`, dependency/build/cache output | Local secrets or generated state | Ignored; secret-free `.env.example`/`.env.template` remain source templates |
| Source, role procedures, public examples and approved release assets | Reusable/public implementation | Versioned deliberately |

The toolkit's distributed role-memory templates and general library lessons are public source, not client records. Only the actual distributed toolkit checkout and its genuine linked Git worktrees receive that distinction; an unrelated project cannot select it by changing a project ID. Public fixtures must contain synthetic or explicitly approved data.

## Automatic protection

Role installation and project bootstrap append a final Crewloom-owned privacy block to the selected project's `.gitignore`, retaining existing rules. Both host role-memory paths are excluded. Repeating setup repairs negations appended afterward. Existing private files are preserved.

Before installation/bootstrap writes its outputs, its selected Git index is checked. Reserved local-state paths and all files currently ignored by project rules are refused if tracked, including `git add -f` additions and ignored custom configurations. Symlinked Git markers and unsafe ignore files are refused; inherited Git repository/index/configuration overrides are removed from Git child processes.

The toolkit's mandatory repository gate performs the same index check. It does not rely on `.gitignore` to decide which generated/private names are forbidden.

Consumer projects can use the read-only check in their own CI or existing pre-commit hook:

```bash
crewloom project privacy --project /absolute/path/to/project
```

Exit 0 means the exact selected Git index has no detected private/ignored tracked paths and representative effective ignore checks pass. Effective ignore coverage is evaluated from the `.gitignore` files staged in that index (nested rules and negations included) inside a scratch repository with system/global Git configuration disabled. `.git/info/exclude`, `core.excludesFile` and unstaged working-tree edits protect only this machine; they are reported as `local_only_ignore_probes`/`missing_portable_ignore_probes` and cannot make the project `ready`. Stage the ignore file (`git add .gitignore`) to publish the policy; nothing in the index or working tree is modified by the check. An ignore file with unresolved merge stages is reported in `unmerged_ignore_files` and is never `ready`. A staged nested ignore file that re-includes a private name the root policy ignores (for example `!.crewloom/` or `!.env.local` under `nested/`) is reported in `nested_negation_gaps`; harmless nested rules and unrelated negations are accepted. Exit 2 means tracked local data, missing ignore coverage, an unavailable index or a rejected request. A plain directory is not reported as a verified Git index. No files, Git configuration, index entries or existing hooks are changed by this command. The toolkit does not silently replace consumer hooks; connect this command to the selected project's existing hook/CI if commits must be blocked there.

This checks reserved paths, project ignore policy and known configuration names. It does not classify the contents of every arbitrary file, scan all secrets, constrain arbitrary host tools or remove already-published history. Put private payloads in the owned locations even when their names look like ordinary source files.

## Previously tracked data

An ignore rule does not remove a tracked file. Setup therefore refuses tracked data rather than silently deleting it or rewriting an index. After reviewing the exact selected project/path, preserve a local backup and remove only the intended file from that project's index:

```bash
git -C /absolute/path/to/project rm --cached -- path/to/private-file
crewloom project privacy --project /absolute/path/to/project
```

`--cached` preserves the local file. Review the staged removal before committing; prior commits still retain their contents. Do not use broad recursive untracking against an unselected project.

## Parallel tasks and copies

The coordinator gives each task a distinct checkout binding and writable memory. Model tasks seed the required roles' private memory from the same selected project into their own worktree; source guide files must already be part of its frozen Git base. Files are copied, never linked, and resume preserves task-local changes. The parent project's memory is not overwritten by the task, and these memory snapshots do not become task commits.

Avoid copying `.crewloom` or host state into another project. Moving a checkout requires explicit relocation. A fresh clone reuses its portable configuration and creates its own local binding; if the owner deliberately keeps configuration private, it needs explicit identity/configuration setup or a private restore. Identity is never inferred from an old chat or a matching directory name. Ignoring durable state is a publication rule, not a backup or retention system.


## Distribution archives

Wheels and source archives exclude private and generated content at any directory depth: `.crewloom`, `.git`, `node_modules`, `.next`, `build`, `dist`, virtual-environment, cache and `*.egg-info` trees, `.env`/`.env.*`/`*.env` files, run/event logs, bytecode, and every symlink (a link can carry content from outside the checkout). `.env.example` and `.env.template` remain source. The same predicate in `setup.py` filters the manifest (and therefore `SOURCES.txt`), the wheel's package data and the sdist copy, so a wheel rebuilt from the source archive is equally clean.

A reviewed public file whose name looks private is listed in `documentation/ARCHIVE_POLICY.json` (`approved_public_paths`, exact repository-relative paths) in a pull request that explains why it is safe. Nothing is approved today. The archive test builds real wheels and sdists with the setuptools builder inside the declared range, using a build input that still contains the private canaries.
