# Managed execution enforcement

Managed command steps execute against a temporary snapshot containing only declared inputs. The project directory is never mounted. The snapshot is read-only except for individual declared output files. The trusted broker validates nonempty output bytes, input fingerprints and destination paths before publishing artifacts. Failed commands publish nothing. Multi-file publication is not an atomic filesystem transaction.

Containers have no network, Docker socket or forwarded host environment. Their root filesystem is read-only; capabilities are dropped, privilege escalation disabled, and runtime metadata hidden. Limits are 1 GiB memory, two CPUs, 128 processes, 128 MiB temporary storage, and 4 MiB per writable file. Plans set a wall timeout of 1–3600 seconds. Declared inputs total at most 16 MiB; outputs total at most 4 MiB; each set contains at most 128 files. Inputs and existing destinations cannot be hardlinks; redirected output paths are rejected. Outputs cannot modify the trusted Crewloom checkout.

Commands must write declared files in place. Atomic rename over bind-mounted output files and undeclared build artifacts are unsupported. Use `/tmp` for intermediate work, then copy results into the declared files. Include imported modules and configuration in inputs.

## Model generation

Managed `model` steps default to tool-free provider RPC. Set `host` to `openai` or `anthropic`, specify an explicit supported `model` identifier, and configure `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` locally. Do not put credentials in plans. The provider receives the selected prompt and declared textual inputs; it receives no filesystem, shell, browser or delegated-agent tools. Returned artifacts must match the declared output schema and pass the same publication broker.

Requests use fixed HTTPS endpoints without redirects or ambient proxies. Responses are capped at 2 MiB, prompts at 256 KiB and generated output at 4096 tokens. A killable worker enforces the wall timeout. The project ledger permits at most 32 model attempts across workflow IDs; two failures with unchanged evidence block retries. These limits are not a dollar spending cap: configure account spending controls with the provider.

Native `codex` and `claude` CLI steps are rejected by default. The operator can explicitly pass `--allow-host-cli` for compatibility with existing plans. This runs an external host outside the enforced model boundary. A plan cannot enable that exception itself. Historical CLI evaluations establish their recorded results, not enforcement by this provider gateway.

## Trust boundary

Docker, the operating system, the trusted broker and the person operating the host remain trusted. Manual task steps and agents with arbitrary host access are outside this boundary. Repository instructions cannot force such agents to obey. Project locks coordinate this runner; they do not protect against another host process modifying files. Review declared inputs before sending them to an external provider. Provider authentication and live model success require local credentials; mock transport tests alone do not establish either.

Self-Editing Mode should produce changes in a separate project or Git worktree. Review and test the resulting changes before updating the trusted runtime. Running a model with write access to its own active enforcement code would invalidate this boundary.
