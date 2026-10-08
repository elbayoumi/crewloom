# Controlled context study

A paired, tool-free experiment: does giving a host the complete source of a small
project, instead of a selected navigation map over that same project, change the
measured cost and the measured quality of the artifact it produces?

This document is the public protocol. The frozen task contracts and the held-out
acceptance cases are supervisor-owned and read-only; the study reads them, verifies
their digest, and never writes them.

## What the study is not

- It is not a claim about any model, provider or product. Three small synthetic
  development tasks over one nine-module fixture project support a paired
  comparison inside this repository and nothing wider.
- It is not a billing statement. Cost is reported only as a provider actually
  reported it; an absent count stays `null` and is never replaced with `0`.
- It is not an agent benchmark. Generation is tool-free text; there is no
  navigation tool, no filesystem tool and no autonomous loop.
- Standard CI never runs it. It spends provider quota and produces per-trial
  evidence, so it is an operator command.

## Held-out quality

33 frozen cases across three tasks, 11 each, are shipped as grader-only packaged
data at `examples/context-study/grader/contract.json` (SHA256
`ec385875a0354567f0e95e013f6a8daa03b66e055745600c5b89cf762b381c9a`).
`evaluate_hosts.study_contracts()` refuses to run when those bytes differ.

The resource lives in `examples/`, not in `.crewloom/`, because a distribution
prunes private runtime state: reading the held-out cases from a pruned path made
the study unrunnable from an installed wheel. The bytes are identical to the
supervisor original at
`.crewloom/production-foundation/STUDY_TASK_CONTRACTS.json`, which stays
untouched. In the producer checkout, `test_context_study.py` also compares that original when it exists. A clean public export instead verifies the frozen public SHA and packaged-resource acceptance without requiring any private file. No packaging
metadata change is needed: `MANIFEST.in` already ships `examples/**` and
`pyproject.toml` already declares `examples/**/*.json` as package data.

The resource sits outside `examples/context-study/project/`, so it cannot be
picked up by the fixture source inventory, and `study_contracts()` refuses a
contract path that resolves inside the fixture.

| Task | Output | API |
| --- | --- | --- |
| `invoice-summary` | `src/ledger.py` | `summarize(records)` |
| `dependency-order` | `src/scheduler.py` | `plan(tasks)` |
| `project-path` | `src/paths.py` | `resolve_project_path(root, relative)` |

The cases, their inputs and their expected values never appear in a generation
prompt or in the fixture source inventory. A prompt is built from exactly
`task_id`, `api`, `contract` and `output`; the fixture tree carries no oracle.

## The two conditions

Both conditions carry **byte-identical mandatory content**: the task contract, the
rules, the acceptance criteria, the declared output, the complete body of the
REQUIRED helper module and one inventory digest over every fixture module. Only the
treatment differs.

| | `full-source` | `selected-map` |
| --- | --- | --- |
| Contract, rules, criteria, output | identical | identical |
| REQUIRED helper body | complete | complete |
| Other modules | complete source of every module | symbol navigation only, bounded budget |
| Navigation source | none | `repo_map.build` + `repo_map.render` over the same fixture |

The treatment is never manufactured: no prompt is padded, no mandatory content is
trimmed, and the navigation text comes from the real project index with its real
statistics, index configuration digest and graph-completeness flag. On this fixture
the difference is roughly 20 KB against roughly 8 KB per prompt.

## Frozen before the first call

`protocol.json` in the evidence directory records, before any provider call:
the contracts path and digest, the fixture module list and the SHA256 of every
fixture module plus the declared helper of each task, the SHA256 of this study's
grader module, of the transport module, of the container executor
(`scripts/workflow.py`) and of the grading module, the SHA256 of both in-container
harness sources, the resolved container image id, the seed, the balanced trial
order, the requested models and the SHA256 of all six prompts together with a
`mandatory_sha256` per task that must be equal across its two conditions.

