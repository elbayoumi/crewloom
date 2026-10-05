# Acceptance criteria — ledgerline concurrent development batch

The coordinator records this file's digest with every task commit and with the reviewed
integration decision, so a change here invalidates the evidence instead of silently
redefining it. It is tracked at the base commit on purpose.

## Independent task `billing`

- `src/billing.py` exists, imports the shared `src/money.py` helper, and does not reimplement
  decimal parsing.
- Every amount in the report is a fixed-scale decimal string; no float reaches a total.
- A currency group's tax is the quantized sum of the unrounded per-line taxes, and the
  per-line-rounded alternative is reported next to it.
- A refund reduces its group's net, tax and gross, and a negative amount without the refund
  category is refused.
- An unknown or wrongly-cased currency, an unknown category, a float or non-finite amount, a
  boolean or out-of-range quantity and a tax rate above 100 are each refused by name.
- `tools/check_billing.py` runs inside the task's own container and exits 0.

## Independent task `planning`

- `src/planning.py` exists and reuses the shared `src/scheduling_support.py` validator.
- Order is dependency depth first, then descending priority, then lexical id; the same
  document planned twice returns the same result, including with the input reversed.
- Waves are the order chunked by an explicit capacity and never exceed it.
- A duplicate task, an unknown or self dependency, a boolean or out-of-range priority, an
  invalid id and a dependency cycle are each refused, and the cycle is named.
- `tools/check_planning.py` runs inside the task's own container and exits 0.

## Dependent task `report`

- `src/report.py` and `src/app.py` exist, build on the two ancestor modules already merged
  into this worktree, and change neither of them.
- The combined report carries real invoice totals and a real plan, in one language, with the
  Arabic and English section titles as complete translations of the same keys.
- An explicit language restyles the report and mutates no input it was given.
- `src/app.py` runs as a process, writes a UTF-8 report, and refuses a bad document with exit
  status 2 and one JSON error object instead of a traceback or a partial file.
- The ancestors' acceptance artifacts still describe exactly the module bytes on disk here.
- `tools/check_report.py` runs inside the task's own container and exits 0.

## Combined integration criterion

`tools/check_combined.py` and `tools/run_helper_tests.py` run once in the integration
worktree, over every merged task commit, and both must exit 0:

- all three generated modules and all three per-task acceptance artifacts are present, each
  per-task acceptance is accepted, and each recorded source digest equals the integrated
  bytes;
- the generated command produces the expected English and Arabic reports from the frozen
  samples, including the group total that differs from the per-line-rounded total, a
  mixed-currency document with a refund, and byte-identical output for two identical runs;
- the generated command exits 2 and writes nothing for a dependency cycle, an unknown
  payload field, a float amount, a boolean quantity and an unknown category;
- the frozen fixture tests for the two reused helpers still pass inside the integrated
  candidate.

Publication additionally requires an explicit reviewed decision over the exact base,
candidate head and diff digest, and moves the checked-out tree by one `--ff-only`
fast-forward. Nothing here is satisfied by the generator: every number above is produced by
running code.