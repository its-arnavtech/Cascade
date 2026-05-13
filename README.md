# CASCADE

Current project phase: Phase 3, the storage and memory layer.

Phase 1 status: complete.

Phase 2 status: complete. Redpanda-powered Kafka-compatible event backbone, observation pipeline, experiment tracking, topology, causal reconstruction, and incident report generation are implemented for local kind.

Phase 3 status: implemented. ClickHouse analytical archival, Qdrant semantic memory, incident/report persistence, topology snapshots, and retrieval-service APIs are implemented for local kind.

## Phase 2 Quickstart

```powershell
.\scripts\deploy-phase-2.ps1
.\scripts\accept-phase-2.ps1
.\scripts\demo-phase-2.ps1
```

See `docs/phase-2.md` for architecture, services, topics, and acceptance details.

## Phase 3 Quickstart

```powershell
.\scripts\deploy-phase-3.ps1
.\scripts\accept-phase-3.ps1
.\scripts\demo-phase-3.ps1
```

See `docs/phase-3-storage-memory.md` for storage schemas, memory design, retrieval APIs, acceptance, and troubleshooting.

## Phase 3 - Storage + Memory Layer

Phase 3 adds durable storage and memory to the completed Phase 2 incident-intelligence pipeline:

- ClickHouse telemetry, time-series, and event analytics
- Qdrant vector memory
- telemetry archival from Redpanda
- experiment event archival
- incident and report persistence
- topology snapshot persistence
- deterministic semantic memory indexing
- similarity search for past incidents
- retrieval-service APIs over ClickHouse and Qdrant

Architecture:

```text
Prometheus
-> observation-service
-> telemetry.raw
-> Redpanda
-> stream-enricher
-> telemetry.enriched
-> telemetry-archiver
-> ClickHouse

Chaos Mesh
-> experiment-tracker-service
-> experiments.events
-> telemetry-archiver
-> ClickHouse

causal-reconstruction-service + incident-timeline-service
-> retrieval-service incident/report archival
-> ClickHouse + Qdrant

retrieval-service
-> ClickHouse + Qdrant
```

## Remaining Roadmap

### Phase 3 — Storage + Memory Layer

Status: implemented for local kind. Cascade can persist observed events, store incident history, create deterministic semantic memory, and retrieve similar incidents.

### Phase 4 — ML Anomaly Detection

Goal: move from rule-based signals to actual anomaly detection.

Adds:

- anomaly detection service
- feature extraction from enriched telemetry
- baseline models such as Isolation Forest, rolling z-score, and threshold models
- later sequence or graph-based anomaly scoring

Outcome:
Cascade detects abnormal service behavior automatically.

### Phase 5 — RAG + Knowledge Layer

Goal: let Cascade reason with documentation and historical incidents.

Adds:

- runbook ingestion
- incident report ingestion
- topology documentation ingestion
- vector embeddings
- retrieval service
- source-grounded explanations

Outcome:
Cascade can retrieve relevant operational knowledge and past incidents.

### Phase 6 — LangChain/LangGraph Agent Runtime

Goal: add the custom agentic AI investigation layer.

Adds:

- LangGraph supervisor agent
- telemetry analyst agent
- incident investigator agent
- topology analyst agent
- remediation planner agent
- verifier/critic agent
- tool calls into telemetry, topology, anomaly, vector, and incident services

Outcome:
Cascade becomes an AI incident investigator instead of only a telemetry pipeline.

### Phase 7 — Chaos Engineering Automation

Goal: close the loop with controlled failure injection.

Adds:

- Chaos Mesh integration service
- experiment planner
- blast-radius controls
- safe experiment execution
- chaos result scoring
- resilience score per service

Outcome:
Cascade can inject faults, observe impact, reconstruct causes, and score resilience.

### Phase 8 — Remediation + Human Approval

Goal: generate safe evidence-backed remediation plans.

Adds:

- remediation recommendation service
- rollback/runbook generator
- confidence scoring
- human approval workflow
- suggested kubectl/infra actions
- gated execution model

Outcome:
Cascade recommends what to do next with evidence and guardrails.

### Phase 9 — UI / Command Center

Goal: make Cascade visually demoable and operationally usable.

