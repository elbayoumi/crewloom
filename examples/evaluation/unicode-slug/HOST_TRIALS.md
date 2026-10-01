# Repeated provider trials

```bash
crewloom evaluate-hosts --host codex --host claude --repeats 5 --output /tmp/crewloom-host-evidence
```

Authenticate both CLIs locally and prepare the Docker image first. You may pass `--codex-model` and `--claude-model` to freeze selected model identifiers. The command may consume provider quota; it starts no model calls in ordinary CI. Output requires a fresh destination and is never overwritten.

The coordinator freezes task, prompt and scorer hashes before generation, shuffles a balanced with/without-role matrix using a recorded seed, stores anonymized source submissions, then scores each in Docker using the existing deterministic evaluator. The grader receives source and image only. `mapping.json` is kept separate from submission score files; `report.json` joins labels only after scoring. Each repetition is a fresh generation, not a repeated score of one output. Two host failures skip remaining calls for that host and failed/blocked trials remain visible in requested-versus-scored totals.

This separates generation from acceptance scoring. It does not provide an independent human coordinator, private holdout cases or a broad software-quality comparison. The benchmark contract and acceptance cases are public. The with-role prompt is longer, model defaults can differ and a pass-rate tie does not establish benefit. Interpret outcomes only for this pure-function task and configuration. Costs not reported by a host remain unknown.