Planned calls: 2 available hosts × 3 tasks × 2 conditions × 3 repeats = **36**,
shuffled once with the frozen seed `20261004`. Requested models are frozen before
any call and never substituted: Codex `gpt-6-sol`, OpenCode
`opencode/space-bunny-free`. Claude is absent because its local login is
unavailable; its absence is recorded, not measured.

## Running it

```bash
python3 scripts/evaluate_hosts.py --study --output /path/to/fresh-evidence \
    --study-host codex --study-host opencode
```

Useful flags: `--repeats` (default 3), `--seed`, `--image`, `--timeout` (default
300 s), `--case-runs` (default 1; the graded APIs are deterministic, so the
container is the isolation boundary rather than a sampling device).

The standalone command above exposes study mode. CLI forwarding is verified separately
from transport and scoring, and the original role-control benchmark remains available.

## Evidence written per trial

`protocol.json`, `contracts.json`, `prompt-<task>-<condition>.txt`, `results.json`,
`report.json`, and one directory per trial containing the generated artifact, the
exact prompt, bounded `stdout` and `stderr` from the transport, and `grade.json`.

Every trial row records its order, seed, host, task, condition, repeat, context
bytes, mandatory digest, source SHA256, requested model, reported model, host
version, normalized input/cached/cache-write/output/reasoning/total tokens, cost,
generation duration, grading duration, held-out pass count, raw paths and error.

Transport logs are retained only because the study asked for them. Host output can
contain configuration, so review an evidence directory before publishing it.

## Failure accounting

- Every planned trial appears exactly once in `results.json`. Nothing is
  regenerated, replaced, reworded or re-run on a different model.
- A failed quality grade is retained in its denominator.
- A generation or transport failure is retained with its error.
- An unavailable host or missing local login (`model_host.HostUnavailable`) stops
  only that host. Its remaining trials are recorded as `host-unavailable`, they
  stay in the denominator, and the other host continues.
- There is no early stopping after a failed grade and no automatic retry.

## The quality trust boundary

The candidate is untrusted content. The expected values never enter its container.

- The grader is called with only the candidate bytes, the task identity, the image
  id, the timeout and the fixture path. The host and the condition are not
  arguments, are not staged files, and do not appear in any staged byte.
- Each case runs in its own container: network none, read-only container root,
  dropped capabilities, pid, memory and CPU limits, a timeout, and the project
  staged as the only mount.
- **The stage is mounted read-only with no writable path anywhere.** The executor
  is called with `writable=()`, which adds `readonly` to the bind mount and no
  read-write sub-mount. File modes are *not* the boundary: the candidate owns the
  stage and can raise its own modes again, so a read-only mount is what actually
  refuses `open`, `chmod`, `unlink` and `mkdir`. `_seal_stage()` still clears every
  write bit, but only as defence in depth.
- The stage declares the executor's own `/workspace/.crewloom` mountpoint before it
  is sealed, because the runtime creates that path inside a mount it may no longer
  write to.
- Every staged regular file is fingerprinted before and after every run, **the
  trusted harness included**. Excluding the harness would let a candidate rewrite
  the checker and return its own verdict without the fingerprints noticing. A
  successful rewrite is detected and the case scores zero.
- The staged candidate receives the helper modules, the current case input, the
  filesystem fixture and the invocation harness. No oracle, no other case, no
  reported grade.
- The candidate runs as a child process of the in-container harness with its own
  captured output, and returns its value over a dedicated descriptor the parent
  holds open. It cannot hand the harness a result of its own choosing, cannot
  write the harness, and cannot publish a pass counter.
- The harness publishes a **typed outcome envelope** it builds itself:
  `{'outcome': 'value', 'value': ...}`, `{'outcome': 'raised', 'exception': ...}`
  or `{'outcome': 'input-mutated'}`. A single-key `error` object in the frozen
  contract therefore means *raise the built-in exception of that name*, and a
  candidate cannot satisfy it by returning `{'error': 'ValueError'}`. A raised
  exception is named only when it is the identical built-in; a class the candidate
  defined under the same name, or a subclass, is reported module-qualified and
  never matches. Only these three shapes are accepted from the descriptor.
