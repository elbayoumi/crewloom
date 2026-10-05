# Contract: `src/report.py` and `src/app.py`

Write exactly two modules: `src/report.py` and `src/app.py`. Standard library only, no
network, no state outside the file the command is told to write.

Both modules are built in a worktree that already contains the two modules this batch
generated before it, `src/billing.py` and `src/planning.py`, and their source is part of this
task's input. Read them and build on their public surface:

- `billing.compute_invoice(invoice)` and `billing.check_language(value)`;
- `planning.schedule(tasks, capacity)`.

Do not reimplement invoice arithmetic or planning, and do not change those modules.

## `src/report.py`

```python
PAYLOAD_KEYS = ('capacity', 'invoice', 'language', 'tasks')
SECTION_TITLES = {'en': {...}, 'ar': {...}}   # invoice, plan, summary, currencies, waves, latest_tasks

def build_report(payload) -> dict
```

- the payload is a JSON object; an unknown key is refused with `ValueError` naming it, and a
  missing or non-object `invoice` is refused;
- an explicit `language` overrides the invoice language and is validated with
  `billing.check_language`; when absent the invoice language is used;
- the invoice is handed to `billing.compute_invoice` and the tasks and capacity to
  `planning.schedule`, so every number in the report is produced by those modules;
- `payload` and `payload['invoice']` are never mutated — an override copies the invoice.

Output:

```python
{'report': 'ledgerline', 'version': 1, 'language': 'ar'|'en', 'titles': SECTION_TITLES[language],
 'invoice': <billing.compute_invoice(...)>,
 'plan': <planning.schedule(...)>,
 'summary': {'invoice_id': str, 'currencies': [...], 'gross_by_currency': {code: str},
             'invoice_lines': int, 'task_count': int, 'waves': int, 'priority_total': int,
             'latest_tasks': [...]}}
```

`titles` holds the localized section names for the one language of the report, and the
Arabic and English titles are complete translations of the same six keys.

## `src/app.py`

A command with an actual user interface:

```
python3 src/app.py --data data/ledger_en.json --out artifacts/report.json
python3 src/app.py --data data/ledger_ar.json --out report.json --language ar
```

- `--data` and `--out` are required; `--language` accepts `ar` or `en` and overrides the
  invoice language for the whole report;
- the input is one JSON object, read as UTF-8, at most 4 MiB; a symlinked or missing file is
  refused;
- the output directory is created when needed and the report is written as UTF-8 JSON with
  `ensure_ascii=False`, `indent=2` and sorted keys, so Arabic text is stored as Arabic and
  two runs are byte-identical;
- success prints one small JSON object `{"status": "written", ...}` on standard output and
  exits `0`;
- a refused document prints exactly one JSON object `{"status": "blocked", "error": "..."}`
  on standard error and exits `2` — never a traceback, and never a partial output file;
- `src/` is put on `sys.path` by the module itself, so `import billing` works when the command
  is started as `python3 src/app.py` from the project root.

Refusals the command must reproduce, not swallow: an unknown currency, an invalid category, a
non-integer quantity, an unknown `depends_on`, a dependency cycle, an unknown payload field
and a document that is not JSON.