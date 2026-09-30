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

# Tailwind min-width breakpoints. A class such as "lg:grid-cols-[minmax(0,1fr)_minmax(320px,1fr)]" only
# applies from that width up, so its fixed floors are safe while they sum to at most half the breakpoint
# (the other half is left for gaps, padding and the remaining tracks).
BREAKPOINTS = {"sm": 640, "md": 768, "lg": 1024, "xl": 1280, "2xl": 1536}
PREFIXED_ARBITRARY_GRID = re.compile(r"(?:^|:)(sm|md|lg|xl|2xl):grid-cols-\[")
FLOOR_PX = re.compile(r"minmax\(\s*(\d+)px\s*,")


def token_at(line: str, index: int) -> str:
    """The quote/space-delimited token containing ``index`` (one Tailwind class)."""
    start = max(line.rfind(c, 0, index) for c in " \t\"'`") + 1
    ends = [e for e in (line.find(c, index) for c in " \t\"'`") if e != -1]
    return line[start:min(ends) if ends else len(line)]


def guarded_by_breakpoint(line: str, index: int) -> bool:
    token = token_at(line, index)
    match = PREFIXED_ARBITRARY_GRID.search(token)
    if not match:
        return False
    floors = sum(int(n) for n in FLOOR_PX.findall(token))
    return floors * 2 <= BREAKPOINTS[match.group(1)]


def find_violations(text: str) -> list[tuple[int, str]]:
    violations = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in MINMAX_FLOOR.finditer(line):
            floor = m.group(1).strip()
            if BARE_PX_FLOOR.match(floor) and not guarded_by_breakpoint(line, m.start()):
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
