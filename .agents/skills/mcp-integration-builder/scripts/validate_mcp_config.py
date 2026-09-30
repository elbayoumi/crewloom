#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp-integration-builder — validate an MCP client config (mcpServers JSON).

Checks: top-level mcpServers object exists, every server has command + known
transport, env values are placeholders (no embedded real secrets).
Stdlib only. Exit 0 = PASS, 1 = usage/JSON error, 2 = gate rejection.
"""
import argparse
import json
import re
import sys

KNOWN_TRANSPORTS = ("stdio", "sse", "streamable-http", "http")
SECRET_HINT = re.compile(r"(sk-|gsk_|ghp_|xox|AKIA|-----BEGIN|eyJ[A-Za-z0-9_-]{10,})")


def check(cfg: dict) -> list:
    if not isinstance(cfg, dict):
        return ["top-level JSON must be an object"]
    errors = []
    servers = cfg.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return ["missing or empty top-level 'mcpServers' object"]
    for name, srv in servers.items():
        if not isinstance(srv, dict):
            errors.append(f"server '{name}': must be an object")
            continue
        if not srv.get("command"):
            errors.append(f"server '{name}': missing 'command' (e.g. uvx/npx/python)")
        transport = srv.get("transport", "stdio")
        if transport not in KNOWN_TRANSPORTS:
            errors.append(f"server '{name}': unknown transport '{transport}'")
        env = srv.get("env", {})
        if not isinstance(env, dict):
            errors.append(f"server '{name}': 'env' must be an object")
            continue
        for k, v in env.items():
            if isinstance(v, str) and SECRET_HINT.search(v):
                errors.append(f"server '{name}': env '{k}' looks like an embedded real secret — use a placeholder")
    return errors


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    a = p.parse_args()
    try:
        with open(a.config, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"FAIL: cannot load config: {e}")
        return 1
    errs = check(cfg)
    if errs:
        print("FAIL mcp config:")
        for e in errs:
            print(f"  - {e}")
        return 2
    print(f"PASS mcp config ({len(cfg['mcpServers'])} server(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