- The supplied input is compared after the call on **every** path, including one
  that raised. A correct answer computed from an input the candidate then emptied
  scores zero, and so does an input emptied before the documented refusal is
  reported.
- Comparison is external and type-aware: `True` is never accepted where `1` is
  required.
- Malformed output, no output, a nonzero exit, a timeout and a missing attribute
  are honest failures with the reason recorded, never a partial pass.

This is task-contract acceptance with real containers, not proof against arbitrary
adversarial software in a same-user container, and not an OS-level sandbox around
the generation host.

## Reported measurements

`report.json` groups by host, task and condition with planned, scored and failed
counts, status counts, mean held-out pass rate, context bytes, and mean, sample
count and sample variance for each usage count, cost, generation duration and
grading duration. `pairs` holds the per-host, per-task full-source minus
selected-map differences over matched repeats, again with sample counts and
variance. A metric a provider never reported has `reported: 0` and a `null` mean.

The held-out mean is conditional on **scored submissions**. Provider failures and unattempted host-unavailable rows remain in planned/status counts; they are not assigned invented quality scores. Quality pairing includes only repeats scored in both conditions, while token pairing includes only repeats with both actual counts. Report those sample sizes and generation success separately. A conditional quality tie does not erase failed generation attempts.

## Host boundary

The Codex and OpenCode adapters run installed CLIs, which is the explicit operator
exception, not an OS sandbox. OpenCode additionally runs in a fresh scratch
directory outside the checkout, with a task-scoped `XDG_CONFIG_HOME`, a deny-all
agent profile, `tools.skill` disabled, `--pure`, and the binary's own disable
switches for Claude integration, external skills, project discovery and default
plugins. `HOME` and `CODEX_HOME` are never changed, no user authentication file is
read or copied, and no global configuration is edited. Managed administrative
settings still win; a failed isolation rejects the measurement rather than
overriding policy.

Requested model and reported model are separate fields. A stream that carries no
model metadata reports `model_reported: null`; the request is never substituted
for it.

## Offline checks

```bash
python3 -m unittest discover -s scripts -p test_model_usage.py
python3 -m unittest discover -s scripts -p test_context_study.py
CREWLOOM_DOCKER_TESTS=1 python3 -m unittest discover -s scripts -p test_context_study.py
```

`test_model_usage.py` pins provider usage normalization, the tool-free transport
refusals, the deny-all profile, the task-scoped environment and Python 3.9 grammar
compatibility. `test_context_study.py` pins the frozen protocol, the packaged
held-out resource, held-out separation, condition parity, the blind and
non-self-graded grader, the read-only stage mount, harness fingerprint coverage,
the exception-semantics envelope and the post-call input comparison, the Docker
proof with correct, wrong, grade-spoofing, input-mutating, mode-escaping and
crashing candidates, and collection accounting with a stubbed provider. The
Docker-graded cases skip unless `CREWLOOM_DOCKER_TESTS=1`.

`test_context_study.py` includes one differential that cannot pass on file modes
alone: the candidate raises its own modes, attempts a write, and returns the
reference answer only if that write is refused. A read-write mount scores zero on
all eleven cases; a read-only mount scores eleven.

### Python 3.9

The supported floor is Python 3.9, which the syntax check alone does not prove:
`ast.parse(..., feature_version=(3, 9))` accepts syntax that the 3.9 runtime does
not implement. `_stage_filesystem()` therefore builds the `hardlink` fixture with
`os.link()` rather than `Path.hardlink_to()`, which is 3.10+. Verified on a real
`python:3.9-slim` interpreter (3.9.25): the harness grades a correct reference
answer, `os.link` produces a file with `st_nlink == 2`, and `evaluate_hosts`
imports, resolves the packaged grader resource, reads the ten-module fixture
inventory and builds a prompt.

