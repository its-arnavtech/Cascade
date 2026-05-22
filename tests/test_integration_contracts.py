from __future__ import annotations

import json
from pathlib import Path

from services.shared.autopilot.events import autopilot_event
from services.shared.autopilot.schemas import AutopilotRunRecord
from services.shared.chaos.events import chaos_event
from services.shared.contracts import (
    CONTRACT_MODELS,
    EVENT_TOPIC_CONTRACTS,
    AnomalyReport,
    AutopilotRun,
    PolicyDecision,
    RCAReport,
    RemediationExecution,
    RemediationPlan,
    RiskLevel,
    contract_schema_bundle,
)
from services.shared.remediation.events import remediation_event


def test_contract_schema_bundle_is_generated_for_all_major_payloads() -> None:
    schema_path = Path("schemas/cascade-contracts.schema.json")
    assert schema_path.exists()
    generated = contract_schema_bundle()
    persisted = json.loads(schema_path.read_text(encoding="utf-8"))

    for name in CONTRACT_MODELS:
        assert name in generated["$defs"]
        assert name in persisted["$defs"]
        assert generated["$defs"][name]["properties"]["schema_version"]


def test_legacy_rca_report_adapts_to_canonical_contract() -> None:
    report = RCAReport.from_legacy(
        {
            "schema_version": "cascade.rca.v1",
            "report_id": "rca-report-1",
            "generated_at": "2026-05-21 10:00:00.000",
            "target_service": "catalogue",
            "likely_root_cause_service": "catalogue",
            "affected_downstream_services": ["front-end"],
            "confidence_score": 0.64,
            "evidence": [{"type": "anomaly", "id": "anomaly-1"}],
        }
    )

    assert report.target.service == "catalogue"
    assert report.correlation_id == "rca-report-1"
    assert report.status == "insufficient_evidence"


def test_policy_to_remediation_chain_uses_explicit_ids() -> None:
    decision = PolicyDecision(
        allowed=True,
        status="dry_run_only",
        action_type="restart_deployment",
        mode="dry_run",
        risk_level=RiskLevel.LOW,
        recommendation_id="rec-1",
    )
    plan = RemediationPlan.from_legacy(
        {
            "plan_id": "plan-1",
            "service": "catalogue",
            "namespace": "cascade-targets",
            "recommendation_id": "rec-1",
            "rca_report_id": "rca-report-1",
            "action_type": "restart_deployment",
            "policy_decision": decision.model_dump(),
        }
    )
    execution = RemediationExecution.from_legacy(
        {
            "execution_id": "exec-1",
            "plan_id": plan.plan_id,
            "service": "catalogue",
            "namespace": "cascade-targets",
            "action_type": plan.action_type,
            "policy_decision_id": decision.policy_decision_id,
        }
    )

    assert plan.recommendation_id == "rec-1"
    assert plan.rca_report_id == "rca-report-1"
    assert execution.correlation_id == "exec-1"
    assert execution.policy_decision_id == decision.policy_decision_id


def test_redpanda_topic_payload_contracts_accept_legacy_events() -> None:
    anomaly = AnomalyReport.from_legacy(
        {
            "anomaly_id": "anomaly-1",
            "detected_at": "2026-05-21 10:00:00.000",
            "service": "catalogue",
            "namespace": "cascade-targets",
            "severity": "high",
            "detector_type": "zscore",
            "model_name": "deterministic",
        }
    )
    chaos = EVENT_TOPIC_CONTRACTS["chaos.experiments"].from_legacy(
        chaos_event(
            "chaos.run.completed",
            plan={"plan_id": "chaos-plan-1", "experiment_kind": "pod_kill", "target_service": "catalogue", "target_namespace": "cascade-targets"},
            run={"run_id": "chaos-run-1", "experiment_id": "exp-1", "status": "completed", "dry_run": True},
        )
    )
    remediation = EVENT_TOPIC_CONTRACTS["remediation.actions"].from_legacy(
        remediation_event(
            "remediation.execution.completed",
            plan={"plan_id": "plan-1", "service": "catalogue", "namespace": "cascade-targets", "action_type": "restart_deployment"},
            execution={"execution_id": "exec-1", "plan_id": "plan-1", "status": "dry_run", "dry_run": True},
        )
    )

    assert anomaly.target.service == "catalogue"
    assert chaos.correlation_id == "chaos-run-1"
    assert remediation.correlation_id == "exec-1"


def test_autopilot_event_contains_contract_join_keys() -> None:
    run = AutopilotRunRecord(
        run_id="auto-1",
        created_at="2026-05-21 10:00:00.000",
        updated_at="2026-05-21 10:01:00.000",
        status="verify",
        mode="dry_run",
        trigger_type="anomaly",
        trigger_id="anomaly-1",
        service="catalogue",
        namespace="cascade-targets",
        anomaly_id="anomaly-1",
        investigation_id="investigation-1",
        remediation_plan_id="plan-1",
        execution_id="exec-1",
        proposed_action="restart_deployment",
        recommendation={"recommendation_id": "rec-1"},
        action={"policy_decision_id": "policy-1"},
        verification={"verification_id": "verify-1", "rollback_plan_id": "rollback-1"},
    )

    event = autopilot_event("autopilot.step.completed", run)
    canonical = AutopilotRun.from_legacy(event)

    assert event["correlation_id"] == "auto-1"
    assert event["recommendation_id"] == "rec-1"
    assert event["policy_decision_id"] == "policy-1"
    assert canonical.run_id == "auto-1"
