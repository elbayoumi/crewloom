#!/usr/bin/env python3
"""Static UI review hints, never acceptance. Exit 2 means unverified.

Whole-project regex cannot prove rendered layout, focus, accessible names or
visual quality. Findings need element-level browser review; no hints is not PASS.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SOURCE_EXTENSIONS = {".css", ".scss", ".tsx", ".jsx", ".html", ".vue", ".svelte"}
EXCLUDED = {"node_modules", ".next", "dist", "build", ".git"}
INTERACTIVE = re.compile(r"<(button|a)\b|<(input|textarea|select)\b", re.I)
PLACEHOLDER = re.compile(r"\[(?:todo|tbd|client[_ -]?logo|add text)[^\]]*\]", re.I)


def source_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_EXTENSIONS
            and not any(part in EXCLUDED for part in p.parts)]


def audit(root: Path) -> dict:
    files = source_files(root)
    if not any(p.suffix.lower() not in {".css", ".scss"} for p in files):
        return {"state": "unmeasured", "issues": ["No supported UI source files found"], "files": 0}
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files)
    issues: list[str] = []
    if not re.search(r"@media\s*\([^)]*width", text, re.I) and not re.search(r"(?:sm|md|lg|xl):", text):
        issues.append("No responsive breakpoint hint detected; intrinsic layout needs browser review")
    if INTERACTIVE.search(text) and not re.search(r":focus(?:-visible)?\b|focus-visible|focus:ring|aria-label=|aria-labelledby=", text, re.I):
        issues.append("No explicit focus or ARIA hint detected; check native accessible names and browser focus")
    if PLACEHOLDER.search(text):
        issues.append("Unresolved placeholder text detected in UI source")
    if re.search(r"<img\b(?![^>]*(?:alt=|aria-label=))", text, re.I):
        issues.append("Image without alt or accessible label detected")
    if re.search(r"<button\b[^>]*>\s*</button>", text, re.I):
        issues.append("Empty button detected")
    return {"state": "unverified", "issues": issues, "files": len(files),
            "findings_are_heuristic": True, "browser_review_required": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    if not root.is_dir():
        print("Project directory unavailable", file=sys.stderr)
        return 2
    result = audit(root)
    print(json.dumps(result, ensure_ascii=False) if args.json else
          f"{result['state'].upper()}: {result['files']} UI source files; " +
          ("; ".join(result["issues"]) if result["issues"] else "no static hints; browser review required"))
    return 2


if __name__ == "__main__":
    sys.exit(main())
