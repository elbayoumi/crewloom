#!/usr/bin/env python3
"""Detect real layout-overlap bugs from a rendered-page DOM snapshot.

Consumes externally captured DOM rectangles. This tool does not render pages;
supply real browser snapshot evidence in the schema accepted below.

Rule: in normal document flow (position static/relative, float none),
sibling elements should never occupy overlapping screen space. Two such
elements with an intersecting bounding box means CSS overflow escaped its
container (e.g. `white-space: nowrap` text wider than its grid/flex cell) —
that is always a real bug, never a deliberate design overlay. Elements that
are each other's ancestor/descendant are excluded (nesting is not overlap).
Absolute/fixed/sticky-positioned elements are excluded from the comparison
entirely — the snapshot script already flags them as normalFlow: false.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MIN_OVERLAP_PX = 4  # ignore sub-pixel/anti-aliasing rounding noise


def rects_overlap(a: dict, b: dict) -> tuple[int, int] | None:
    ax1, ay1, ax2, ay2 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx1, by1, bx2, by2 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    ox = min(ax2, bx2) - max(ax1, bx1)
    oy = min(ay2, by2) - max(ay1, by1)
    if ox >= MIN_OVERLAP_PX and oy >= MIN_OVERLAP_PX:
        return (ox, oy)
    return None


def is_nested(a: dict, b: dict) -> bool:
    """Treat one rect fully containing the other as nesting, not overlap —
    a snapshot has no parent/child ids, so full containment is the only
    element-count-independent proxy available."""
    ax1, ay1, ax2, ay2 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx1, by1, bx2, by2 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    a_in_b = bx1 <= ax1 and by1 <= ay1 and bx2 >= ax2 and by2 >= ay2
    b_in_a = ax1 <= bx1 and ay1 <= by1 and ax2 >= bx2 and ay2 >= by2
    return a_in_b or b_in_a


def analyze(snapshot: dict, viewport_label: str) -> list[dict]:
    elements = [e for e in snapshot.get("elements", []) if e.get("normalFlow") and e.get("text")]
    findings = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            a, b = elements[i], elements[j]
            if a["text"] == b["text"]:
                continue
            if is_nested(a, b):
                continue
            overlap = rects_overlap(a, b)
            if overlap:
                findings.append({
                    "viewport": viewport_label,
                    "element_a": a["text"],
                    "element_b": b["text"],
                    "overlap_px": {"x": overlap[0], "y": overlap[1]},
                    "rect_a": {k: a[k] for k in ("x", "y", "w", "h")},
                    "rect_b": {k: b[k] for k in ("x", "y", "w", "h")},
                })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", action="append", required=True,
                         help="Path to a JSON file produced by layout_overlap_snapshot.js. Repeat once per viewport.")
    parser.add_argument("--viewport-label", action="append", default=[],
                         help="Label for each --snapshot in the same order (default: the snapshot's own recorded width).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.viewport_label and len(args.viewport_label) != len(args.snapshot):
        print("ERROR: --viewport-label count must match --snapshot count", file=sys.stderr)
        return 2

    all_findings: list[dict] = []
    for idx, path_str in enumerate(args.snapshot):
        path = Path(path_str)
        if not path.exists():
            print(f"ERROR: snapshot not found: {path}", file=sys.stderr)
            return 2
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
            return 2
        label = args.viewport_label[idx] if args.viewport_label else f"{snapshot.get('viewport', {}).get('w', '?')}px"
        all_findings.extend(analyze(snapshot, label))

    if args.json:
        print(json.dumps({"findings": all_findings, "pass": not all_findings}, ensure_ascii=False, indent=2))
    else:
        if not all_findings:
            print(f"PASS — no in-flow sibling overlap across {len(args.snapshot)} viewport snapshot(s)")
        else:
            print(f"FAIL — {len(all_findings)} overlapping element pair(s) found:")
            for f in all_findings:
                print(f"  [{f['viewport']}] \"{f['element_a']}\" overlaps \"{f['element_b']}\" "
                      f"by {f['overlap_px']['x']}x{f['overlap_px']['y']}px "
                      f"(rects: {f['rect_a']} vs {f['rect_b']})")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
