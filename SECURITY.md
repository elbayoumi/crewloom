# Security

Treat role instructions as task guidance, not authorization to act on external systems. Inspect tools, permissions, dependencies, and side effects before execution. Use a bounded test workspace for evaluation.

Do not put secrets, private customer records, credentials, or sensitive execution logs into public memory, examples, or issues. Repository checks are not an execution sandbox.

The dashboard gives launched tools a copy of its environment without the dashboard token or secret-named variables and redacts credential-shaped text from stored output; this is defense in depth, not a guarantee that every secret is recognized. The Chrome companion needs `<all_urls>` to capture the visible tab and index pages, starts disabled, and acts only after explicit enablement; install it only in a browser profile you are willing to expose to that scope. The `reverse-engineering-analyst` role runs a separate analysis tool such as REA with your permissions and no sandbox, so open hostile samples in a disposable VM or container.

Report sensitive findings through GitHub private vulnerability reporting if enabled. Otherwise ask the repository owner for a private channel without posting exploit details or private records. No dedicated external reporting inbox is configured.
