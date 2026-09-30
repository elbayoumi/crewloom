#!/usr/bin/env python3
"""Find fixed-pixel CSS Grid floors without viewport bounds. Static syntax heuristic; rendered geometry needs separate browser inspection."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SOURCE_EXTENSIONS = {".css", ".scss", ".tsx", ".jsx"}
EXCLUDED_DIRS = {"node_modules", ".next", "dist", "build", ".git"}

# minmax( <first argument> , ...) — the first argument is the track's floor.
# A bare "200px" floor is unsafe (no viewport-relative ceiling); "min(200px, 100%)",
# "min-content", "max-content", "auto" or a percentage are all safe as-is.
MINMAX_FLOOR = re.compile(r"minmax\(\s*([^,()]+(?:\([^()]*\))?)\s*,")
BARE_PX_FLOOR = re.compile(r"^\d+px$")


def find_violations(text: str) -> list[tuple[int, str]]:
    violations = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in MINMAX_FLOOR.finditer(line):
            floor = m.group(1).strip()
            if BARE_PX_FLOOR.match(floor):
                violations.append((i, line.strip()))
    return violations


def source_files(root: Path) -> list[Path]:
    return [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SOURCE_EXTENSIONS
        and not any(part in EXCLUDED_DIRS for part in p.parts)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_dir)
    if not root.exists():
        print(f"ERROR: project dir not found: {root}", file=sys.stderr)
        return 2

    all_violations = []
    for path in source_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in find_violations(text):
            all_violations.append({"file": str(path.relative_to(root)), "line": line_no, "code": line})

    if args.json:
        import json
        print(json.dumps({"violations": all_violations, "pass": not all_violations}, ensure_ascii=False, indent=2))
    else:
        if not all_violations:
            print("PASS — no unguarded fixed-px grid floor found")
        else:
            print(f"FAIL — {len(all_violations)} unguarded fixed-px grid floor(s):")
            for v in all_violations:
                print(f"  {v['file']}:{v['line']}: {v['code']}")
            print("\nFix: wrap the fixed floor as minmax(min(Npx, 100%), 1fr) so it never "
                  "exceeds the viewport on a narrow screen.")
    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
