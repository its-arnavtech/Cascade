# CASCADE

Current project phase: Phase 9, UI / Command Center.

Phase 1 status: complete.

Phase 2 status: complete. Redpanda-powered Kafka-compatible event backbone, observation pipeline, experiment tracking, topology, causal reconstruction, and incident report generation are implemented for local kind.

Phase 3 status: complete. ClickHouse analytical archival, Qdrant semantic memory, incident/report persistence, topology snapshots, and retrieval-service APIs are implemented for local kind.

Phase 4 status: complete. Feature extraction, explainable baseline anomaly detection, anomaly storage, Redpanda anomaly publishing, and retrieval anomaly APIs are implemented for local kind.

Phase 5 status: complete. Runbook/document ingestion, incident report ingestion, anomaly knowledge ingestion, topology knowledge ingestion, deterministic embeddings, ClickHouse knowledge metadata, Qdrant knowledge vectors, source-grounded search, context pack assembly, and retrieval-service knowledge APIs are implemented for local kind.

Phase 6 status: complete. Read-only agent tool gateway, deterministic local investigation graph, evidence-backed report generation, investigation persistence, agent step/tool-call traceability, optional LangGraph/LLM hooks, and compact investigation lifecycle events are implemented for local kind.

Phase 7 status: complete. Safe chaos planning, Chaos Mesh execution, safety policy enforcement, dry-run validation, observation windows, resilience scoring, ClickHouse persistence, Redpanda chaos lifecycle events, and optional Phase 6 investigation integration are implemented for local kind.

Phase 8 status: complete. Evidence-backed remediation recommendation, rollback/runbook generation, human approval/rejection records, dry-run validation, optional gated execution disabled by default, ClickHouse persistence, Redpanda remediation lifecycle events, and read-only agent remediation tools are implemented for local kind.

Phase 9 status: implemented. React command-center UI, FastAPI fixed-route BFF, Kubernetes deployment, local demo workflow, dashboard, telemetry/anomaly/incident/knowledge/investigation/chaos/remediation/system pages, and safe dry-run operator workflows are implemented for local kind.

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

## Phase 4 Quickstart

```powershell
.\scripts\deploy-phase-4.ps1
.\scripts\accept-phase-4.ps1
.\scripts\demo-phase-4.ps1 -Synthetic
```

See `docs/phase-4-anomaly-detection.md` for feature extraction, model design, anomaly schemas, acceptance, and troubleshooting.

## Phase 5 Quickstart

```powershell
.\scripts\deploy-phase-5.ps1
.\scripts\accept-phase-5.ps1
.\scripts\demo-phase-5.ps1
```

See `docs/phase-5-rag-knowledge-layer.md` for knowledge ingestion, retrieval APIs, context pack format, acceptance, and troubleshooting.

## Phase 6 Quickstart

```powershell
.\scripts\deploy-phase-6.ps1
.\scripts\accept-phase-6.ps1
.\scripts\demo-phase-6.ps1
```

See `docs/phase-6-agent-runtime.md` for the tool gateway, investigation graph, deterministic mode, APIs, safety boundaries, acceptance, and troubleshooting.

## Phase 7 Quickstart

```powershell
.\scripts\deploy-phase-7.ps1
.\scripts\accept-phase-7.ps1
.\scripts\demo-phase-7.ps1
```

Use `.\scripts\accept-phase-7.ps1 -DryRunOnly` or `.\scripts\demo-phase-7.ps1 -DryRunOnly` for non-disruptive validation.

See `docs/phase-7-chaos-automation.md` for the safety model, Chaos Mesh templates, execution APIs, resilience scoring, RBAC boundaries, acceptance, and troubleshooting.

## Phase 8 Quickstart

```powershell
.\scripts\deploy-phase-8.ps1
.\scripts\accept-phase-8.ps1
.\scripts\demo-phase-8.ps1
```

Default Phase 8 acceptance and demo workflows do not mutate target workloads. Real execution is blocked by `EXECUTION_ENABLED=false`.

See `docs/phase-8-remediation-approval.md` for the safety model, approval workflow, dry-run validation, APIs, RBAC boundaries, acceptance, and troubleshooting.

## Phase 9 Quickstart

