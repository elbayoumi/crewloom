#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crewloom automation-ops-engineer — validate an n8n workflow JSON contract.

Checks: valid JSON; nodes is a non-empty list; connections present (dict or
list, matching real n8n exports); every node has non-empty id/name/type;
every credentials reference names a non-empty id or name; no banned secret
field (password/token/secret/apiKey, case-insensitive) holds a non-empty
literal value.

Exit 0 + PASS on success, exit 2 + FAIL listing violations otherwise.
Stdlib only.
"""
import json
import sys
from pathlib import Path

BANNED_KEYS = {"password", "token", "secret", "apikey", "api_key", "api-key"}


def _walk(node, path, violations):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if isinstance(k, str) and k.lower() in BANNED_KEYS:
                if isinstance(v, str) and v.strip():
                    violations.append(f"embedded secret: field '{p}' holds a literal value")
                elif isinstance(v, dict) and v.get("value"):
                    violations.append(f"embedded secret: field '{p}' holds a literal value")
            _walk(v, p, violations)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]", violations)


def check(path: Path):
    violations = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        return [f"unreadable file: {e}"]
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]
    nodes = data.get("nodes")
    conns = data.get("connections")
    if not isinstance(nodes, list) or not nodes:
        violations.append("missing or empty 'nodes' list")
    else:
        for i, n in enumerate(nodes):
            if not isinstance(n, dict):
                violations.append(f"nodes[{i}] is not an object")
                continue
            for field in ("id", "name", "type"):
                v = n.get(field)
                if not isinstance(v, str) or not v.strip():
                    violations.append(f"nodes[{i}] missing non-empty '{field}'")
            creds = n.get("credentials")
            if creds is not None:
                if not isinstance(creds, dict) or not creds:
                    violations.append(f"node '{n.get('name', i)}' has empty/invalid 'credentials'")
                else:
                    for ctype, cref in creds.items():
                        if not isinstance(cref, dict) or not (
                            (isinstance(cref.get("id"), str) and cref["id"].strip())
                            or (isinstance(cref.get("name"), str) and cref["name"].strip())
                        ):
                            violations.append(
                                f"node '{n.get('name', i)}' credential '{ctype}' lacks non-empty id/name"
                            )
    if not isinstance(conns, (dict, list)):
        violations.append("missing 'connections' (dict or list)")
    _walk(data, "$", violations)
    return violations


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_workflow_contract.py <workflow.json>", file=sys.stderr)
        return 2
    violations = check(Path(sys.argv[1]))
    if violations:
        print(f"FAIL {sys.argv[1]}:")
        for v in violations:
            print(f"  - {v}")
        return 2
    print(f"PASS {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
