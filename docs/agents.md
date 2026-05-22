# Agent investigations - Agent Runtime

Agent investigations turns Cascade into an evidence-backed incident investigator. It adds a read-only tool gateway and an agent orchestrator that can gather telemetry, anomaly, topology, memory, and knowledge evidence, then produce a structured investigation report.

Agent investigations does not execute remediation, mutate Kubernetes resources, run chaos experiments, or provide a UI. The separate Autopilot service can consume investigation outputs as one step in a policy-gated loop, but the agent runtime itself remains read-only.

## Architecture

```text
telemetry / anomalies / incidents / topology / knowledge
-> agent-tool-gateway
-> agent-orchestrator-service
-> investigation_runs / agent_steps / agent_tool_calls / investigation_reports
-> agent.investigations
```

Existing Cascade services remain the source of truth. The agent runtime calls those services through safe tool contracts instead of duplicating storage or retrieval logic.

## Services

### agent-tool-gateway

The gateway exposes read-only tools over existing Cascade APIs:

- `get_recent_events`
- `get_service_events`
- `get_recent_feature_windows`
- `get_recent_anomalies`
- `get_anomaly_by_id`
- `get_service_anomalies`
- `get_recent_incidents`
- `get_incident_by_id`
- `search_knowledge`
- `build_knowledge_context`
- `get_topology`
- `get_upstream_services`
- `get_downstream_services`
- `get_service_impact`
- `search_similar_incidents`
- `generate_incident_timeline`
- `generate_investigation_report_template`
- `get_debug_counts`

Each tool returns a normalized response with status, data, evidence references, latency, and an error field.

### agent-orchestrator-service

The orchestrator runs deterministic investigation workflows, persists state in ClickHouse, and optionally publishes compact lifecycle events to Redpanda.

Key endpoints:

- `GET /health`
- `GET /ready`
- `GET /agents/status`
- `GET /tools`
- `POST /investigations`
- `POST /investigations/from-latest-anomaly`
- `GET /investigations`
- `GET /investigations/{investigation_id}`
- `GET /investigations/{investigation_id}/report`

## Investigation Graph

The deterministic runtime executes graph-style nodes:

- `supervisor`: chooses the investigation path and enforces limits.
- `anomaly_analyst`: inspects anomalies and feature-window evidence.
- `telemetry_analyst`: inspects telemetry and recent feature windows.
- `topology_analyst`: inspects upstream/downstream service impact.
- `knowledge_analyst`: retrieves runbooks and source-grounded knowledge context.
- `incident_historian`: searches similar incident memory.
- `report_writer`: assembles an evidence-backed report.
- `verifier_critic`: checks whether conclusions are supported by collected evidence.

## Deterministic Mode

`AGENT_RUNTIME_MODE=deterministic` is the default and is the mode used by acceptance. It does not require OpenAI, Anthropic, hosted inference, model downloads, GPUs, or cloud services.

The deterministic planner uses templates and the retrieved evidence only. If evidence is missing, reports say so instead of inventing details.

## Optional LangGraph / LLM Hooks

The service exposes configuration placeholders:

- `AGENT_RUNTIME_MODE=deterministic|langgraph`
- `LLM_PROVIDER=none|openai|local`
- `LLM_MODEL`
- `OPENAI_API_KEY`

External LLM mode is optional and not required by Agent investigations. If LangGraph or an LLM provider is unavailable, `/agents/status` reports deterministic mode as active.

## ClickHouse Schema

Agent investigations adds:

- `investigation_runs`
- `agent_steps`
- `investigation_reports`
- `agent_tool_calls`

These tables are created idempotently by the ClickHouse schema job.

## Redpanda Topic

Agent investigations adds the `agent.investigations` topic for compact lifecycle events:

- `investigation.started`
- `investigation.step.completed`
- `investigation.completed`
- `investigation.failed`

Full report bodies stay in ClickHouse, not Kafka.

## Safety Boundaries

- Tool contracts are read-only.
- Mutating tools are blocked in shared safety code.
- Suggested remediation is text only.
- No `kubectl` mutations are executed by Agent investigations services.
- No Chaos Mesh experiments are applied automatically.
- Remediation approval and execution live in the remediation services and can be orchestrated by Autopilot; Agent investigations remains read-only.

## Deployment

```powershell
.\scripts\deploy-agents.ps1
.\scripts\accept-agents.ps1
.\scripts\demo-agents.ps1
```

Reset only Agent investigations services:

```powershell
.\scripts\reset-agents.ps1
```

To intentionally clear Agent investigations ClickHouse rows during a local reset:

```powershell
.\scripts\reset-agents.ps1 -ClearAgentTables
```

## Acceptance Criteria

Acceptance verifies:

- Knowledge and RAG baseline services and tables are healthy.
- Agent investigations ClickHouse tables exist.
- `agent.investigations` exists.
- agent services are ready.
- tool registry includes required tools.
- representative tool calls return normalized responses.
- a deterministic investigation completes.
- run, step, tool-call, and report rows are persisted.
- the report includes evidence refs, confidence, limitations, and text-only remediation suggestions.

## Troubleshooting

Run:

```powershell
.\scripts\debug-agents.ps1
```

The debug script collects Kubernetes status, Redpanda topics, Agent investigations table counts, recent investigation rows, service logs, health endpoints, tool registry, agent status, and recent investigations.

## Known Limitations

- Deterministic mode is the default investigation engine.
- LangGraph/LLM mode is optional scaffolding only.
- No remediation execution inside the agent runtime.
- No autonomous chaos execution.
- No UI.
- No long-running async workflow engine yet; Agent investigations investigations run synchronously for local demos and acceptance.
- Recommendations require human review.
