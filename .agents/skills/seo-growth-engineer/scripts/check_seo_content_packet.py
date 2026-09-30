#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crewloom seo-growth-engineer — gate every article publish (stdlib only)."""
import argparse
import json
import re
import sys

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def check(packet: dict) -> list:
    if not isinstance(packet, dict):
        return ["top-level JSON must be an object"]
    errors = []
    title = packet.get("title", "")
    if not isinstance(title, str) or not title:
        errors.append("title: missing")
    elif len(title) > 60:
        errors.append(f"title: {len(title)} chars > 60")
    meta = packet.get("meta_description", "")
    if not isinstance(meta, str) or not meta:
        errors.append("meta_description: missing")
    elif not 120 <= len(meta) <= 160:
        errors.append(f"meta_description: {len(meta)} chars not in 120-160")
    slug = packet.get("slug", "")
    if not isinstance(slug, str) or not slug:
        errors.append("slug: missing")
    elif not SLUG_RE.match(slug):
        errors.append(f"slug: '{slug}' not kebab-case")
    try:
        wc = int(packet.get("wordcount", 0))
    except (TypeError, ValueError):
        wc = 0
    if wc < 800:
        errors.append(f"wordcount: {wc} < 800")
    links = packet.get("internal_links", [])
    if not isinstance(links, list) or len(links) < 1:
        errors.append("internal_links: need >=1 internal link")
    if not packet.get("canonical"):
        errors.append("canonical: missing")
    return errors


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--packet", required=True, help="path to article packet JSON")
    a = p.parse_args()
    try:
        with open(a.packet, encoding="utf-8") as f:
            packet = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot read packet: {e}")
        return 2
    errs = check(packet)
    if errs:
        print("FAIL:")
        for e in errs:
            print(f"  - {e}")
        return 2
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
