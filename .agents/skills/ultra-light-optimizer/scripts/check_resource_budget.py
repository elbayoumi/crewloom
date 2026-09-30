#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crewloom ultra-light-optimizer — resource budget gate (stdlib only).

Scans a project dir for hard resource-waste patterns from
references/ultra-light-contract.md. Exit 0 = PASS, 1 = HARD violations,
2 = unverified (no scannable code files).
"""
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__",
             ".next", "dist", "build", ".claude", "uploads"}
SCAN_EXTS = {".js", ".jsx", ".ts", ".tsx", ".py", ".php", ".dart"}

PATTERNS = [
    ("R-HARD-01", "DB: SELECT * over-fetch (contract DB-1)",
     re.compile(r"(?i)select\s+\*\s+from")),
    ("R-HARD-02", "DB: query call inside loop (contract DB-2)",
     re.compile(r"(?i)(await\s+\w*(service|repo)\w*\.\w+\s*\(|await\s+[A-Z]\w*\.(findOne|findAll|findByPk|findAndCountAll|create|update|destroy|count)\s*\(|await\s+.*\.query\s*\(|Sequelize\.(literal|fn|col)\s*\(|\.findOne\s*\(|\.findAll\s*\()")),
    ("R-HARD-03", "DB: raw SQL without LIMIT/pagination (contract DB-3)",
     re.compile(r"(?i)(select\s+.+\s+from\s+\w+)(?!.*limit)")),
    ("R-HARD-04", "API: fetch/axios call inside loop (contract API-2)",
     re.compile(r"(fetch\s*\(|axios\.(get|post)\s*\()")),
    ("R-HARD-05", "Bundle: heavy full import lodash/moment (contract B-1)",
     re.compile(r"""require\s*\(\s*['"]lodash['"]\s*\)|from\s+['"]lodash['"]|require\s*\(\s*['"]moment['"]\s*\)|from\s+['"]moment['"]""")),
    ("R-SOFT-01", "Hygiene: console.log in code (contract B-4)",
     re.compile(r"console\.log\s*\(")),
]


def load_exceptions(path):
    """Parse exception file: RULE|path-substring|reason per line, # comments."""
    exc = []
    if not path:
        return exc
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        if len(parts) == 3:
            exc.append(tuple(parts))
    return exc


def is_excepted(hit, exceptions):
    return any(rule in hit and sub in hit for rule, sub, _ in exceptions)


def iter_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in SCAN_EXTS:
            continue
        if any(d in p.parts for d in SKIP_DIRS):
            continue
        yield p


LOOP_RX = re.compile(r"(?<![\w-])(for|while)(?![\w-])|\.map\s*\(\s*async|\.forEach\s*\(|for\s+.*\bof\b")
LOOP_WINDOW = 15  # DB/fetch hit must sit within N lines after a loop opener


def loop_regions(lines):
    """Return set of 1-based line numbers covered by a loop window."""
    covered = set()
    for i, ln in enumerate(lines, 1):
        if LOOP_RX.search(ln):
            for j in range(i, min(len(lines) + 1, i + LOOP_WINDOW + 1)):
                covered.add(j)
    return covered


def check_file(path: Path):
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return hits
    lines = text.splitlines()
    in_loop = loop_regions(lines)
    for pid, msg, rx in PATTERNS:
        for i, ln in enumerate(lines, 1):
            if not rx.search(ln):
                continue
            if pid in ("R-HARD-02", "R-HARD-04") and i not in in_loop:
                continue
            if pid == "R-HARD-03" and ("limit" in ln.lower() or "take" in ln.lower()
                                       or "paginate" in ln.lower() or "first" in ln.lower()):
                continue
            hits.append(f"{pid} {path}:{i}: {msg}")
    return hits


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", required=True)
    ap.add_argument("--exceptions", default=None,
                    help="exception file: RULE|path-substring|reason per line")
    a = ap.parse_args()
    root = Path(a.project_dir)
    exceptions = load_exceptions(a.exceptions)
    files = list(iter_files(root))
    if not files:
        print("UNVERIFIED: no scannable code files found")
        return 2
    hard, soft, excused = [], [], 0
    for f in files:
        for h in check_file(f):
            if "R-SOFT" in h:
                soft.append(h)
            elif is_excepted(h, exceptions):
                excused += 1
            else:
                hard.append(h)
    for h in sorted(hard) + sorted(soft):
        print(h)
    print(f"scanned={len(files)} hard={len(hard)} soft={len(soft)} excused={excused}")
    if hard:
        print("FAIL: fix HARD violations or document exception (contract §استثناء)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
