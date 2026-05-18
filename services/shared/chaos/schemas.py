from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from services.shared.targets.catalog import ACTIVE_NAMESPACE, ACTIVE_PROTECTED_SERVICES, ACTIVE_SAFE_CHAOS_SERVICES


class ChaosPlanRequest(BaseModel):
    objective: str = "Validate service resilience with bounded chaos"
    target_service: str = "catalogue"
    target_namespace: str = ACTIVE_NAMESPACE
    target_workload: str | None = None
    experiment_kind: str = Field(default="pod_kill", pattern="^(pod_kill|network_delay|stress_cpu)$")
    duration_seconds: int = Field(default=30, ge=5, le=300)
    dry_run: bool = True


class ChaosRunRequest(BaseModel):
    plan_id: str
    approval_id: str = ""
    approved: bool = False
    dry_run: bool = True
    observation_window_seconds: int = Field(default=60, ge=5, le=600)
    trigger_agent_investigation: bool = True


class SafetyPolicy(BaseModel):
    allowed_namespaces: list[str] = Field(default_factory=lambda: [ACTIVE_NAMESPACE])
    denied_namespaces: list[str] = Field(default_factory=lambda: ["kube-system", "kube-public", "kube-node-lease", "local-path-storage", "monitoring", "cascade-system", "default"])
    allowed_services: list[str] = Field(default_factory=lambda: list(ACTIVE_SAFE_CHAOS_SERVICES))
    denied_services: list[str] = Field(default_factory=lambda: ["clickhouse", "redpanda", "qdrant", "postgres", "postgresql", "mysql", "mongodb", "kafka"])
    protected_services: list[str] = Field(default_factory=lambda: list(ACTIVE_PROTECTED_SERVICES) + ["clickhouse", "redpanda", "qdrant", "prometheus", "grafana", "chaos-controller-manager"])
    supported_kinds: list[str] = Field(default_factory=lambda: ["pod_kill", "network_delay", "stress_cpu"])
    supported_resource_kinds: list[str] = Field(default_factory=lambda: ["PodChaos", "NetworkChaos", "StressChaos"])
    denied_resource_kinds: list[str] = Field(default_factory=lambda: ["Namespace", "Secret", "ConfigMap", "Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding", "ServiceAccount", "PersistentVolumeClaim", "StatefulSet", "Job", "CronJob"])
    max_duration_seconds: int = 120
    max_target_count: int = 1
    require_approval_for_real_runs: bool = True
    required_labels: dict[str, str] = Field(default_factory=lambda: {"app.kubernetes.io/part-of": "cascade", "cascade.io/phase": "phase7", "cascade.io/managed-by": "chaos-executor-service"})


class SafetyResult(BaseModel):
    allowed: bool
    safety_score: float
    risk_level: str
    findings: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


class ChaosPlan(BaseModel):
    plan_id: str
    status: str
    plan_type: str = "controlled-chaos"
    experiment_kind: str
    target_namespace: str
    target_service: str
    target_workload: str = ""
    target_selector: dict[str, Any]
    duration_seconds: int
    blast_radius_score: float
    safety_score: float
    risk_level: str
    objective: str
    hypothesis: str
    expected_impact: str
    safety_policy: dict[str, Any]
    manifest: dict[str, Any]
    safety_findings: list[str] = Field(default_factory=list)


class ChaosRunResult(BaseModel):
    run_id: str
    plan_id: str
    experiment_id: str
    status: str
    dry_run: bool
    approved: bool
    cleanup_status: str = "not_required"
    observation: dict[str, Any] | None = None
    score: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    error: str = ""
