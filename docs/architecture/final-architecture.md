# Final Cascade Architecture

Cascade is a Kubernetes-native AI reliability platform for local incident intelligence, anomaly detection, agent investigation, chaos dry-runs, remediation planning, and operator approval.

## Overview

Target workload telemetry flows from Prometheus and Kubernetes into Redpanda topics, is enriched and archived into ClickHouse, indexed into Qdrant, and surfaced through retrieval services, agents, and the Command Center.

## Phase Map

- Phase 1: Kubernetes, target workload, and observability foundation.
- Phase 2: telemetry ingestion, Redpanda event backbone, topology, causal reconstruction, and incident timeline.
- Phase 3: ClickHouse analytical storage and Qdrant incident memory.
- Phase 4: feature extraction and anomaly detection.
- Phase 5: knowledge ingestion and RAG retrieval over runbooks and operational records.
- Phase 6: deterministic agent investigation runtime and read-only tool gateway.
- Phase 7: chaos planning and dry-run execution with safety boundaries.
- Phase 8: remediation recommendation, approval records, and dry-run executor.
- Phase 9: Command Center UI and browser-facing API proxy.
- Phase 10: hardening scripts, backups, secret hygiene, rate limiting, final docs, and acceptance aggregation.

## Service Map

Core APIs:

- `observation-service:8000`
- `stream-enricher:8001`
- `experiment-tracker-service:8002`
- `topology-service:8004`
- `causal-reconstruction-service:8005`
- `incident-timeline-service:8006`
- `retrieval-service:8012`
- `knowledge-retrieval-service:8016`
- `agent-tool-gateway:8017`
- `agent-orchestrator-service:8018`
- `chaos-planner-service:8019`
- `chaos-executor-service:8020`
- `remediation-recommender-service:8021`
- `approval-service:8022`
- `remediation-executor-service:8023`
- `command-center-api:8031`
- `command-center:8030`

## Data Flow

Prometheus/Kubernetes signals enter `observation-service`, publish to `telemetry.raw`, move through `stream-enricher` to `telemetry.enriched`, and are archived by `telemetry-archiver`. Feature extraction and anomaly detection read ClickHouse tables and publish anomaly lifecycle events. Agent, chaos, and remediation services write state to ClickHouse and compact lifecycle messages to Redpanda.

## Topics

- `telemetry.raw`
- `telemetry.enriched`
- `experiments.events`
- `anomalies.detected`
- `agent.investigations`
- `chaos.experiments`
- `remediation.actions`

## Storage

ClickHouse database: `cascade`.

Important tables include telemetry and experiment events, incidents, reports, topology snapshots, feature windows, anomaly events, model runs, knowledge documents/chunks, investigation runs/steps/reports/tool calls, chaos plans/runs/observations/scores/safety violations, and remediation plans/approvals/executions/policy audit rows.

Qdrant collections:

- `cascade_incident_memory`
- `cascade_knowledge_base`

## Safety Boundaries

- Command Center API allows only GET and selected safe POST routes.
- Real remediation execution is blocked by default.
- Real chaos execution is blocked through the UI path by default.
- Phase 7 normal validation uses `-DryRunOnly`.
- Rate limiting is local in-memory protection on `command-center-api`.

## Local vs Production

Local kind is excellent for demo and development, but it is not production durable. Production deployment would need distributed rate limiting, authentication, network policy, persistent storage design, scheduled backups, restore drills, ingress/WAF controls, observability SLOs, and explicit Redpanda retention policy.
