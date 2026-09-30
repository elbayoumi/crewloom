#!/usr/bin/env python3
"""Find literal colors in UI source that are absent from the approved design tokens.

Static text check: it reads hex (#rgb, #rrggbb, #rrggbbaa) and rgb()/rgba() literals with numeric channels.
Named colors, hsl(), currentColor and computed styles are out of scope; confirm contrast and rendering in a browser.
Exit 0: no drift. Exit 1: literals outside the tokens. Exit 2: unverified (missing/invalid tokens or no source).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SOURCE_EXTENSIONS = {".css", ".scss", ".tsx", ".jsx", ".html", ".vue", ".svelte"}
CONFIG_NAMES = re.compile(r"^tailwind\.config\.(?:js|cjs|mjs|ts)$")
EXCLUDED_DIRS = {"node_modules", ".next", "dist", "build", ".git", ".venv", "venv", "site-packages", "coverage", "out"}

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*(?:[,/]\s*[\d.]+%?\s*)?\)", re.I)


def normalize_hex(value: str) -> str:
    """Lowercase six-digit RGB; the alpha channel of #rrggbbaa is ignored."""
    digits = value.lstrip("#").lower()
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits[:6]


def rgb_to_hex(r: str, g: str, b: str) -> str | None:
    channels = [int(r), int(g), int(b)]
    return "#%02x%02x%02x" % tuple(channels) if all(c <= 255 for c in channels) else None


def literals(line: str) -> list[str]:
    found = [normalize_hex(m.group(0)) for m in HEX.finditer(line)]
    found += [h for m in RGB.finditer(line) if (h := rgb_to_hex(*m.groups()))]
    return found


def token_colors(node) -> dict[str, str]:
    """Map normalized color -> token path for every hex/rgb string value in the token JSON."""
    colors: dict[str, str] = {}

    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else str(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif isinstance(value, str):
            for color in literals(value):
                colors.setdefault(color, path)

    walk(node, "")
    return colors


def source_files(root: Path, tokens: Path) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if not p.is_file() or any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        if p.resolve() == tokens.resolve():
            continue
        if p.suffix.lower() in SOURCE_EXTENSIONS or CONFIG_NAMES.match(p.name):
            out.append(p)
    return sorted(out)


def audit(root: Path, tokens_path: Path, allow: set[str]) -> dict:
    try:
        tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"state": "unverified", "error": f"cannot read tokens: {exc}"}
    palette = token_colors(tokens)
    if not palette:
        return {"state": "unverified", "error": "tokens file contains no color values"}
    files = source_files(root, tokens_path)
    if not files:
        return {"state": "unverified", "error": "no supported UI source files found"}
    violations, used = [], set()
    for path in files:
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            for color in literals(line):
                if color in palette:
                    used.add(color)
                elif color not in allow:
                    violations.append({"file": str(path.relative_to(root)), "line": line_no,
                                       "color": color, "code": line.strip()[:160]})
    unused = sorted(f"{palette[c]} ({c})" for c in palette if c not in used)
    return {"state": "drift" if violations else "clean", "files": len(files), "violations": violations,
            "unused_tokens": unused, "note": "static text check; verify contrast and rendering in a browser"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--tokens", required=True, help="approved design tokens JSON")
    parser.add_argument("--allow", default="", help="comma-separated extra colors to accept, e.g. '#fff,#000'")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_dir)
    if not root.is_dir():
        print(f"ERROR: project dir not found: {root}", file=sys.stderr)
        return 2
    allow = {normalize_hex(c.strip()) for c in args.allow.split(",") if HEX.fullmatch(c.strip())}
    result = audit(root, Path(args.tokens), allow)
    code = {"clean": 0, "drift": 1}.get(result["state"], 2)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["state"] == "unverified":
        print(f"UNVERIFIED — {result['error']}", file=sys.stderr)
    elif result["state"] == "clean":
        print(f"PASS — no literal color outside the tokens ({result['files']} files)")
    else:
        print(f"FAIL — {len(result['violations'])} literal color(s) outside the tokens:")
        for v in result["violations"]:
            print(f"  {v['file']}:{v['line']}: {v['color']}  {v['code']}")
        print("\nFix: use a token (CSS variable or class) or add the color to the approved tokens file.")
    if result.get("unused_tokens") and not args.json and result["state"] != "unverified":
        print(f"note: {len(result['unused_tokens'])} token color(s) unused (warning only)")
    return code


if __name__ == "__main__":
    sys.exit(main())
