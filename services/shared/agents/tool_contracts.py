from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    target_service: str
    method: str
    path_template: str
    read_only: bool = True
    timeout_seconds: float = 10.0
    default_input: dict[str, Any] | None = None


TOOL_REGISTRY: dict[str, ToolContract] = {
    "get_recent_events": ToolContract("get_recent_events", "Fetch recent telemetry events.", "retrieval-service", "GET", "/events/recent"),
    "get_service_events": ToolContract("get_service_events", "Fetch recent telemetry for one service.", "retrieval-service", "GET", "/events/service/{service}"),
    "get_recent_feature_windows": ToolContract("get_recent_feature_windows", "Fetch recent feature windows.", "retrieval-service", "GET", "/features/recent"),
    "get_recent_anomalies": ToolContract("get_recent_anomalies", "Fetch recent anomaly events.", "retrieval-service", "GET", "/anomalies/recent"),
    "get_anomaly_by_id": ToolContract("get_anomaly_by_id", "Fetch an anomaly by ID.", "retrieval-service", "GET", "/anomalies/{anomaly_id}"),
    "get_service_anomalies": ToolContract("get_service_anomalies", "Fetch anomalies for one service.", "retrieval-service", "GET", "/anomalies/service/{service}"),
    "get_recent_incidents": ToolContract("get_recent_incidents", "Fetch recent incidents.", "retrieval-service", "GET", "/incidents/recent"),
    "get_incident_by_id": ToolContract("get_incident_by_id", "Fetch incident detail and reports.", "retrieval-service", "GET", "/incidents/{incident_id}"),
    "search_knowledge": ToolContract("search_knowledge", "Search source-grounded knowledge.", "knowledge-retrieval-service", "POST", "/knowledge/search"),
    "build_knowledge_context": ToolContract("build_knowledge_context", "Build source-grounded context pack.", "knowledge-retrieval-service", "POST", "/knowledge/context"),
    "get_topology": ToolContract("get_topology", "Fetch service dependency topology.", "topology-service", "GET", "/topology"),
    "get_upstream_services": ToolContract("get_upstream_services", "Fetch upstream services.", "topology-service", "GET", "/topology/{service}/upstream"),
    "get_downstream_services": ToolContract("get_downstream_services", "Fetch downstream services.", "topology-service", "GET", "/topology/{service}/downstream"),
    "get_service_impact": ToolContract("get_service_impact", "Estimate topology blast radius.", "topology-service", "POST", "/topology/impact"),
    "get_latest_blast_radius": ToolContract("get_latest_blast_radius", "Fetch the latest topology blast-radius estimate for a target service.", "topology-service", "POST", "/topology/blast-radius"),
    "get_causal_report": ToolContract("get_causal_report", "Fetch a statistical causality report without creating a new analysis.", "retrieval-service", "GET", "/causality/reports/recent"),
    "get_recent_rca_reports": ToolContract("get_recent_rca_reports", "Fetch recent RCA evidence bundles.", "retrieval-service", "GET", "/rca/recent"),
    "get_rca_report": ToolContract("get_rca_report", "Fetch one RCA evidence bundle.", "retrieval-service", "GET", "/rca/{report_id}"),
    "get_target_workload": ToolContract("get_target_workload", "Resolve the canonical active target workload and service catalog.", "topology-service", "GET", "/target/workload"),
    "search_similar_incidents": ToolContract("search_similar_incidents", "Search incident memory.", "retrieval-service", "POST", "/memory/search"),
    "generate_incident_timeline": ToolContract("generate_incident_timeline", "Generate incident timeline template.", "incident-timeline-service", "POST", "/timeline"),
    "generate_investigation_report_template": ToolContract("generate_investigation_report_template", "Generate incident report template.", "incident-timeline-service", "POST", "/report"),
    "get_debug_counts": ToolContract("get_debug_counts", "Fetch debug row and point counts.", "retrieval-service", "GET", "/debug/counts"),
    "get_recent_chaos_runs": ToolContract("get_recent_chaos_runs", "Fetch recent Phase 7 chaos runs.", "chaos-executor-service", "GET", "/runs"),
    "get_chaos_run": ToolContract("get_chaos_run", "Fetch one Phase 7 chaos run detail.", "chaos-executor-service", "GET", "/runs/{run_id}"),
    "get_recent_resilience_scores": ToolContract("get_recent_resilience_scores", "Fetch recent resilience scores.", "chaos-executor-service", "GET", "/scores/recent"),
    "get_safety_policy": ToolContract("get_safety_policy", "Fetch active chaos safety policy.", "chaos-executor-service", "GET", "/safety/policy"),
    "get_recent_remediation_plans": ToolContract("get_recent_remediation_plans", "Fetch recent Phase 8 remediation plans.", "remediation-recommender-service", "GET", "/plans"),
    "get_remediation_plan": ToolContract("get_remediation_plan", "Fetch one Phase 8 remediation plan.", "remediation-recommender-service", "GET", "/plans/{plan_id}"),
    "get_recent_remediation_executions": ToolContract("get_recent_remediation_executions", "Fetch recent Phase 8 remediation dry-run/execution records.", "remediation-executor-service", "GET", "/executions"),
    "get_recent_remediation_verifications": ToolContract("get_recent_remediation_verifications", "Fetch recent post-remediation verification results.", "remediation-executor-service", "GET", "/verifications"),
    "get_remediation_verification": ToolContract("get_remediation_verification", "Fetch one post-remediation verification result.", "remediation-executor-service", "GET", "/verifications/{verification_id}"),
    "get_recent_remediation_rollback_plans": ToolContract("get_recent_remediation_rollback_plans", "Fetch recent remediation rollback plans.", "remediation-executor-service", "GET", "/rollback-plans"),
    "get_remediation_rollback_plan": ToolContract("get_remediation_rollback_plan", "Fetch one remediation rollback plan.", "remediation-executor-service", "GET", "/rollback-plans/{rollback_plan_id}"),
    "get_remediation_safety_policy": ToolContract("get_remediation_safety_policy", "Fetch active remediation safety policy.", "remediation-executor-service", "GET", "/safety/policy"),
    "evaluate_remediation_policy": ToolContract("evaluate_remediation_policy", "Evaluate a proposed remediation action against policy without mutation.", "remediation-recommender-service", "POST", "/policy/evaluate"),
}


MUTATING_TOOL_NAMES = {"restart_deployment", "scale_deployment", "delete_pod", "apply_chaos", "patch_resource", "execute_remediation", "approve_remediation", "reject_remediation"}
