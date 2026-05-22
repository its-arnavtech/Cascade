# Cascade integration contracts

Cascade subsystems should exchange the canonical contracts in `services/shared/contracts.py` at service and event boundaries. Existing services may keep local models internally, but adapters should normalize outbound payloads before they cross API, Redpanda, ClickHouse JSON, or Command Center boundaries.

## Canonical contracts

The contract layer defines these major payloads:

| Contract | Purpose |
| --- | --- |
| `ServiceIdentity` | Identifies a Cascade service or target workload producer. |
| `TargetRef` | Identifies the namespace, service, workload, resource, or selector being observed or changed. |
| `MetricWindow` | Normalized telemetry window with explicit missing-data state. |
| `AnomalyReport` | Detector output tied to a target and evidence. |
| `RCAReport` | Root-cause analysis output, including topology and chaos links. |
| `TopologySnapshot` | Nodes, edges, dependency map, discovery status, warnings, and limitations. |
| `PolicyDecision` | Safety gate decision for a recommendation/action. |
| `RemediationPlan` | Proposed action with recommendation, RCA, policy, rollback, and post-check references. |
| `RemediationExecution` | Dry-run or real execution record. |
| `VerificationResult` | Post-remediation comparison and explicit evidence quality. |
| `RollbackPlan` | Available or unavailable rollback plan with reason and actions. |
| `AutopilotRun` / `AutopilotStep` | Closed-loop orchestration state and step log. |
| `ChaosExperiment` / `ChaosCampaign` | Experiment and campaign records linked back to telemetry/RCA/verification. |
| `AuditEvent` | Append-only audit record for all major objects. |
| `Recommendation` | RCA-to-action recommendation object. |
| `EvidenceBundle` | Shared evidence references and metric windows. |

Enums standardize `HealthState`, `RiskLevel`, `AutonomyLevel`, and `PolicyMode`. Unknown or missing data must be represented explicitly with `unknown`, `unavailable`, `insufficient_evidence`, or `not_applicable`; do not invent values to satisfy a schema.

## Object relationships

Use these IDs to wire product flow later:

1. `AnomalyReport.anomaly_id` and `TopologySnapshot.snapshot_id` feed `RCAReport`.
2. `RCAReport.report_id` feeds `Recommendation.rca_report_id`.
3. `Recommendation.recommendation_id` feeds `PolicyDecision.recommendation_id`.
4. `PolicyDecision.policy_decision_id` and `Recommendation.recommendation_id` feed `RemediationPlan`.
5. `RemediationPlan.plan_id` feeds `RemediationExecution.plan_id`.
6. `RemediationExecution.execution_id` feeds `VerificationResult.execution_id`.
7. `VerificationResult.rollback_plan_id` ties to `RollbackPlan.rollback_plan_id` when rollback is available.
8. `AutopilotRun.run_id` ties together anomaly, RCA, recommendation, policy, remediation, verification, rollback, chaos, topology, and evidence IDs.
9. `ChaosExperiment.experiment_id` and campaign `run_ids` link chaos activity to telemetry, RCA, and verification.
10. `AuditEvent` should include the relevant object IDs plus `correlation_id`.

## Correlation conventions

`correlation_id` is the stable workflow join key. Prefer `AutopilotRun.run_id` when an Autopilot loop owns the work. Otherwise use the most concrete lifecycle ID available: execution ID, chaos run ID, RCA report ID, audit event ID, or evidence bundle ID.

`run_id` identifies a concrete run within a subsystem. It can equal `correlation_id`, but it should not replace more specific IDs such as `execution_id`, `verification_id`, or `rollback_plan_id`.

## Event topics

Current Redpanda topic-to-contract mapping:

| Topic | Canonical payload |
| --- | --- |
| `anomalies.detected` | `AnomalyReport` |
| `chaos.experiments` | `ChaosExperiment` |
| `remediation.actions` | `RemediationExecution` |
| `autopilot.runs` | `AutopilotRun` |
| `causality.reports` | `RCAReport` |
| `agent.investigations` | `EvidenceBundle` |

Legacy event builders still emit their existing `schema_version` values for compatibility. They now add `contract_schema_version`, `correlation_id`, and join IDs where available.

## JSON schemas and Command Center

The generated JSON Schema bundle lives at `schemas/cascade-contracts.schema.json`. Regenerate it with:

```powershell
python scripts/generate-contract-schemas.py
```

Command Center exposes the same bundle at `GET /api/contracts` so the UI and future clients can discover schemas and topic mappings through the proxy.

Frontend contract mirrors live in `web/command-center/src/api/types.ts`. These are intentionally permissive with `JsonRecord` extras so older services can keep returning legacy fields while new wiring uses canonical IDs.

## Migration notes

Compatibility shims should call `from_legacy()` on canonical models at boundaries. This preserves legacy fields as extras, records mismatched legacy schema versions as `legacy_schema_version`, and fills `TargetRef` from older `service`, `namespace`, `target_service`, and `target_namespace` fields.

Do not rewrite service internals solely to use these models. Normalize payloads at API, event, storage JSON, and UI boundaries, then migrate local implementation models only when a feature naturally touches them.
