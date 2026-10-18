# Security

Treat role instructions as task guidance, not authorization to act on external systems. Inspect tools, permissions, dependencies, and side effects before execution. Use a bounded test workspace for evaluation.

Do not put secrets, private customer records, credentials, or sensitive execution logs into public memory, examples, or issues. Repository checks are not an execution sandbox.

The dashboard gives launched tools a copy of its environment without the dashboard token or secret-named variables and redacts credential-shaped text from stored output; this is defense in depth, not a guarantee that every secret is recognized. The Chrome companion needs `<all_urls>` to capture the visible tab and index pages, starts disabled, and acts only after explicit enablement; install it only in a browser profile you are willing to expose to that scope. The `reverse-engineering-analyst` role runs a separate analysis tool such as REA with your permissions and no sandbox, so open hostile samples in a disposable VM or container.

## Container Security and Rootless Isolation Policy

Crewloom enforces hardware- and OS-level execution sandboxing for autonomous workflows via Docker:

1. **Rootless & Non-Root Execution**:
   - Workflow containers refuse execution under host root (`uid == 0`).
   - The `--user` flag mirrors the unprivileged host user (`uid:gid`), preventing files created inside the container from escaping ownership bounds.
   - In containerized CI or Kubernetes environments where the host agent is already containerized, configure `userns-remap` in `/etc/docker/daemon.json` (`"userns-remap": "default"`) or run Docker-in-Docker in rootless mode (`dockerd-rootless.sh`) so that container UID 0 maps to an unprivileged subordinate UID range on the underlying host.

2. **Air-Gapped Network Bounds**:
   - All workflow containers run with `--network none`. Network egress and ingress are strictly disabled, eliminating arbitrary exfiltration of repository context or tokens.

3. **Strict Read-Only Filesystem & Mount Boundaries**:
   - The base project root is mounted read-only (`type=bind,src=...,dst=/workspace,readonly`) whenever writable paths are declared.
   - Writable subdirectories are mounted with exact, narrow paths (`safe_path` ensures no path traversal outside the project directory).
   - Comma characters (`,`) are strictly rejected in both source and destination mount paths to prevent mount option injection.
   - Internal runtime state (`/workspace/.crewloom`) is masked with a read-only tmpfs mount (`--tmpfs /workspace/.crewloom:ro,noexec,nosuid,size=1m`) to prevent containerized code from inspecting or tampering with coordinator credentials, state journals, or run history.
   - The container root filesystem is mounted strictly read-only (`--read-only`), with Linux capabilities dropped (`--cap-drop ALL`), `no-new-privileges` enforced, and scratch space restricted to a bounded `tmpfs` (`/tmp:rw,nosuid,size=128m`).

Report sensitive findings through GitHub private vulnerability reporting if enabled. Otherwise ask the repository owner for a private channel without posting exploit details or private records. No dedicated external reporting inbox is configured.
