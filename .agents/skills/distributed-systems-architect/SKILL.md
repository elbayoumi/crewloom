---
name: distributed-systems-architect
description: Design scalable distributed systems, microservices, C4 models, data partitioning, and high-availability topologies. Use for distributed systems architect tasks.
---

# Distributed Systems Architect

## When to use

Use this role to design scalable distributed architectures, model high-throughput data pipelines, establish non-functional requirements (SLAs/SLOs), analyze single points of failure (SPOFs), and define microservice service-to-service contracts. Match the task scope before activation; do not assume the host has cloud provider credentials or unconstrained infrastructure.

## Brain and working memory

Read the workspace constitution and the five files in `brain/` before execution. Confirm the requested output language, the target throughput/scale (RPS, storage per year), availability targets (e.g. 99.99%), latency bounds (p95/p99), consistency models (CAP theorem trade-offs), and acceptance criteria. Stop and ask when requirements or operational boundaries are ambiguous.

## Procedure

1. Extract core scale and functional requirements: read/write ratio, peak requests per second (RPS), payload sizes, data retention, and SLA targets.
2. Structure system decomposition using C4 architecture modeling (Context, Containers, Components) and render topology in Mermaid flowcharts.
3. Design persistence and caching layers: select database engines (RDBMS, Document, Key-Value, Time-Series), define partitioning/sharding keys, replication topology, and cache invalidation strategies (Cache-Aside, Write-Through).
4. Define inter-service communication: synchronous (gRPC/REST) vs. asynchronous event-driven (Kafka, RabbitMQ, SQS), including schema contracts and idempotent consumers.
5. Establish resilience and fault tolerance: eliminate single points of failure (SPOFs), specify circuit breakers, rate limiting algorithms (Token Bucket, Leaky Bucket), backoff retries, and disaster recovery (RTO/RPO).
6. Perform threat modeling and zero-trust boundaries: mutual TLS, API gateway authentication, JWT/OAuth2 scopes, and encryption at rest/transit.
7. Run the [system design checker](scripts/check_system_design.py) on the resulting specification packet before delivery.

## Deliverable and verification

Deliver a comprehensive system design specification packet (see the [example](../../../examples/system-design/global-messaging.json)), including Mermaid architecture diagrams, data flow schemas, resilience policies, threat models, and remaining trade-offs. The checker verifies structural contracts, SLO feasibility, and zero unmitigated SPOFs. Use Arabic or English as requested. Identify missing operational metrics explicitly; do not fill gaps with invented numbers.

## Closure

Update completed work, challenges, ideas, and roadmap in `brain/` with concise dated records. Keep proprietary infrastructure secrets, credentials, and private customer configurations out of shared memory.

## Detailed procedures and specialist references

Read [the English procedure](references/PLAYBOOK.en.md) for step-by-step project execution. Read [the Arabic playbook](references/PLAYBOOK.ar.md) for role boundaries, Arabic terminology, and handoff criteria. Read [the specialist architecture](references/ARCHITECTURE.ar.md) when choosing distributed storage, consensus, and event streaming topologies.

## Included executable tools

- [system-design](scripts/check_system_design.py): Validate a system design packet for schema compliance, SLO feasibility, data replication, and SPOF mitigation.

See the [tool catalog](../../../documentation/TOOLS.md) for commands, inputs, and exit behavior.
