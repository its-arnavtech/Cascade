# CASCADE

Current project phase: Phase 2, the deterministic telemetry and incident reconstruction layer.

Phase 2 status: Redpanda-powered Kafka-compatible event backbone, observation pipeline, experiment tracking, topology, causal reconstruction, and incident report generation are implemented for local kind.

## Phase 2 Quickstart

```powershell
.\scripts\deploy-phase-2.ps1
.\scripts\accept-phase-2.ps1
.\scripts\demo-phase-2.ps1
```

See `docs/phase-2.md` for architecture, services, topics, and acceptance details.

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