```powershell
.\scripts\deploy-phase-9.ps1
.\scripts\accept-phase-9.ps1
.\scripts\demo-phase-9.ps1
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Open `http://localhost:18300`.

See `docs/phase-9-command-center.md` for the UI pages, BFF design, safety boundaries, deployment, acceptance, demo, and troubleshooting workflow.

## Phase 3 - Storage + Memory Layer

Phase 3 adds durable storage and memory to the completed Phase 2 incident-intelligence pipeline:

- ClickHouse telemetry, time-series, and event analytics
- Qdrant vector memory in `cascade_incident_memory`
- telemetry and experiment archival from Redpanda
- incident and report persistence
- topology snapshot persistence
- deterministic semantic memory indexing
- similarity search for past incidents
- retrieval-service APIs over ClickHouse and Qdrant

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
```

## Phase 4 - ML Anomaly Detection

Phase 4 moves Cascade from remembering incidents to detecting abnormal service behavior automatically:

- feature extraction from ClickHouse `telemetry_events`
- service/workload feature windows in `telemetry_feature_windows`
- rolling z-score, threshold baseline, and optional Isolation Forest detectors
- ensemble risk score and severity mapping
- anomaly persistence in ClickHouse `anomaly_events`
- detector execution tracking in `model_runs`
- Redpanda publishing to `anomalies.detected`
- retrieval-service anomaly APIs

```text
ClickHouse telemetry_events
-> feature-extractor-service
-> telemetry_feature_windows
-> anomaly-detector-service
-> anomaly_events
-> anomalies.detected
-> retrieval-service anomaly APIs
```

## Phase 5 - RAG + Knowledge Layer

Phase 5 lets Cascade retrieve source-grounded operational knowledge without requiring OpenAI, hosted inference, model downloads, LangGraph, autonomous agents, remediation execution, or a UI.

- runbook and document ingestion
- incident report ingestion
- anomaly knowledge ingestion
- topology knowledge ingestion
- deterministic local 128-dimension embeddings
- ClickHouse `knowledge_documents`, `knowledge_chunks`, `knowledge_ingestion_runs`, and `knowledge_queries`
- Qdrant `cascade_knowledge_base`
- source-grounded operational search
- deterministic context pack assembly
- retrieval-service `/knowledge/*` APIs

```text
docs/runbooks/incidents/anomalies/topology
-> knowledge-ingestion-service
-> knowledge_documents / knowledge_chunks
-> Qdrant cascade_knowledge_base
-> knowledge-retrieval-service
-> retrieval-service knowledge APIs
```

## Phase 6 - LangChain/LangGraph Agent Runtime

Phase 6 lets Cascade investigate incidents and anomalies by calling real platform tools and assembling evidence-backed reports. It runs without paid APIs by default.

- `agent-tool-gateway` wraps existing Cascade APIs as read-only tools.
- `agent-orchestrator-service` runs graph-style investigation workflows.
- deterministic local planner mode is the default acceptance/demo mode.
- optional LangGraph/LLM configuration hooks are present but not required.
- ClickHouse stores `investigation_runs`, `agent_steps`, `agent_tool_calls`, and `investigation_reports`.
- Redpanda topic `agent.investigations` stores compact lifecycle events.
- reports include evidence refs, confidence, limitations, recommended next investigation steps, and text-only remediation suggestions.
- Phase 6 does not execute remediation, mutate Kubernetes resources, run chaos experiments, or provide a UI.

```text
anomaly_events / incidents / telemetry / topology / knowledge
-> agent-tool-gateway
-> agent-orchestrator-service
-> investigation_runs / agent_steps / investigation_reports
-> agent.investigations
```

## Phase 7 - Chaos Engineering Automation

Phase 7 lets Cascade safely run bounded Chaos Mesh experiments against Online Boutique and score resilience from real telemetry/anomaly/incident evidence.

- `chaos-planner-service` creates safety-validated experiment plans.
- `chaos-executor-service` executes approved or dry-run plans and always re-validates safety.
- safety policy limits chaos to allowlisted services in `cascade-targets`.
- executor RBAC can create/delete Chaos Mesh resources only, not mutate application deployments or infrastructure.
- ClickHouse stores `chaos_experiment_plans`, `chaos_experiment_runs`, `chaos_observations`, `resilience_scores`, and `chaos_safety_violations`.
- Redpanda topic `chaos.experiments` stores compact lifecycle events.
- observation collects telemetry, anomalies, incidents, and optional Phase 6 investigations.
- Phase 7 does not execute remediation.

```text
topology/anomalies/incidents/knowledge
-> chaos-planner-service
-> chaos_experiment_plans
-> chaos-executor-service
-> Chaos Mesh CRDs
-> observations/resilience_scores
-> chaos.experiments
-> optional agent investigation
```

## Phase 8 - Remediation + Human Approval

Phase 8 lets Cascade recommend what to do next while keeping humans in control of any mutation.

- `remediation-recommender-service` creates deterministic evidence-backed remediation plans from anomalies, incidents, investigations, chaos results, and runbook knowledge.
- plans include pre-checks, remediation steps, post-checks, rollback/runbook steps, evidence refs, confidence, action type, and safety findings.
- `approval-service` stores explicit approval and rejection decisions with approver metadata and expiration.
- `remediation-executor-service` re-validates policy, records dry-run validation, and blocks real execution unless approval, policy, RBAC, allowlists, and `EXECUTION_ENABLED=true` all permit it.
- ClickHouse stores `remediation_plans`, `remediation_approvals`, `remediation_executions`, `remediation_safety_violations`, and `remediation_policy_audit`.
- Redpanda topic `remediation.actions` stores compact lifecycle events.
- The agent tool gateway exposes only read-only remediation plan/execution/policy tools.
- Phase 8 does not run arbitrary shell commands, approve on behalf of users, mutate system namespaces, patch secrets/configmaps/RBAC, or execute LLM-generated commands.

```text
incidents/anomalies/investigations/chaos scores/knowledge
-> remediation-recommender-service
-> remediation_plans
-> approval-service
-> remediation_approvals
-> remediation-executor-service
-> dry-run validation / optional safe execution
-> remediation_executions
-> remediation.actions
```

## Phase 9 - UI / Command Center

Phase 9 makes Cascade usable from a browser instead of only scripts and service endpoints.

- `web/command-center` is a React + TypeScript + Vite UI with TanStack Query, React Router, lucide icons, dark-mode operator styling, and explicit loading/error/empty states.
- `command-center-api` is a FastAPI BFF that exposes same-origin `/api/*` routes and proxies only to fixed internal Cascade services.
- The dashboard shows counts, system health, recent anomalies, incidents, investigations, chaos runs/scores, and remediation plans.
- Telemetry, anomalies, incidents, knowledge, investigations, chaos, remediation, system health, and about pages cover the major Cascade capabilities.
- Safe actions include knowledge search, deterministic investigation creation, chaos dry-run plan/run, remediation plan creation, approval/rejection records, and remediation dry-run validation.
- Real remediation execution is disabled by default and blocked by the BFF. Real chaos execution controls are not exposed by default.

```text
Browser
-> command-center
-> command-center-api /api/*
-> retrieval/knowledge/agent/chaos/remediation services
```

## Current Stack

- Docker Desktop
- kind Kubernetes cluster
- kubectl
- PowerShell
- Python
- FastAPI
- React
- TypeScript
- Vite
- TanStack Query
- aiokafka
- Redpanda Kafka-compatible broker
- Prometheus
- Grafana
- OpenTelemetry
- Chaos Mesh
- ClickHouse
- Qdrant
- Google Online Boutique target app

## Repository Hygiene

- Secrets and environment-specific values must use local environment variables or an untracked `.env` file.
- `.env`, kubeconfig files, local database volumes, debug/demo/acceptance outputs, generated reports, and model artifacts are ignored.
- Use `.env.example` for safe placeholder configuration.
- Do not commit local Kubernetes configs, ClickHouse/Qdrant/Redpanda data directories, or exported telemetry/incident dumps.

## Remaining Roadmap

### Phase 10 - Production Hardening + Final Polish

Goal: add auth/RBAC, rate limiting, database backups, stronger secret hygiene, final `.gitignore` and security audit, sensitive API/database credential handling, production docs/polish, architecture diagrams, one-command demo, CI, screenshots/GIFs/video, and final portfolio polish.

## Author

Built as a high-complexity systems + AI project targeting SWE, Platform Engineering, and ML Infrastructure roles.

## License

MIT
