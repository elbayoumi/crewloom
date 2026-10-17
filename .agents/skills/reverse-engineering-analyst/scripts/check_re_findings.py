#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reverse-engineering-analyst — validate a findings packet's bookkeeping.

Checks: target hash and authorization are present, every finding has a known kind, observations and
derivations link to recorded evidence, inferences and unknowns state their limitations, identifiers are
unique, and no literal secret is embedded. It does not prove a claim is true.
Stdlib only. Exit 0 = PASS, 1 = usage/JSON error, 2 = gate rejection.
"""
import argparse
import json
import re
import sys

KINDS = ('observation', 'derivation', 'inference', 'unknown')
NEEDS_EVIDENCE = ('observation', 'derivation', 'inference')
NEEDS_LIMITATIONS = ('inference', 'unknown')
SHA256 = re.compile(r'[0-9a-f]{64}')
SECRET_HINT = re.compile(r'(sk-[A-Za-z0-9]{8,}|gsk_|ghp_|xox[bap]-|AKIA[0-9A-Z]{8,}|-----BEGIN|eyJ[A-Za-z0-9_-]{10,})')


def text(value):
    return isinstance(value, str) and bool(value.strip())


def secret_paths(value, path='$'):
    if isinstance(value, str):
        return [path] if SECRET_HINT.search(value) else []
    if isinstance(value, dict):
        return [hit for key, item in value.items() for hit in secret_paths(item, f'{path}.{key}')]
    if isinstance(value, list):
        return [hit for index, item in enumerate(value) for hit in secret_paths(item, f'{path}[{index}]')]
    return []


def check_target(packet):
    target = packet.get('target')
    if not isinstance(target, dict):
        return ["missing 'target' object"]
    errors = []
    if not text(target.get('path')):
        errors.append('target.path is required')
    digest = target.get('sha256')
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append('target.sha256 must be 64 lowercase hex characters')
    if not text(target.get('authorization')):
        errors.append('target.authorization must state who authorized the analysis and why')
    return errors


def check_evidence(packet):
    evidence = packet.get('evidence')
    if not isinstance(evidence, list):
        return ["'evidence' must be a list"], set()
    errors, known = [], set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or not text(item.get('id')) or not text(item.get('tool')):
            errors.append(f'evidence[{index}] needs non-empty id and tool')
            continue
        if item['id'] in known:
            errors.append(f"duplicate evidence id '{item['id']}'")
        known.add(item['id'])
    return errors, known


def check_findings(packet, known):
    findings = packet.get('findings')
    if not isinstance(findings, list) or not findings:
        return ["'findings' must be a non-empty list"]
    errors, seen = [], set()
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            errors.append(f'findings[{index}] must be an object')
            continue
        name = item.get('id')
        label = f"finding '{name}'" if text(name) else f'findings[{index}]'
        if not text(name):
            errors.append(f'{label} needs an id')
        elif name in seen:
            errors.append(f'duplicate finding id {name!r}')
        else:
            seen.add(name)
        if not text(item.get('claim')):
            errors.append(f'{label} needs a claim')
        kind = item.get('kind')
        if kind not in KINDS:
            errors.append(f"{label}: kind must be one of {', '.join(KINDS)}")
            continue
        links = item.get('evidence_ids', [])
        if not isinstance(links, list) or any(not isinstance(link, str) for link in links):
            errors.append(f'{label}: evidence_ids must be a list of strings')
            continue
        if kind in NEEDS_EVIDENCE and not links:
            errors.append(f'{label}: a {kind} must cite evidence')
        for link in links:
            if link not in known:
                errors.append(f"{label}: unknown evidence id '{link}'")
        if kind in NEEDS_LIMITATIONS and not text(item.get('limitations')):
            errors.append(f'{label}: a {kind} must state its limitations')
    return errors


def check(packet):
    if not isinstance(packet, dict):
        return ['top-level JSON must be an object']
    evidence_errors, known = check_evidence(packet)
    errors = check_target(packet) + evidence_errors + check_findings(packet, known)
    errors += [f'{path} looks like an embedded secret' for path in secret_paths(packet)]
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--findings', required=True)
    args = parser.parse_args()
    try:
        with open(args.findings, encoding='utf-8') as handle:
            packet = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f'FAIL: cannot load findings: {exc}')
        return 1
    errors = check(packet)
    if errors:
        print('FAIL re findings:')
        for error in errors:
            print(f'  - {error}')
        return 2
    print(f"PASS re findings ({len(packet['findings'])} finding(s), {len(packet['evidence'])} evidence record(s))")
    return 0


if __name__ == '__main__':
    sys.exit(main())
