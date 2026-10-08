# Repository scope

The mandatory gate also rejects tracked private/generated paths and any file ignored by the selected project's current Git rules, including forced additions. See [project publication privacy](PROJECT_PRIVACY.md). This adds an index boundary to the existing directory-scope boundary.

`REPOSITORY_SCOPE.json` declares the only top-level directories and files that belong to this
toolkit checkout. `scripts/check_repository.py` and the pre-commit hook refuse anything else:
an unregistered directory or file, a foreign `project_id`, an absent or malformed contract,
names that differ only by case, and paths that escape the root. Ignoring a folder with
`.gitignore` does not register it.

Why it exists: an unrelated Android application was once committed under this repository's
Git root and reached `main`. The application now lives in its own private repository with its
own canonical root. Independent applications must not be added here.

Changing the scope is a reviewed change: edit `REPOSITORY_SCOPE.json` in a pull request and
explain why the new entry belongs to the toolkit. Build tools write `PKG-INFO` and `setup.cfg`
at the root of a source archive, so those two names are registered. The contract ships in the
wheel and source archive, so the same check runs from an installed copy.

This gate cannot stop a privileged host tool from writing outside it; it rejects the mistake
at commit time and in CI.
