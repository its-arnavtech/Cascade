from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


UNKNOWN = "unknown"
UNAVAILABLE = "unavailable"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
NOT_APPLICABLE = "not_applicable"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ContractModel(BaseModel):
    """Canonical cross-service payload base with backwards-compatible extras."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_version: str = "cascade.contracts.v1"
    correlation_id: str = ""
    run_id: str = ""

    @model_validator(mode="after")
    def normalize_correlation(self):
        if not self.correlation_id:
            for attr in ("run_id", "autopilot_run_id", "execution_id", "verification_id", "rollback_plan_id", "report_id", "campaign_id", "experiment_id", "event_id"):
                value = str(getattr(self, attr, "") or "")
                if value:
                    self.correlation_id = value
                    break
        return self

    @classmethod
    def from_legacy(cls, payload: dict[str, Any] | BaseModel | None):
        data = payload.model_dump() if isinstance(payload, BaseModel) else dict(payload or {})
        canonical_schema = cls.model_fields["schema_version"].default or "cascade.contracts.v1"
        if data.get("schema_version") and data.get("schema_version") != canonical_schema:
            data.setdefault("legacy_schema_version", data["schema_version"])
        data["schema_version"] = canonical_schema
        return cls.model_validate(_alias_contract_fields(data))

    def to_legacy(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = UNKNOWN
    UNAVAILABLE = UNAVAILABLE
    INSUFFICIENT_EVIDENCE = INSUFFICIENT_EVIDENCE
    NOT_APPLICABLE = NOT_APPLICABLE


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = UNKNOWN
    UNAVAILABLE = UNAVAILABLE
    INSUFFICIENT_EVIDENCE = INSUFFICIENT_EVIDENCE
    NOT_APPLICABLE = NOT_APPLICABLE


class AutonomyLevel(IntEnum):
    READ_ONLY = 0
    RECOMMEND_ONLY = 1
    DRY_RUN_FIXES = 2
    AUTO_LOW_RISK = 3
    APPROVAL_FOR_RISKY = 4
    NEVER_ALLOWED = 5


class PolicyMode(StrEnum):
    READ_ONLY = "read_only"
    DRY_RUN = "dry_run"
    LOCAL_DEMO = "local_demo"
    PRODUCTION_SAFE = "production_safe"


class ServiceIdentity(ContractModel):
    schema_version: Literal["cascade.contracts.v1"] = "cascade.contracts.v1"
    service: str = UNKNOWN
    namespace: str = UNKNOWN
    workload: str = ""
    cluster: str = ""
    environment: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class TargetRef(ContractModel):
    schema_version: Literal["cascade.contracts.v1"] = "cascade.contracts.v1"
    service: str = UNKNOWN
    namespace: str = UNKNOWN
    workload: str = ""
    resource_kind: str = ""
    resource_name: str = ""
    selector: dict[str, Any] = Field(default_factory=dict)


class MetricWindow(ContractModel):
    schema_version: Literal["cascade.metric_window.v1"] = "cascade.metric_window.v1"
    window_id: str
    service: str = UNKNOWN
    namespace: str = UNKNOWN
    window_start: str
    window_end: str
    event_count: int = 0
    request_rate: float | None = None
    error_rate: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    readiness_rate: float | None = None
    availability_rate: float | None = None
    health_state: HealthState = HealthState.UNKNOWN
    evidence_quality: str = UNKNOWN
    metrics: dict[str, float | int | None] = Field(default_factory=dict)


class EvidenceBundle(ContractModel):
    schema_version: Literal["cascade.evidence_bundle.v1"] = "cascade.evidence_bundle.v1"
    bundle_id: str = Field(default_factory=lambda: "evidence_" + uuid.uuid4().hex[:24])
    created_at: str = Field(default_factory=_now_iso)
    target: TargetRef = Field(default_factory=TargetRef)
    quality: str = INSUFFICIENT_EVIDENCE
    summary: str = ""
    refs: list[dict[str, Any]] = Field(default_factory=list)
    metric_windows: list[MetricWindow] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AnomalyReport(ContractModel):
    schema_version: Literal["cascade.anomaly_report.v1"] = "cascade.anomaly_report.v1"
    anomaly_id: str
    detected_at: str
    target: TargetRef = Field(default_factory=TargetRef)
    severity: RiskLevel = RiskLevel.UNKNOWN
    status: str = UNKNOWN
    detector_type: str = UNKNOWN
    model_name: str = UNKNOWN
    anomaly_score: float = 0.0
    risk_score: float = 0.0
    explanation: str = ""
    evidence: EvidenceBundle | dict[str, Any] = Field(default_factory=EvidenceBundle)


class TopologySnapshot(ContractModel):
    schema_version: Literal["cascade.topology_snapshot.v1"] = "cascade.topology_snapshot.v1"
    snapshot_id: str
    captured_at: str
    discovery_status: str = UNKNOWN
    source_summary: dict[str, Any] = Field(default_factory=dict)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class RCAReport(ContractModel):
    schema_version: Literal["cascade.rca.v1"] = "cascade.rca.v1"
    report_id: str
    generated_at: str
    status: str = INSUFFICIENT_EVIDENCE
    target: TargetRef = Field(default_factory=TargetRef)
    target_service: str = UNKNOWN
    likely_root_cause_service: str = UNKNOWN
    affected_downstream_services: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    related_chaos_experiment: dict[str, Any] | None = None
    topology_snapshot_id: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    explanation: str = ""


class Recommendation(ContractModel):
    schema_version: Literal["cascade.recommendation.v1"] = "cascade.recommendation.v1"
    recommendation_id: str = Field(default_factory=lambda: "rec_" + uuid.uuid4().hex[:24])
    created_at: str = Field(default_factory=_now_iso)
    rca_report_id: str = ""
    anomaly_id: str = ""
    target: TargetRef = Field(default_factory=TargetRef)
    action_type: str = "investigate_only"
    summary: str = ""
    confidence: float = 0.0
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    evidence_bundle_id: str = ""
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)


class PolicyDecision(ContractModel):
    schema_version: Literal["cascade.policy_decision.v1"] = "cascade.policy_decision.v1"
    policy_decision_id: str = Field(default_factory=lambda: "policy_" + uuid.uuid4().hex[:24])
    decided_at: str = Field(default_factory=_now_iso)
    recommendation_id: str = ""
    allowed: bool
    status: str
    action_type: str
    mode: PolicyMode | str = PolicyMode.DRY_RUN
    autonomy_level: int = int(AutonomyLevel.DRY_RUN_FIXES)
    required_autonomy_level: int = int(AutonomyLevel.NEVER_ALLOWED)
    risk_level: RiskLevel | str = RiskLevel.UNKNOWN
    risk_score: float = 0.0
    blast_radius: int = 0
    requires_approval: bool = False
    dry_run_only: bool = False
    allowed_automatically: bool = False
    rollback_available: bool = False
    reasons: list[str] = Field(default_factory=list)


class RemediationPlan(ContractModel):
    schema_version: Literal["cascade.remediation_plan.v1"] = "cascade.remediation_plan.v1"
    plan_id: str
    created_at: str = Field(default_factory=_now_iso)
    status: str = UNKNOWN
    recommendation_id: str = ""
    rca_report_id: str = ""
    target: TargetRef = Field(default_factory=TargetRef)
    service: str = UNKNOWN
    namespace: str = UNKNOWN
    action_type: str = "investigate_only"
    action_summary: str = ""
    confidence: float = 0.0
    risk_level: RiskLevel | str = RiskLevel.UNKNOWN
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    policy_decision: PolicyDecision | dict[str, Any] | None = None
    rollback_steps: list[str] = Field(default_factory=list)
    post_checks: list[str] = Field(default_factory=list)


class RemediationExecution(ContractModel):
    schema_version: Literal["cascade.remediation_execution.v1"] = "cascade.remediation_execution.v1"
    execution_id: str
    plan_id: str
    started_at: str = Field(default_factory=_now_iso)
    completed_at: str | None = None
    status: str = UNKNOWN
    dry_run: bool = True
    executed: bool = False
    action_type: str = UNKNOWN
    target: TargetRef = Field(default_factory=TargetRef)
    service: str = UNKNOWN
    namespace: str = UNKNOWN
    policy_decision_id: str = ""
    rollback_available: bool = False
    output_summary: str = ""
    error_message: str = ""


class VerificationResult(ContractModel):
    schema_version: Literal["cascade.verification_result.v1"] = "cascade.verification_result.v1"
    verification_id: str
    execution_id: str
    plan_id: str
    completed_at: str = Field(default_factory=_now_iso)
    status: str = INSUFFICIENT_EVIDENCE
    evidence_quality: str = INSUFFICIENT_EVIDENCE
    rollback_status: str = NOT_APPLICABLE
    summary: str = ""
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class RollbackPlan(ContractModel):
    schema_version: Literal["cascade.rollback_plan.v1"] = "cascade.rollback_plan.v1"
    rollback_plan_id: str
    execution_id: str
    plan_id: str
    created_at: str = Field(default_factory=_now_iso)
    status: str = UNAVAILABLE
    rollback_type: str = UNKNOWN
    available: bool = False
    auto_executable: bool = False
    reason: str = ""
    actions: list[dict[str, Any]] = Field(default_factory=list)


class AutopilotStep(ContractModel):
    schema_version: Literal["cascade.autopilot_step.v1"] = "cascade.autopilot_step.v1"
    step_id: str
    run_id: str
    created_at: str = Field(default_factory=_now_iso)
    state: str
    status: str
    summary: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""


class AutopilotRun(ContractModel):
    schema_version: Literal["cascade.autopilot_run.v1"] = "cascade.autopilot_run.v1"
    run_id: str
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    completed_at: str | None = None
    status: str = UNKNOWN
    final_result: str = ""
    mode: str = "dry_run"
    trigger_type: str = "manual"
    trigger_id: str = ""
    target: TargetRef = Field(default_factory=TargetRef)
    anomaly_id: str = ""
    rca_report_id: str = ""
    recommendation_id: str = ""
    policy_decision_id: str = ""
    remediation_plan_id: str = ""
    execution_id: str = ""
    verification_id: str = ""
    rollback_plan_id: str = ""
    chaos_experiment_id: str = ""
    topology_snapshot_id: str = ""
    evidence_bundle_id: str = ""
    steps: list[AutopilotStep] = Field(default_factory=list)


class ChaosExperiment(ContractModel):
    schema_version: Literal["cascade.chaos_experiment.v1"] = "cascade.chaos_experiment.v1"
    experiment_id: str
    plan_id: str = ""
    run_id: str = ""
    experiment_kind: str = UNKNOWN
    target: TargetRef = Field(default_factory=TargetRef)
    status: str = UNKNOWN
    dry_run: bool = True
    approved: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    evidence_bundle_id: str = ""
    rca_report_id: str = ""
    verification_id: str = ""


class ChaosCampaign(ContractModel):
    schema_version: Literal["cascade.chaos_campaign.v1"] = "cascade.chaos_campaign.v1"
    campaign_id: str
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    status: str = UNKNOWN
    name: str = ""
    target_namespace: str = UNKNOWN
    allowed_services: list[str] = Field(default_factory=list)
    experiment_templates: list[dict[str, Any]] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    evidence_bundle_ids: list[str] = Field(default_factory=list)


class AuditEvent(ContractModel):
    schema_version: Literal["cascade.audit_event.v1"] = "cascade.audit_event.v1"
    event_id: str = Field(default_factory=lambda: "audit_" + uuid.uuid4().hex[:24])
    timestamp: str = Field(default_factory=_now_iso)
    event_type: str
    subsystem: str
    severity: str = "info"
    actor: str = "cascade-system"
    action: str = ""
    decision: str = ""
    status: str = ""
    risk_level: RiskLevel | str = RiskLevel.UNKNOWN
    policy_decision_id: str = ""
    remediation_execution_id: str = ""
    verification_id: str = ""
    rollback_plan_id: str = ""
    autopilot_run_id: str = ""
    chaos_experiment_id: str = ""
    campaign_id: str = ""
    rca_report_id: str = ""
    recommendation_id: str = ""
    topology_snapshot_id: str = ""
    evidence_bundle_id: str = ""
    evidence_summary: str = ""
    raw_payload_json: str = "{}"
    user_safe_message: str = ""


CONTRACT_MODELS: dict[str, type[ContractModel]] = {
    name: model
    for name, model in {
        "ServiceIdentity": ServiceIdentity,
        "TargetRef": TargetRef,
        "MetricWindow": MetricWindow,
        "AnomalyReport": AnomalyReport,
        "RCAReport": RCAReport,
        "TopologySnapshot": TopologySnapshot,
        "PolicyDecision": PolicyDecision,
        "RemediationPlan": RemediationPlan,
        "RemediationExecution": RemediationExecution,
        "VerificationResult": VerificationResult,
        "RollbackPlan": RollbackPlan,
        "AutopilotRun": AutopilotRun,
        "AutopilotStep": AutopilotStep,
        "ChaosExperiment": ChaosExperiment,
        "ChaosCampaign": ChaosCampaign,
        "AuditEvent": AuditEvent,
        "Recommendation": Recommendation,
        "EvidenceBundle": EvidenceBundle,
    }.items()
}

ENUM_CONTRACTS: dict[str, type[StrEnum] | type[IntEnum]] = {
    "HealthState": HealthState,
    "RiskLevel": RiskLevel,
    "AutonomyLevel": AutonomyLevel,
    "PolicyMode": PolicyMode,
}

EVENT_TOPIC_CONTRACTS: dict[str, type[ContractModel]] = {
    "anomalies.detected": AnomalyReport,
    "chaos.experiments": ChaosExperiment,
    "remediation.actions": RemediationExecution,
    "autopilot.runs": AutopilotRun,
    "causality.reports": RCAReport,
    "agent.investigations": EvidenceBundle,
}


class ContractEnvelope(ContractModel):
    schema_version: Literal["cascade.event_envelope.v1"] = "cascade.event_envelope.v1"
    event_id: str = Field(default_factory=lambda: "event_" + uuid.uuid4().hex[:24])
    event_type: str
    topic: str = ""
    emitted_at: str = Field(default_factory=_now_iso)
    producer: ServiceIdentity = Field(default_factory=ServiceIdentity)
    payload_schema: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


def canonical_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]}"


def normalize_policy_mode(value: str) -> str:
    value = (value or "").replace("-", "_")
    return value if value in {item.value for item in PolicyMode} else PolicyMode.DRY_RUN.value


def contract_schema_bundle() -> dict[str, Any]:
    defs: dict[str, Any] = {}
    for name, model in {**CONTRACT_MODELS, "ContractEnvelope": ContractEnvelope}.items():
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        defs[name] = {key: value for key, value in schema.items() if key != "$defs"}
        defs.update(schema.get("$defs", {}))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://cascade.local/schemas/cascade-contracts.schema.json",
        "title": "Cascade Integration Contracts",
        "type": "object",
        "$defs": defs,
        "oneOf": [{"$ref": f"#/$defs/{name}"} for name in sorted(CONTRACT_MODELS)],
    }


def _alias_contract_fields(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    if "target" not in result:
        target = {
            "service": result.get("service") or result.get("target_service") or result.get("likely_root_cause_service") or UNKNOWN,
            "namespace": result.get("namespace") or result.get("target_namespace") or UNKNOWN,
            "workload": result.get("workload") or result.get("target_workload") or "",
            "resource_kind": result.get("resource_kind") or "",
            "resource_name": result.get("resource_name") or "",
            "selector": result.get("selector") or result.get("target_selector") or {},
        }
        result["target"] = target
    if "target_service" not in result and isinstance(result.get("target"), dict):
        result["target_service"] = result["target"].get("service", UNKNOWN)
    if "service" not in result and isinstance(result.get("target"), dict):
        result["service"] = result["target"].get("service", UNKNOWN)
    if "namespace" not in result and isinstance(result.get("target"), dict):
        result["namespace"] = result["target"].get("namespace", UNKNOWN)
    if "correlation_id" not in result:
        result["correlation_id"] = result.get("run_id") or result.get("execution_id") or result.get("report_id") or result.get("event_id") or ""
    return result
