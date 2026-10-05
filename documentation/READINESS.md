# Agency rollout readiness

`scripts/agency_readiness.py` answers one narrow preflight question for one agency client project: **does the existing project-control ledger register this exact project root under this exact ID, and does the state it records still describe the files on disk right now?** It is a reporter, not a rollout step. It never enrolls a project, never reconciles evidence, and never changes a control status.

```bash
python3 scripts/agency_readiness.py \
  --project-id sample-client \
  --project-root /agency/04_Clients/Active/Client_sample \
  --agency-root /agency \
  --registry /agency/.agents/project-control/registry.json
```

The JSON report goes to standard output and nothing else is touched. Add `--language ar` for Arabic human labels; the machine keys never change.

## Why a separate reporter

The project-control ledger already has one validator, [`project_binding.validate_agency_registry`](../scripts/project_binding.py), and one reader, [`project_binding.agency_registry`](../scripts/project_binding.py). The lifecycle uses both to decide whether a project may run in enforced mode. This reporter calls those same functions, so the ledger schema, its statuses, its relative-path rules and its evidence rules stay exactly one implementation, and the toolkit keeps no second client list.

It deliberately does **not** run the external agency validator that [`project_binding.run_agency_validator`](../scripts/project_binding.py) can execute for a lifecycle entry. That validator belongs to the agency and may write client state; a read-only preflight cannot depend on it. A ledger is therefore reported as *checked*, not as *passed*.

## Inputs

Every input is explicit. None is inferred from the working directory, a previous run, the registry's own location or a filename that looks similar.

| Flag | Meaning |
| --- | --- |
| `--project-id` | Exact registered project ID. Required; must match the ledger's identifier pattern. |
| `--project-root` | Existing canonical project root of that registration. Required. |
| `--agency-root` | Existing agency workspace root that holds the ledger. Required. |
| `--registry` | Explicit agency project-control registry file. Required. |
| `--max-evidence-age-seconds` | Explicit evidence age limit, an integer from 0 to 31 536 000. Default 2 592 000 (30 days); the effective value is always in the report. |
| `--report-out` | Optional report file inside the selected project's own `.crewloom/readiness` directory. Default: stdout only. |
| `--language` | `en` or `ar`; human labels only. |

The ledger entry keeps exactly the schema the adapter already validates: `id`, `active_dir`, `context_snapshot`, `delivery_owner`, `control_status`, `last_verified_at`, `next_action` and `state_evidence`. Duplicate IDs, unknown fields or entry fields, a registry that is not schema version 1, and a path that escapes the agency root are reported rather than repaired.

## What `ready` means, and what it does not

`outcome: ready` is scoped to **registration and evidence freshness**:

- the registry carries the exact schema, and exactly one entry resolves to this canonical root under this ID;
- `last_verified_at` and `state_evidence.observed_at` are parseable, timezone-aware, not in the future, and inside the explicit age limit measured against the real current UTC clock;
- the state evidence is a real, nonempty, single-link regular file inside its own `active_dir`, and its **current** digest still equals the recorded digest;
- the project carries a valid portable configuration and local binding for the same identity.

It does **not** mean:

- the delivery was verified, or the client's own acceptance ran;
- any host, CLI, credential or agent is configured or capable;
- the evidence file's contents are true — a matching digest proves only that the file is unchanged since it was observed;
- that the agency's own validator accepted the ledger (it is not run).

## Outcomes and exit codes

| `outcome` | Exit | Meaning |
| --- | --- | --- |
| `ready` | 0 | Every check above passed for this explicit identity. |
| `needs_reconciliation` | 2 | The ledger itself records `needs_reconciliation` or `blocked`. Reported as recorded; files are untouched. |
| `not_ready` | 2 | The check ran and found problems: missing fields, schema or identity conflicts, stale or future timestamps, a digest that no longer matches, an uninstalled owner role, unsafe or foreign paths, or required setup that is absent. |
| `blocked` | 2 | The registration could not be checked at all: an unusable project root, agency root, registry path, or unreadable ledger. |
| `error` | 2 | The request itself was malformed, for example an out-of-range evidence age limit. |

`problems` is a list of `{kind, field, detail, blocking}` records. `kind` is one of `schema`, `identity`, `status`, `path`, `hash`, `ownership`, `timestamp`, `stale`, `evidence`, `missing`, `setup`. `missing_fields` names the absent required fields on their own. The list is bounded at 200 entries; a truncated report sets `problems_truncated` rather than implying completeness.

Non-ready is the ordinary result of a preflight. Exit 2 means "ask the agency owner", not "something failed to run".

## Read-only is measured, not promised

The default invocation creates nothing and changes nothing:

- no `.crewloom` directory, `AGENTS.md`, `crewloom.project.json`, `.gitignore`, cache, binding or reconciliation state is created;
- no Git, network, Docker or host command runs, and no provider is contacted;
- no ledger entry, client file or status is written or transitioned;
- no directory is created even for the optional report: an operator who wants a stored report creates `.crewloom/readiness` first, with `crewloom project enter` or by hand.

The suite in [`scripts/test_agency_readiness.py`](../scripts/test_agency_readiness.py) proves this by snapshotting every path under a synthetic agency workspace — kind, mode, size, mtime and content digest, including its `.git` directory — before and after a run, and comparing the two. Missing project configuration or binding is reported as `required setup`; the reporter never creates one, and a `blocked` or `not_ready` verdict never becomes `ready` as a side effect of running it.

## The one optional write

`--report-out` writes a single owner-only (`0600`) JSON file, staged beside its destination and moved into place with one atomic replace, and only when all of the following hold:

- the same explicit project ID and canonical root resolve to a valid registration **again**, at write time, through the same adapter;
- the path is selected-project relative and lies inside that project's own `.crewloom/readiness` directory, which is the only namespace this reporter owns;
- no component is a symlink, the destination is not a hardlink, and it is not inside `.git` or inside the shared Crewloom runtime, installed roles or installed documentation.

The owned namespace is the rule that keeps a report from ever replacing runtime authority: `.crewloom/binding.json`, `.crewloom/reviewers.json`, `.crewloom/active_task.json`, controller state and any other runtime file are refused, and a `..` component cannot turn an owned path into a binding write. A refused or failed write is reported in `write.status` and on standard error, and makes the exit code 2. It never downgrades to a silent success and never falls back to another path. Bounded output: a report larger than 256 KiB is refused rather than truncated.

## Reusing it

```python
import agency_readiness as readiness

payload = readiness.report('sample-client', '/agency/04_Clients/Active/Client_sample',
                            '/agency', '/agency/.agents/project-control/registry.json',
                            max_evidence_age_seconds=604800)
if not payload['ready']:
    print(payload['outcome'], payload['missing_fields'], payload['problems'])
```

`report(...)` returns the same dictionary the CLI prints and writes nothing. `now=` injects a timezone-aware instant so an age boundary can be tested deterministically; without it the real current UTC clock is used. `store_report(payload, project_root, relative)` is the guarded write, for callers that want the file rather than stdout.

## Known limitation

The agency inventory reviewed while this reporter was written holds **four** registered projects, **all** of them in `needs_reconciliation`, and no owner has selected a current-state evidence root for any of them. No client in that inventory can therefore be reported `ready`, and none is: the reporter has no authorized identity or current evidence for them, and it will not guess either. That private inventory is read-only to this tool; this public guide carries counts and the limitation only, never client names or private paths.