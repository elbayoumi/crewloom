#!/usr/bin/env python3
"""Check delivery evidence bookkeeping, not the truth or visual quality of evidence."""
import argparse
import hashlib
import json
import re
from pathlib import Path

CHECKS = {"brief", "pilot", "technical", "visual", "responsive", "keyboard", "accessibility",
          "journey", "error_states"}
TECHNICAL_SCOPE = {"build", "browser", "responsive", "accessibility"}
SEVERITIES = {"critical", "high", "medium", "low"}


def check(data, root, expected_revision=None):
    root = root.resolve()
    problems, counts, escalation = [], dict.fromkeys(sorted(SEVERITIES), 0), []
    if not isinstance(data, dict):
        raise ValueError("Packet must be an object")
    if data.get("schema_version") != 2:
        problems.append("schema_version 2 required; evidence hashes must be reviewed")
    if not isinstance(expected_revision, str) or not expected_revision.strip():
        problems.append("Expected revision must come from the current project snapshot")
    elif data.get("revision") != expected_revision:
        problems.append("Packet does not match expected project revision")
    for key in ("project", "revision", "implementer"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            problems.append("Missing " + key)
    checks, defects = data.get("checks"), data.get("defects")
    if not isinstance(checks, list) or not isinstance(defects, list):
        raise ValueError("checks and defects must be lists")
    seen = set()
    for row in checks:
        if not isinstance(row, dict):
            raise ValueError("Invalid check record")
        name = row.get("id")
        if not isinstance(name, str) or not name.strip() or name in seen:
            problems.append("Invalid or duplicate check id")
            continue
        seen.add(name)
        if row.get("status") != "pass":
            problems.append(name + ": not verified")
        reviewer = row.get("reviewer")
        implementer = data.get("implementer", "")
        if not isinstance(reviewer, str) or not reviewer.strip() or (isinstance(implementer, str) and reviewer.strip().casefold() == implementer.strip().casefold()):
            problems.append(name + ": separate reviewer required")
        if row.get("revision") != data.get("revision"):
            problems.append(name + ": stale revision")
        if name == "technical":
            scope = row.get("review_scope")
            if not isinstance(scope, list) or not TECHNICAL_SCOPE.issubset(set(scope)):
                problems.append("technical: review_scope must cover build, browser, responsive and accessibility")
        evidence = row.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            problems.append(name + ": missing evidence")
            continue
        for item in evidence:
            if not isinstance(item, dict):
                problems.append(name + ": evidence needs path and sha256; legacy path is unverified")
                continue
            relative, digest = item.get("path"), item.get("sha256")
            if not isinstance(relative, str) or not relative.strip():
                problems.append(name + ": invalid evidence path")
                continue
            path = (root / relative).resolve()
            if root not in path.parents or not path.is_file() or path.stat().st_size == 0:
                problems.append(name + ": missing, empty or external evidence")
                continue
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                problems.append(name + ": invalid sha256")
                continue
            actual = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    actual.update(chunk)
            if actual.hexdigest() != digest.lower():
                problems.append(name + ": evidence changed since recorded review")
    problems.extend("Missing check: " + name for name in sorted(CHECKS - seen))
    identifiers = set()
    for defect in defects:
        if not isinstance(defect, dict):
            raise ValueError("Invalid defect record")
        name = defect.get("id")
        if not isinstance(name, str) or not name.strip() or name in identifiers:
            problems.append("Invalid or duplicate defect id")
            continue
        identifiers.add(name)
        severity, status = defect.get("severity"), defect.get("status")
        attempts = defect.get("failed_attempts")
        if severity not in SEVERITIES or status not in {"open", "resolved"} or type(attempts) is not int or attempts < 0:
            problems.append(name + ": invalid defect fields")
            continue
        if not isinstance(defect.get("owner"), str) or not defect["owner"].strip():
            problems.append(name + ": missing owner")
        if status == "open":
            counts[severity] += 1
            if attempts >= 2:
                escalation.append(name)
            problems.append(name + ": open defect")
        elif defect.get("verification_check") not in seen:
            problems.append(name + ": missing verification check")
    return {"state": "blocked" if problems else "ready_for_review",
            "product_approved": False, "open_defects": counts,
            "escalation_required": escalation, "problems": problems,
            "limits": "Checks structure, supplied revision and evidence bytes; not reviewer identity, truth or freshness of the supplied snapshot."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--expected-revision", required=True,
                        help="Current project commit or snapshot ID, obtained independently of this packet")
    args = parser.parse_args()
    try:
        result = check(json.loads(args.packet.read_text(encoding="utf-8")), args.packet.resolve().parent, args.expected_revision)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"state": "unverified", "error": str(exc), "product_approved": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
