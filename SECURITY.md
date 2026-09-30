# Security

Treat role instructions as task guidance, not authorization to act on external systems. Inspect tools, permissions, dependencies, and side effects before execution. Use a bounded test workspace for evaluation.

Do not put secrets, private customer records, credentials, or sensitive execution logs into public memory, examples, or issues. Repository checks are not an execution sandbox.

Report sensitive findings through GitHub private vulnerability reporting if enabled. Otherwise ask the repository owner for a private channel without posting exploit details or private records. No dedicated external reporting inbox is configured.