Adds:

- Next.js dashboard
- service topology graph
- live telemetry panels
- event stream viewer
- incident timeline
- agent reasoning trace
- chaos experiment console
- similar incidents panel
- remediation approval panel

Outcome:
Cascade becomes a real operations console for distributed failure intelligence.

### Phase 10 — Production Hardening + Final Polish

Goal: make Cascade portfolio/interview-ready.

Adds:

- auth/basic RBAC
- improved docs
- architecture diagrams
- one-command demo
- GitHub Actions CI
- screenshots/GIFs/video
- final README polish
- resume bullet points
- demo scenarios such as pod kill, service latency, retry storm, and degraded dependency

Outcome:
Cascade becomes a Kubernetes-native chaos, observability, and AI incident intelligence platform.

### Distributed Systems Reliability & Chaos Intelligence Platform

## Overview

Cascade is a cloud-native platform that goes beyond traditional chaos engineering by closing the full reliability loop:

* Automatically selects what to break
* Injects controlled failures into distributed systems
* Reconstructs causal failure timelines from telemetry
* Identifies root causes using an agentic AI system
* Recommends actionable remediations
* Learns from every experiment

> Unlike traditional tools that stop at fault injection, Cascade provides **end-to-end failure understanding and reasoning**.

---

## Key Features

### 🔹 Autonomous Experiment Pipeline

* Trigger experiments on real microservices systems
* Inject faults using Chaos Mesh
* Enforce safety via controlled execution

### 🔹 Causal Failure Reconstruction

* Rebuilds service-level failure chains using:

  * distributed traces
  * metric anomalies
* Produces structured causal graphs:

  ```
  payment → cart → frontend failure chain
  ```

### 🔹 Agentic Root Cause Analysis

* Multi-step reasoning pipeline using LangChain
* Combines:

  * causal graphs
  * telemetry summaries
  * historical failure patterns
* Outputs:

  * root cause
  * confidence
  * reasoning trace

### 🔹 RAG + Vector Memory

* Stores historical failure signatures in Qdrant
* Retrieves similar past incidents
* Improves reasoning with contextual grounding

### 🔹 Real System Validation

Tested on:

* Google Online Boutique (11-service microservices system)
* Custom failure-injected microservices application

---

## Architecture (Simplified)

```
[User / Trigger]
        ↓
[Experiment Runner]
        ↓
[Injection Service] → Chaos Mesh
        ↓
[Observation Layer]
(Prometheus + OpenTelemetry)
        ↓
[Causal Reconstruction Service]
        ↓
[Agent System (LangChain)]
        ↓
[RAG Layer (Qdrant)]
        ↓
[Root Cause + Recommendation]
        ↓
[UI / Dashboard]
```

---

## Tech Stack

### Infrastructure

* Docker
* Kubernetes
* Helm

### Backend

* Go (core services)
* Python (AI + reasoning)
* gRPC + REST

### Data

* PostgreSQL (system state)
* Redis (agent state, caching)
* Qdrant (vector database)

### Observability

* Prometheus
* Grafana
* OpenTelemetry

### AI / Agents

* LangChain
* Embeddings + RAG
* Custom agent pipeline

### Frontend

* Next.js
* TypeScript
* Tailwind

---

## Example Flow

1. Inject failure into a service (e.g., payment-service)
2. System collects metrics + traces
3. Cascade reconstructs:

   ```
   payment → cart → frontend failure chain
   ```
4. Agent analyzes:

   * identifies root cause
   * retrieves similar past failures
5. Outputs:

   * explanation
   * recommendation

---

## Demo Scenarios

* Service failure cascade
* Timeout propagation
* Retry amplification (custom system)

---

## Why This Matters

Modern distributed systems are too complex for manual debugging.

Cascade demonstrates:

* automated failure understanding
* system-level reasoning
* intelligent observability

---

## Future Work

* Full Kafka-based streaming pipeline
* Neo4j topology graph
* Advanced causal inference models
* LangGraph-based agent runtime
* ML-based anomaly detection

---

## Author

Built as a high-complexity systems + AI project targeting:

* SWE
* Platform Engineering
* ML Infrastructure roles

---

## License

MIT