## Handoff to the coordinator task

Two items belong to files this study does not own:

1. `scripts/workflow.py:982` tests `step['host'] in ('codex','claude')` for the
   operator opt-in. It must consult the transport layer's own list instead:
   `if step['host'] in host_module.CLI_HOSTS and not allow_host_cli:`. Until that
   one-line change lands, a managed workflow step naming `host: opencode` reaches
   generation without `--allow-host-cli`, which `scripts/test_native_host_optin_boundaries.py`
   rejects. The authoritative list now lives in `model_host.CLI_HOSTS`.
2. `scripts/crewloom.py` exposes `evaluate-hosts` for the role-control benchmark
   only. Adding `--study` there means new subcommand arguments; study mode is
   currently reachable through the module CLI above.

Registry entries for the two owned modules, the two new test modules, this document
and `examples/context-study/*` also belong to the registry owner.

`examples/context-study/grader/contract.json` is now part of
`examples/context-study/*`, so it is covered by that registry entry.

## Observed outcome of the first frozen run (2026-10-05)

The preregistered 36-call run (seed 20261004, three synthetic tasks, no retries) is
recorded in `examples/evaluation/context-study-20261005.json`. It is **not complete**:
only Codex produced scored trials.

| Host | Condition | Scored / planned | Held-out pass | Input tokens (mean, scored) |
|---|---|---|---|---|
| Codex (`gpt-6-sol`) | full-source | 9 / 9 | 11/11 in every trial | about 14,000 |
| Codex (`gpt-6-sol`) | selected-map | 8 / 9 | 0/11 in every trial | about 11,700 |
| OpenCode (`opencode/space-bunny-free`) | both | 0 / 18 | none scored | not reported |

Reading this honestly: the selected-map input was about 22% smaller, but every scored
selected-map trial failed all held-out checks, so no like-for-like saving exists and none
is claimed. The cause is verified from the stored artifacts: required helper bodies were
present in both arms, but all eight scored selected-map modules imported helpers in a relative
form (`from .money import ...`) and raised `ImportError` on every held-out case, while every
scored full-source module used the package form shown in the other modules (`from src.money
import ...`). The selected-map prompt carried no example of that form, so the arm measured a
missing convention rather than missing logic. OpenCode failures were 14 malformed structured responses
and 4 timeouts. Neither host reported cost. Do not cite this run as evidence of token
savings, speed or general quality.

The next arm was designed in [CONTEXT_STUDY_V2_DESIGN.md](CONTEXT_STUDY_V2_DESIGN.md); the
design changes no v1 result above, and the v2 run that followed is recorded at the end of this page.

## Study v2 status

The v2 study has been run once (2026-10-06); its outcome is recorded at the end of this page.
It is a preregistered one-time run: do not repeat it to improve its numbers, and treat a new
protocol, not a rerun, as the way to ask a different question. Before that run:

The closure map, its prompt arm, the v2 plan and the offline sufficiency gate are implemented
and pinned by `scripts/test_study_closure_map_boundaries.py`. On the fixture the closure-map
prompts are 11.2 to 11.5 KB against 20.8 to 20.9 KB for full source and 8.2 to 8.6 KB for the v1
selected map, and the gate rejects the v1 selected-map prompt for all three tasks and accepts
full-source and closure-map. These are prompt sizes and a static check, not token savings or a
quality result. The run that supplied the quality and token measurements is described below.

### Running study v2

```bash
python3 scripts/evaluate_hosts.py --study-v2 --output <fresh private path> --study-host codex
```

The command uses the preregistered seed `20261006`, the arms `full-source` and `closure-map`,
three repeats per task and arm, and 18 calls for one host. Before the output directory exists
and before any provider call, it runs the offline sufficiency gate on the real prompts against
the frozen references and stops with an error when any arm is short of what its reference
imports. `protocol.json` additionally records the gate result, the SHA256 of each reference and
the SHA256 of `scripts/repo_map.py` (the map generator). Failures stay in the denominators; no
trial is retried or replaced. `--study` still runs v1, and passing both flags is refused.

