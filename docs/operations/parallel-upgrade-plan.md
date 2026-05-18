# Cascade Parallel Upgrade Plan

## Goal

Upgrade Cascade into a production-grade autonomous reliability platform through seven parallel workstreams while preserving safety, real API data, test coverage, and clean integration boundaries.

This plan is a coordination contract. Each workstream owns its assigned files and must document any necessary edits outside its boundary before opening a PR.

## Workstream Ownership

| Workstream | Branch | Primary Owner Scope |
|---|---|---|
| Target workload migration to Sock Shop | `codex/upgrade-sock-shop-target` | Target manifests, target docs, target service catalog, target-facing scripts/defaults |
| Graph-based blast-radius engine | `codex/upgrade-topology-blast-radius` | Topology service and shared topology graph module |
| Statistical causality engine | `codex/upgrade-statistical-causality` | Causal reconstruction service, causality stats module, causal report storage/API |
| Evidence-driven agent reports | `codex/upgrade-evidence-investigations` | Agent report schema/runtime/tool contracts, read-only evidence integration |
| Chaos/remediation safety hardening | `codex/upgrade-safety-hardening` | Chaos/remediation policy, approval enforcement, RBAC, NetworkPolicies |
| Local kind low-resource profile | `codex/upgrade-kind-low-resource` | Kubernetes resource profiles, low-resource overlays, infra tuning docs |
| Command Center intelligence UI | `codex/upgrade-command-center-intelligence` | Command Center API proxy additions, React UI panels/hooks/types |

## Branch Naming

Use exactly these branch names:

- `codex/upgrade-sock-shop-target`
- `codex/upgrade-topology-blast-radius`
- `codex/upgrade-statistical-causality`
- `codex/upgrade-evidence-investigations`
- `codex/upgrade-safety-hardening`
- `codex/upgrade-kind-low-resource`
- `codex/upgrade-command-center-intelligence`
- Integration branch after staged merges: `codex/upgrade-95-integration`

## Shared API Contracts

Existing APIs must remain backward compatible unless explicitly listed here.

| Service | Workstream | Allowed Additions |
|---|---|---|
| `topology-service` | Blast radius | `GET /topology/target`, `GET /topology/graph`, `POST /topology/blast-radius`, optional `GET /topology/{service}/dependencies?hops=&direction=` |
| `causal-reconstruction-service` | Causality | `POST /causality/analyze`, `GET /causality/reports/recent`, `GET /causality/reports/{report_id}` |
| `agent-tool-gateway` | Agent reports | Read-only tools for blast-radius and causal report retrieval only |
| `agent-orchestrator-service` | Agent reports | Extend investigation report payloads; keep `POST /investigations` compatible |
| `chaos-planner-service` | Safety | May consume richer blast-radius response; must keep `POST /plans` compatible |
| `remediation-*` | Safety | May extend policy/plan responses; must keep plan, approval, dry-run endpoints compatible |
| `command-center-api` | UI | May add proxy routes for `topology` and `causality`; dangerous POSTs remain blocked |

No workstream may remove or rename existing public endpoints without integration approval.

## Shared Data Contracts

| Contract | Owner | Allowed Shape |
|---|---|---|
| Active target workload | Sock Shop target | One canonical target object: workload name, namespace, frontend service, service allowlist, safe chaos targets, protected services |
| Topology graph | Blast radius | Nodes, edges, direction, criticality, metadata, graph version; existing `dependencies` response remains available |
| Blast radius report | Blast radius | `root_service`, `affected_services`, `upstream_services`, `downstream_services`, `paths`, `score`, `risk_level`, `evidence` |
| Causal report | Causality | `report_id`, `trigger`, `window`, `candidates`, `method`, `confidence`, `limitations`, `generated_at` |
| Causal candidate | Causality | `service`, `metric`, `lag_seconds`, `score`, optional `p_value`, `confidence`, `reason` |
| Investigation report JSON | Agent reports | Add hypothesis, evidence, rejected alternatives, topology support, causal support, citations, recommended next action |
| Safety policy | Safety | May add denied services, protected services, approval expiry requirements, rollback requirements, audit metadata |
| Command Center types | UI | Mirror API contracts without static mock data |

Shared ClickHouse schema changes must be made in both `services/shared/storage/clickhouse_client.py` and `infra/kubernetes/clickhouse/schema-job.yaml`.

## File Ownership Boundaries

