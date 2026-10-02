# Repository architecture

[Public architecture](../documentation/ARCHITECTURE.md) describes the toolkit boundaries. [AGENTS.md](../AGENTS.md) is the single authority for agent behavior. Public role procedures and core tools improve in their existing paths; do not maintain duplicate versioned implementations.

Model generation passes explicit project text to a trusted CLI in a temporary directory; the artifact layer validates writes and the Docker executor verifies code. Host CLI flags are not an OS sandbox. Trial treatment labels remain outside the deterministic scorer.

Managed runs use tool-free provider RPC and declared-file container snapshots. Native CLI use requires an explicit operator exception. The trusted runtime cannot be a managed output destination.