After the last trial the runner recomputes every frozen input (fixture modules, helpers, the prompt
files on disk, grader, transport, executor, map generator and references) and writes
`verification.json`. If anything changed while the study ran, it raises an error naming every
changed item and publishes no `report.json`; `results.json` keeps the trials already measured.

## Observed outcome of study v2 (2026-10-06)

The preregistered 18-call run (seed 20261006, Codex `gpt-6-sol`, no retries) completed with all
18 trials scored and every frozen input verified unchanged afterwards. The offline gate passed
for every task and arm before the first call. The sanitized record is
`examples/evaluation/context-study-v2-20261006.json`.

| Arm | Held-out checks passed | Mean input tokens | Mean output tokens | Mean generation time |
|---|---|---|---|---|
| full-source | 99 / 99 | 14,941 | 868 | 31.0 s |
| closure-map | 99 / 99 | 12,194 | 876 | 31.7 s |

What this supports: on these three synthetic tasks the closure map lost no held-out quality and
used 2,731 to 2,767 fewer input tokens (about 18%) in every one of the nine pairs, which follows
its smaller prompt (11.2 to 11.5 KB against 20.8 to 20.9 KB). What it does not support: a quality
gain (both arms are at the ceiling), a cost saving (the host reported no cost), an uncached-token
saving (those vary with prompt-cache hits, paired differences from -6,067 to +11,599) or a speed
gain (no difference). One host, three tasks and three repeats limit any wider claim; harder tasks
are needed to separate the arms on quality.

### Why the OpenCode trials failed, and what changed

The 14 refused OpenCode generations of the v1 study all finished normally and each invented its own
response shape (13 flat `{"src/x.py": "..."}` maps and one `{"files": ...}`). Codex and Claude receive
the artifact schema through a CLI flag; `opencode run` has none, and the prompt only said "matching
the schema" without stating it. The 4 timeouts (about 300 s each) are a separate cause and are not
addressed by this change. The OpenCode transport now states the exact shape and the declared paths in
the agent's system prompt, in the task-scoped profile file; the user message stays the study prompt
byte for byte and appears once in argv, so a frozen study prompt is unaffected. Other hosts are
unchanged and every invented shape is still refused. The change is verified against a stand-in
executable that answers by what it was shown; whether a real model now follows the stated shape is
checked separately.

## New limited live smoke — 2026-10-08

A separate six-request smoke protocol reused the closure prompt and frozen grader on one invoice task; it did not repeat or replace the preregistered study v2 above. [Sanitized observations](../examples/evaluation/live-smoke-20261008.json) preserve scored, failed and not-dispatched conditions.

| Available Codex arm | Held-out checks | Reported input tokens | Reported output tokens | Prompt bytes | Generation ms |
|---|---|---:|---:|---:|---:|
| Full source | 11/11 | 16,261 | 938 | 23,471 | 91,485 |
| Closure map | 11/11 | 12,991 | 934 | 12,449 | 67,005 |

This single successful pair used3,270 fewer input tokens (20.1095%) with equal task acceptance. The known incorrect candidate passed1/11. No cost was reported; model identity remains unknown, and requested defaults are not reported identity. One pair and a public fixture do not establish statistical significance, quality superiority, general speed or billed savings. Failed authentication records have unknown usage, so total-run token/cost savings are not calculable.

Claude local authentication was absent: its attempts failed, and the remaining Claude condition was not dispatched after failure. There is no complete cross-provider comparison. A distinct before-call addendum used the two remaining requests for a real same-host manual handoff/application acceptance; it did not replace failed trials. The shared controller ledger charged6/6 reservations and refused a seventh. This ceiling counts managed requests, not undocumented internal native CLI steps or money spending. Raw prompts, payloads, generated application and run history remain solely in the independent project's ignored state.
