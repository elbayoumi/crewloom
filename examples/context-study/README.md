# Controlled context study

Fixtures and grader data for the controlled context study. Read
`documentation/CONTEXT_STUDY.md` for the protocol, the frozen acceptance contract
and the reported limits.

```
project/   the synthetic source project every generation prompt is built from
grader/    the frozen held-out contract the trusted grader reads
```

`grader/contract.json` is grader-only data. It carries the 33 held-out cases and
their expected values, which must never enter a generation prompt or the
`project/` source inventory, and it is packaged because a distribution prunes the
private `.crewloom` state the supervisor original lives in. Both copies are
byte-identical and pinned by SHA256.

```
python3 -m unittest discover -s scripts -p test_context_study.py
```

The study itself is executed by the operator, never by standard CI, because it
spends provider quota and produces per-trial evidence:

```bash
python3 scripts/evaluate_hosts.py --study --output /path/to/fresh-study \
    --study-host codex --study-host opencode
```

No command in this directory contacts a provider.