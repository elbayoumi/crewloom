# System Design Blueprints & Verification

This directory contains verified architectural blueprints for scalable, fault-tolerant distributed systems designed using the `distributed-systems-architect` role.

## Architecture Blueprint: Global Messaging Platform

[`global-messaging.json`](global-messaging.json) documents a real-time messaging and event distribution platform designed for:
- **Peak Throughput**: 100,000 requests per second (80K read RPS / 20K write RPS).
- **Service Level Objectives (SLOs)**: 99.99% availability with p99 latency < 120ms.
- **Data Tier**: Partitioned PostgreSQL primary with Raft-automated failover, multi-AZ Redis cluster, and distributed Kafka event streams.
- **Zero Single Points of Failure**: Anycast edge routing, stateless WebSocket proxies, and cross-AZ replication.
- **Zero-Trust Security**: mTLS service mesh, Token Bucket rate-limiting, and cryptographically scoped channel tokens.

## Running Verification

Verify the system design specification packet using the standard library `system-design` tool:

```bash
python3 scripts/crewloom.py run system-design -- --packet examples/system-design/global-messaging.json
```

Expected output:
```text
PASS system-design: global-messaging (4 component(s), 3 data store(s), 0 SPOFs)
```

## Specification Schema Structure

A valid system design packet must satisfy:
1. `schema_version`: Must be integer `1`.
2. `system_id`: Kebab-case identifier matching `^[a-z0-9]+(?:-[a-z0-9]+)*$`.
3. `target_scale`: Explicit positive numeric parameters for `read_rps`, `write_rps`, and `storage_annual_gb`.
4. `slo_targets`: Realistic `availability_percent` (between 99.0% and 99.9999%) and positive `latency_p99_ms`.
5. `components`: Defined microservices with unique IDs, allowed protocols (`grpc`, `http`, `https`, `websocket`, `kafka`, `amqp`), and failure domains.
6. `data_stores`: High-availability persistence with `replication_factor >= 2` and defined RPO backup windows.
7. `resilience`: Mandatory `circuit_breaker: true`, explicit rate-limiting algorithm, and comprehensive `spof_mitigations` list.
8. `threat_model`: List of identified security threats with direct mitigations.
9. `Zero Secret Embedding`: Strictly audited against embedded API keys or credentials.
