#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crewloom context-guardian — build a minimal context pack for a skill."""
import argparse
import os
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

REPO = Path(__file__).resolve().parents[4]
BUDGET = 8000
SOURCES = ("SKILL.md", "brain/ARCHITECTURE.md", "brain/ROADMAP_TODO.md")


def rebase_links(text: str, source: Path, output: Path) -> str:
    """Rewrite source-relative Markdown links so they resolve from the pack location.

    The generator requires --out outside skill sources, so links copied verbatim
    from skill files would break wherever the pack lands. Only relative document
    links are rebased; URLs, anchors, mailto, absolute and template targets stay.
    """

    def replace(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        if re.match(r"(?:[a-zA-Z][a-zA-Z0-9+.-]*:|#|/|\{)", target):
            return match.group(0)
        rebased = os.path.relpath(source.parent / target, output.parent)
        return f"[{label}]({rebased})"

    return re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", replace, text)


def build_pack(base: Path, budget: int = BUDGET, output: Optional[Path] = None, language: str = "en") -> str:
    """Include whole sources or explicit read obligations, never chopped rules."""
    sources = [(rel, base / rel) for rel in SOURCES]
    for _, path in sources:
        if not path.is_file():
            raise ValueError(f"Required source missing: {path}")
    labels = {
        "en": ("# Context pack\n\nEach source is complete or explicitly referred for reading; never execute from truncated instructions.\nRead each referred source once; do not regenerate the pack to retrieve omitted content.\n\n", "Read entire source before execution", "complete"),
        "ar": ("# حزمة السياق\n\nكل مصدر كامل أو محال للقراءة؛ لا تنفذ من تعليمات مبتورة.\nاقرأ كل مصدر محال مرة واحدة دون إعادة توليد الحزمة.\n\n", "محال للقراءة الكاملة قبل التنفيذ", "كامل"),
    }
    if language not in labels:
        raise ValueError("Language must be en or ar")
    header, referred, complete = labels[language]
    sections = [f"## {rel}\n{referred}: {path}\n" for rel, path in sources]
    if len(header + "\n".join(sections)) > budget:
        raise ValueError("Budget too small for source references")
    for index, (rel, path) in enumerate(sources):
        content = path.read_text(encoding="utf-8")
        if output is not None:
            content = rebase_links(content, path, output)
        candidate = f"## {rel} — {complete}\n{content}\n"
        proposed = list(sections)
        proposed[index] = candidate
        if len(header + "\n".join(proposed)) <= budget:
            sections = proposed
    return header + "\n".join(sections)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="Read only this project’s installed role and memory")
    ap.add_argument("--skill", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--language", choices=("en", "ar"), default="en")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", a.skill):
        ap.error("Invalid skill name")
    base = REPO / ".agents" / "skills" / a.skill
    if a.project:
        project = Path(a.project).resolve()
        candidates = [project / host / 'skills' / a.skill for host in ('.agents', '.claude')]
        installed = [p for p in candidates if (p / 'SKILL.md').is_file()]
        if len(installed) != 1:
            ap.error('Project must have exactly one installed copy of this role; no shared-memory fallback')
        base = installed[0].resolve()
        if not base.is_relative_to(project):
            ap.error('Installed role escapes project through a symlink')
    output = Path(a.out).resolve()
    try:
        if a.project and not output.is_relative_to(project):
            raise ValueError('Project context output must remain inside the selected project')
        if any(not (base / rel).resolve().is_relative_to(base) for rel in SOURCES):
            raise ValueError('Role memory source escapes its installation through a symlink')
        if base == output or base in output.parents or (REPO / ".agents" / "skills").resolve() in output.parents:
            raise ValueError("Output must be outside skill sources")
        binding = (f"Project root: {project}\nRole installation: {base}\nKeep project state and outputs in this project.\n\n" if a.project else '')
        pack = binding + build_pack(base, budget=BUDGET-len(binding), output=output, language=a.language)
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(pack)
                stream.flush()
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
    except (OSError, ValueError) as exc:
        print(f"Context pack failed: {exc}. Do not use a previous output as a successful pack.", file=sys.stderr)
        return 1
    print(f"pack: {len(pack)} chars -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
