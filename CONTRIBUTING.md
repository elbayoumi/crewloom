# Contributing

Read [AGENTS.md](AGENTS.md), then inspect the relevant role and memory.

Use English for public developer documentation. Arabic examples and translations are welcome. Keep skill IDs, paths, and machine-readable values stable. Improvements should address concrete role behavior or executable tool use, not merely increase the number of files.

Before creating a script, check [the registry](.agents/CODE_REGISTRY.md). Register new reusable scripts with their purpose, path, and exact run command. Explain dependencies, inputs, output, errors, and side effects.

Run `python3 scripts/check_repository.py` before proposing a change. Add meaningful regressions for changed executable behavior. Distinguish structure, bounded tool use, host discovery, and full workflow evidence.

Keep customer data, secrets, and internal operational logs out of contributions. Preserve applicable third-party notices. Intentionally submitted contributions use Apache-2.0 unless explicitly stated otherwise; submit only material you have the right to contribute.

Enable `.githooks` locally and do not bypass failed checks. Describe the problem, resulting behavior, verification, and remaining limitations in pull requests.
