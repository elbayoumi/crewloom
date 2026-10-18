#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""distributed-systems-architect — validate a system design specification packet.

Checks:
- Schema version, system ID, and target scale parameters are well-formed.
- Realistic SLO targets (availability percentage between 99.0 and 99.9999, positive p99 latency).
- Microservice components have unique IDs, recognized protocols, and multi-node failure domains.
- Data stores enforce high-availability replication (factor >= 2) and defined RPO backup windows.
- Resilience policies mandate circuit breakers, rate limiting, and explicit SPOF mitigation.
- Security threat models link threats directly to mitigations.
- No embedded literal secrets, access keys, or private tokens.

Stdlib only.
Exit codes:
  0 = PASS
  1 = usage error or malformed JSON
  2 = gate validation rejection
"""
import argparse
import json
import re
import sys

ALLOWED_PROTOCOLS = ('grpc', 'http', 'https', 'websocket', 'amqp', 'kafka', 'tcp', 'udp')
SYSTEM_ID_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
SECRET_HINT = re.compile(r'(sk-[A-Za-z0-9_-]{8,}|gsk_|ghp_|xox[bap]-|AKIA[0-9A-Z]{8,}|-----BEGIN|eyJ[A-Za-z0-9_-]{10,})')


def is_non_empty_str(val):
    return isinstance(val, str) and bool(val.strip())


def is_positive_num(val):
    return isinstance(val, (int, float)) and val > 0


def scan_for_secrets(value, path='$'):
    hits = []
    if isinstance(value, str):
        if SECRET_HINT.search(value):
            hits.append(path)
    elif isinstance(value, dict):
        for k, v in value.items():
            hits.extend(scan_for_secrets(v, f'{path}.{k}'))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            hits.extend(scan_for_secrets(item, f'{path}[{i}]'))
    return hits


def validate_system_id(packet):
    sys_id = packet.get('system_id')
    if not is_non_empty_str(sys_id):
        return ["missing or empty 'system_id'"]
    if not SYSTEM_ID_RE.match(sys_id):
        return [f"invalid 'system_id' {sys_id!r}: must be kebab-case (e.g. 'global-messaging')"]
    return []


def validate_target_scale(packet):
    scale = packet.get('target_scale')
    if not isinstance(scale, dict):
        return ["missing 'target_scale' object"]
    errs = []
    if not is_positive_num(scale.get('read_rps')):
        errs.append('target_scale.read_rps must be a positive number')
    if not is_positive_num(scale.get('write_rps')):
        errs.append('target_scale.write_rps must be a positive number')
    if not is_positive_num(scale.get('storage_annual_gb')):
        errs.append('target_scale.storage_annual_gb must be a positive number')
    return errs


def validate_slos(packet):
    slos = packet.get('slo_targets')
    if not isinstance(slos, dict):
        return ["missing 'slo_targets' object"]
    errs = []
    avail = slos.get('availability_percent')
    if not isinstance(avail, (int, float)) or not (99.0 <= avail <= 99.9999):
        errs.append("slo_targets.availability_percent must be a number between 99.0 and 99.9999")
    latency = slos.get('latency_p99_ms')
    if not is_positive_num(latency):
        errs.append("slo_targets.latency_p99_ms must be a positive number in milliseconds")
    return errs


def validate_components(packet):
    comps = packet.get('components')
    if not isinstance(comps, list) or not comps:
        return ["'components' must be a non-empty list of services"]
    errs = []
    seen_ids = set()
    for idx, comp in enumerate(comps):
        if not isinstance(comp, dict):
            errs.append(f"components[{idx}] must be an object")
            continue
        c_id = comp.get('id')
        if not is_non_empty_str(c_id) or not SYSTEM_ID_RE.match(c_id):
            errs.append(f"components[{idx}].id must be a valid kebab-case string")
        elif c_id in seen_ids:
            errs.append(f"duplicate component id {c_id!r}")
        else:
            seen_ids.add(c_id)

        if not is_non_empty_str(comp.get('role')):
            errs.append(f"components[{idx}] ({c_id or 'unknown'}): 'role' is required")

        proto = comp.get('protocol')
        if proto not in ALLOWED_PROTOCOLS:
            errs.append(f"components[{idx}] ({c_id or 'unknown'}): protocol must be one of {ALLOWED_PROTOCOLS}")

        if not is_non_empty_str(comp.get('failure_domain')):
            errs.append(f"components[{idx}] ({c_id or 'unknown'}): 'failure_domain' is required (e.g. multi-az, regional)")
    return errs


def validate_data_stores(packet):
    stores = packet.get('data_stores')
    if not isinstance(stores, list) or not stores:
        return ["'data_stores' must be a non-empty list"]
    errs = []
    seen_ids = set()
    for idx, store in enumerate(stores):
        if not isinstance(store, dict):
            errs.append(f"data_stores[{idx}] must be an object")
            continue
        s_id = store.get('id')
        if not is_non_empty_str(s_id) or not SYSTEM_ID_RE.match(s_id):
            errs.append(f"data_stores[{idx}].id must be a valid kebab-case string")
        elif s_id in seen_ids:
            errs.append(f"duplicate data store id {s_id!r}")
        else:
            seen_ids.add(s_id)

        if not is_non_empty_str(store.get('engine')):
            errs.append(f"data_stores[{idx}] ({s_id or 'unknown'}): 'engine' is required")

        rf = store.get('replication_factor')
        if not isinstance(rf, int) or rf < 2:
            errs.append(f"data_stores[{idx}] ({s_id or 'unknown'}): replication_factor must be an integer >= 2 for high availability")

        rpo = store.get('backup_rpo_minutes')
        if not isinstance(rpo, (int, float)) or rpo < 0:
            errs.append(f"data_stores[{idx}] ({s_id or 'unknown'}): backup_rpo_minutes must be a non-negative number")
    return errs


def validate_resilience(packet):
    resil = packet.get('resilience')
    if not isinstance(resil, dict):
        return ["missing 'resilience' object"]
    errs = []
    if resil.get('circuit_breaker') is not True:
        errs.append("resilience.circuit_breaker must be true (mandatory for distributed stability)")
    if not is_non_empty_str(resil.get('rate_limiting')):
        errs.append("resilience.rate_limiting must state an algorithm (e.g. 'token-bucket', 'sliding-window')")
    spof = resil.get('spof_mitigations')
    if not isinstance(spof, list) or not spof or any(not is_non_empty_str(s) for s in spof):
        errs.append("resilience.spof_mitigations must be a non-empty list of string mitigations proving zero single-points-of-failure")
    return errs


def validate_threat_model(packet):
    tm = packet.get('threat_model')
    if not isinstance(tm, list) or not tm:
        return ["'threat_model' must be a non-empty list of identified threats and mitigations"]
    errs = []
    for idx, item in enumerate(tm):
        if not isinstance(item, dict):
            errs.append(f"threat_model[{idx}] must be an object")
            continue
        if not is_non_empty_str(item.get('threat')):
            errs.append(f"threat_model[{idx}] missing 'threat'")
        if not is_non_empty_str(item.get('mitigation')):
            errs.append(f"threat_model[{idx}] missing 'mitigation'")
    return errs


def check_packet(packet):
    if not isinstance(packet, dict):
        return ["top-level packet must be a JSON object"]
    schema = packet.get('schema_version')
    if schema != 1:
        return [f"unsupported schema_version {schema!r}; expected 1"]

    errors = []
    errors.extend(validate_system_id(packet))
    if not is_non_empty_str(packet.get('summary')):
        errors.append("missing or empty 'summary' description")

    errors.extend(validate_target_scale(packet))
    errors.extend(validate_slos(packet))
    errors.extend(validate_components(packet))
    errors.extend(validate_data_stores(packet))
    errors.extend(validate_resilience(packet))
    errors.extend(validate_threat_model(packet))

    secrets = scan_for_secrets(packet)
    if secrets:
        errors.append(f"embedded credentials or tokens detected at: {', '.join(secrets)}")

    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a system design specification packet.")
    parser.add_argument('--packet', required=True, help="Path to system design JSON packet")
    args = parser.parse_args(argv)

    try:
        with open(args.packet, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        print(f"Error: file not found: {args.packet}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {args.packet}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error reading {args.packet}: {exc}", file=sys.stderr)
        return 1

    errors = check_packet(data)
    if errors:
        print(f"REJECT: system design packet {args.packet} failed {len(errors)} check(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    sys_id = data.get('system_id', 'unknown')
    comp_count = len(data.get('components', []))
    store_count = len(data.get('data_stores', []))
    print(f"PASS system-design: {sys_id} ({comp_count} component(s), {store_count} data store(s), 0 SPOFs)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
