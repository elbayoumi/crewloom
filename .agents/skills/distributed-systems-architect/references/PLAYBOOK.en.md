# Distributed Systems Architect

This English procedure defines the role's project work. The role guides distributed system decomposition, data tier architecture, resilience engineering, and API contract design.

## Inputs and scope

Target throughput (read/write RPS), storage growth, SLA/SLO expectations (availability %, latency targets), domain boundaries, and existing tech stacks. Read the repository constitution and the role's architecture, completed work, challenges, and ideas before acting. Bind one canonical project root.

## Procedure

1. **Requirements & Scale Analysis**: Determine peak concurrency, read-to-write ratio, data volume per transaction, and geographic distribution requirements.
2. **C4 Architecture & Decomposition**: Partition the system into modular services or bounded contexts. Diagram Context, Containers, and Components using standard GitHub Mermaid syntax.
3. **Data Tier & Caching**:
   - Classify access patterns (key-value lookups, complex queries, event streams).
   - Select database engines (PostgreSQL, Cassandra/ScyllaDB, Redis, DynamoDB).
   - Define primary/replica topology, write consensus (quorum), sharding keys, and backup recovery objectives (RPO/RTO).
   - Select caching topology (Cache-Aside, Write-Behind, TTLs, distributed cache cluster).
4. **Inter-Service Communication**:
   - Synchronous RPC (gRPC / HTTP/2) for low-latency command/query paths.
   - Asynchronous Event Bus (Kafka / RabbitMQ / Cloud Pub/Sub) for decoupled state changes, ensuring at-least-once delivery with idempotent consumers.
5. **Reliability & Single Point of Failure (SPOF) Elimination**:
   - Eliminate all single points of failure across load balancers, application tiers, and storage nodes.
   - Enforce circuit breakers, exponential backoff with jitter, and token-bucket rate limiting.
6. **Security & Zero-Trust**:
   - Enforce mutual TLS (mTLS) for service-to-service communication.
   - Define API gateway authentication (OAuth 2.1, OIDC, JWT) and token revocation.
7. **Packet Assembly & Verification**:
   - Assemble the structured JSON specification packet.
   - Run `crewloom run system-design -- --packet system-design.json`.

## Deliverable and acceptance

A valid system design specification packet passing the `system-design` checker, alongside a detailed architecture document with Mermaid diagrams. The design must prove zero unmitigated SPOFs, realistic SLO bounds, and explicit failover strategies.

## Dependencies and failure handling

Use the [public tool catalog](../../../../documentation/TOOLS.md) to establish bundled checks. The role uses the Python standard library core. Record missing operational facts explicitly; do not invent capacity or infrastructure requirements that the application does not need.

## Handoff and memory closure

Carry project root, system ID, target scale metrics, verified packet path, and remaining architectural trade-offs to downstream roles (engineering, infrastructure, security). Update project-local memory in `brain/`, keeping internal infrastructure credentials and private customer data out of public memory.
