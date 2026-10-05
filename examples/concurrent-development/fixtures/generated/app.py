#!/usr/bin/env python3
"""ledgerline: build one invoice and execution-plan report from a JSON document.

    python3 src/app.py --data data/ledger_en.json --out artifacts/report.json
    python3 src/app.py --data data/ledger_ar.json --out report.json --language ar

Standard library only, no network, and no state outside the file it is told to write. A
refused document is reported as one JSON object on standard error with exit status 2, so a
caller never has to parse a traceback to learn why a report is missing.
"""
import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from billing import check_language  # noqa: E402
from report import build_report  # noqa: E402

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024


def load_document(path):
    """Read one JSON document, refusing an oversized, unreadable or non-object file."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError('--data needs a file path')
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError('input document is missing or redirected: ' + str(path))
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError('input document exceeds its size budget')
    try:
        value = json.loads(source.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('input document is not readable JSON: ' + str(exc)) from None
    if not isinstance(value, dict):
        raise ValueError('input document must be a JSON object')
    return value


def render(payload, language=None):
    """The report document as text; one place decides the JSON shape of the output."""
    if language is not None:
        check_language(language)
    return json.dumps(build_report(dict(payload, **({'language': language} if language else {}))),
                      ensure_ascii=False, indent=2, sort_keys=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build one ledgerline report.')
    parser.add_argument('--data', required=True, help='JSON document with invoice, tasks, capacity')
    parser.add_argument('--out', required=True, help='Where to write the report JSON')
    parser.add_argument('--language', default=None, choices=('ar', 'en'),
                        help='Report language; overrides the invoice language')
    args = parser.parse_args(argv)
    try:
        text = render(load_document(args.data), args.language)
        target = Path(args.out)
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + '\n', encoding='utf-8')
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    print(json.dumps({'status': 'written', 'report': 'ledgerline', 'path': args.out},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())