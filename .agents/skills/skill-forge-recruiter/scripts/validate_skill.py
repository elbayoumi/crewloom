#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crewloom skill-forge-recruiter — validate a repo skill against Crewloom standard."""
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BRAIN_FILES = ["ARCHITECTURE.md", "COMPLETED.md", "ROADMAP_TODO.md",
               "CHALLENGES.md", "IDEAS_VAULT.md"]


def check(skill: str) -> list:
    errors = []
    if not isinstance(skill, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', skill):
        return ['expected a stable skill ID, not a filesystem path']
    base = REPO / ".agents" / "skills" / skill
    sk = base / "SKILL.md"
    if not sk.exists():
        return [f"missing {sk}"]
    text = sk.read_text(encoding="utf-8")
    if not text.startswith("---"):
        errors.append("SKILL.md must start with --- at byte 0")
    m = re.search(r"\n---\s*\n", text[3:])
    if not m:
        errors.append("unclosed frontmatter")
    else:
        fm = text[3:m.start() + 3]
        if "name:" not in fm:
            errors.append("frontmatter lacks name:")
        if "description:" not in fm:
            errors.append("frontmatter lacks description:")
    body = text[m.end() + 3:] if m else ""
    if len(body.strip()) < 200:
        errors.append("body too short (<200 chars)")
    section_markers = {
        "Brain / working memory": r"برين|\bbrain\b|\bworking memory\b",
        "When to use / triggers": r"متى|\bwhen to (?:use|invoke)\b|\bactivation\b|\btriggers\b",
    }
    for label, pattern in section_markers.items():
        if not re.search(pattern, body, re.IGNORECASE):
            errors.append(f"body lacks section marker '{label}' (Arabic or English)")
    for bf in BRAIN_FILES:
        if not (base / "brain" / bf).exists():
            errors.append(f"missing brain/{bf}")
    if re.search(r"/home/(?!\.\.\.)[\w.~]|/Users/(?!\.\.\.)[\w.~]", body):
        errors.append("machine-local path in SKILL.md")
    return errors


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skill", required=True)
    a = p.parse_args()
    errs = check(a.skill)
    if errs:
        print(f"FAIL {a.skill}:")
        for e in errs:
            print(f"  - {e}")
        return 1
    print(f"PASS {a.skill}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