| Workstream | Owns |
|---|---|
| Sock Shop target | `targets/sock-shop/**`, target workload docs, target-specific deploy/accept/demo script defaults, service allowlist source of truth |
| Blast radius | `services/topology-service/**`, `services/shared/topology/**`, topology unit tests |
| Causality | `services/causal-reconstruction-service/**`, `services/shared/causality/**`, causal report schema/tests |
| Agent reports | `services/shared/agents/**`, `services/agent-tool-gateway/**`, `services/agent-orchestrator-service/**`, agent tests |
| Safety hardening | `services/shared/chaos/**`, `services/shared/remediation/**`, chaos/remediation executors, approval service, RBAC/NetworkPolicy manifests |
| Low-resource profile | Kubernetes deployment resources, infra overlays, Redpanda/ClickHouse/Qdrant local tuning docs |
| Command Center UI | `web/command-center/**`, `services/command-center-api/**`, command-center API tests |

Any edit outside the owner scope must include a short PR note: file, reason, and affected workstreams.

## Conflict-Risk Files

Coordinate before editing these files:

- `services/shared/storage/clickhouse_client.py`
- `infra/kubernetes/clickhouse/schema-job.yaml`
- `services/command-center-api/app/main.py`
- `web/command-center/src/api/hooks.ts`
- `web/command-center/src/api/types.ts`
- `services/shared/agents/tool_contracts.py`
- `services/shared/chaos/schemas.py`
- `services/shared/remediation/schemas.py`
- `services/shared/knowledge/metadata.py`
- `scripts/accept-all.ps1`
- `README.md`
- `docs/architecture/final-architecture.md`

## Integration Dependencies

1. Sock Shop target lands first because topology, safety allowlists, scripts, docs, and UI defaults depend on the canonical target.
2. Blast-radius engine lands before chaos planner, agent report, and UI integrations consume blast-radius data.
3. Statistical causality lands before agent and UI causal panels consume causal reports.
4. Safety hardening may proceed in parallel, but final policy allowlists must rebase after Sock Shop target.
5. Command Center UI lands after topology and causality APIs are merged or behind graceful empty states.
6. Low-resource profile can land late, but must rebase after new service/env additions.

## Merge Order

1. `codex/upgrade-sock-shop-target`
2. `codex/upgrade-topology-blast-radius`
3. `codex/upgrade-statistical-causality`
4. `codex/upgrade-evidence-investigations`
5. `codex/upgrade-safety-hardening`
6. `codex/upgrade-kind-low-resource`
7. `codex/upgrade-command-center-intelligence`
8. Final integration branch: `codex/upgrade-95-integration`

## Required Validation Per Workstream

| Workstream | Required Commands |
|---|---|
| Sock Shop target | `python -m pytest tests`, `python -m ruff check services tests`, `kubectl kustomize targets/sock-shop` |
| Blast radius | `python -m pytest tests/test_topology_graph.py tests/test_chaos_core.py tests/test_agents_core.py` |
| Causality | `python -m pytest tests/test_causality_core.py tests/test_anomaly_detection_core.py` |
| Agent reports | `python -m pytest tests/test_agents_core.py tests/test_agent_investigation_reports.py` |
| Safety hardening | `python -m pytest tests/test_chaos_core.py tests/test_remediation_core.py tests/command_center_api/test_proxy.py` |
| Low-resource profile | `python -m pytest tests/test_k8s_resource_profiles.py`, `kubectl kustomize infra/kubernetes/overlays/low-resource` |
| Command Center UI | `cd web/command-center; npm run typecheck; npm run build`, `python -m pytest tests/command_center_api/test_proxy.py` |

If a listed new test file does not exist yet, the owning workstream must add it.

## Final Full-Repo Validation

Run from repo root after all merges:

```powershell
python -m compileall services tests
python -m pytest tests
python -m ruff check services tests
cd web\command-center
npm run typecheck
npm run build
cd C:\Cascade
.\scripts\ci-local.ps1 -SkipDockerBuild
.\scripts\accept-all.ps1
```

For cluster validation, also run the target-specific acceptance flow after Sock Shop deployment.

## Hard Rules

- No model may weaken safety gates.
- No model may delete tests to pass validation.
- No model may replace real API data with mock data.
- No model may make Online Boutique and Sock Shop both active canonical targets.
- No model may edit files outside its assigned ownership without documenting why.
- No model may introduce Neo4j, Go, Rust, or major new infrastructure yet.
- No model may remove existing public endpoints without integration approval.
- No model may make agents, chaos, remediation, or Command Center execute real mutations by default.
- No model may commit secrets, kubeconfigs, generated logs, build artifacts, backups, or support bundles.
- No model may overwrite unrelated user or teammate changes during conflict resolution.
