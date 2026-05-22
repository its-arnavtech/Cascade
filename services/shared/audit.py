from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AuditSubsystem = Literal[
    "telemetry",
    "anomaly",
    "RCA",
    "policy",
    "remediation",
    "verification",
    "rollback",
    "Autopilot",
    "chaos",
    "topology",
    "campaigns",
    "UI/user action",
    "system/deployment",
]

AuditSeverity = Literal["debug", "info", "warning", "error", "critical"]

SENSITIVE_KEY_PATTERN = re.compile(
    r"(token|password|passwd|secret|api[_-]?key|authorization|bearer|kubeconfig|connection[_-]?string|connstr|credential|private[_-]?key|client[_-]?secret|client[_-]?(key|certificate)[_-]?data|session)",
    re.IGNORECASE,
)
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(Bearer\s+)[A-Za-z0-9._~+/=-]+|([?&](?:token|api_key|apikey|password|client_secret)=)[^&\s]+|([a-z][a-z0-9+.-]*://[^:/\s]+:)[^@\s]+(@)|\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b",
    re.IGNORECASE,
)
REDACTED = "[REDACTED]"


class AuditEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: "audit_" + uuid.uuid4().hex[:24])
    timestamp: str = Field(default_factory=lambda: _now())
    event_type: str
    subsystem: AuditSubsystem
    severity: AuditSeverity = "info"
    run_id: str = ""
    correlation_id: str = ""
    service: str = ""
    namespace: str = ""
    actor: str = "cascade-system"
    action: str = ""
    decision: str = ""
    status: str = ""
    risk_level: str = ""
    policy_decision_id: str = ""
    remediation_execution_id: str = ""
    verification_id: str = ""
    rollback_plan_id: str = ""
    autopilot_run_id: str = ""
    chaos_experiment_id: str = ""
    campaign_id: str = ""
    rca_report_id: str = ""
    topology_node_or_edge_id: str = ""
    evidence_summary: str = ""
    raw_payload_json: str = "{}"
    user_safe_message: str = ""

    def to_clickhouse_row(self) -> dict[str, Any]:
        data = self.model_dump()
        data["raw_payload_json"] = json_dumps(redact(json_loads(data["raw_payload_json"])))
        data["evidence_summary"] = data["evidence_summary"][:1000]
        data["user_safe_message"] = data["user_safe_message"][:1000]
        return data


def build_audit_event(
    event_type: str,
    subsystem: AuditSubsystem,
    *,
    severity: AuditSeverity = "info",
    payload: dict[str, Any] | None = None,
    timestamp: str | None = None,
    run_id: str = "",
    correlation_id: str = "",
    service: str = "",
    namespace: str = "",
    actor: str = "cascade-system",
    action: str = "",
    decision: str = "",
    status: str = "",
    risk_level: str = "",
    policy_decision_id: str = "",
    remediation_execution_id: str = "",
    verification_id: str = "",
    rollback_plan_id: str = "",
    autopilot_run_id: str = "",
    chaos_experiment_id: str = "",
    campaign_id: str = "",
    rca_report_id: str = "",
    topology_node_or_edge_id: str = "",
    evidence_summary: str = "",
    user_safe_message: str = "",
) -> AuditEvent:
    safe_payload = redact(payload or {})
    return AuditEvent(
        timestamp=timestamp or _now(),
        event_type=event_type,
        subsystem=subsystem,
        severity=severity,
        run_id=run_id,
        correlation_id=correlation_id or run_id or remediation_execution_id or autopilot_run_id or chaos_experiment_id or campaign_id or rca_report_id,
        service=service,
        namespace=namespace,
        actor=actor or "cascade-system",
        action=action or event_type,
        decision=decision,
        status=status,
        risk_level=risk_level,
        policy_decision_id=policy_decision_id,
        remediation_execution_id=remediation_execution_id,
        verification_id=verification_id,
        rollback_plan_id=rollback_plan_id,
        autopilot_run_id=autopilot_run_id,
        chaos_experiment_id=chaos_experiment_id,
        campaign_id=campaign_id,
        rca_report_id=rca_report_id,
        topology_node_or_edge_id=topology_node_or_edge_id,
        evidence_summary=evidence_summary[:1000],
        raw_payload_json=json_dumps(safe_payload),
        user_safe_message=(user_safe_message or evidence_summary or event_type)[:1000],
    )


async def emit_audit_event(client: Any, event: AuditEvent) -> None:
    await client.insert_audit_event(event.to_clickhouse_row())


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if SENSITIVE_KEY_PATTERN.search(str(key)):
                result[str(key)] = REDACTED
            else:
                result[str(key)] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SENSITIVE_VALUE_PATTERN.sub(_redact_match, value)
    return value


def _redact_match(match: re.Match[str]) -> str:
    if match.group(1):
        return match.group(1) + REDACTED
    if match.group(2):
        return match.group(2) + REDACTED
    if match.group(3):
        return match.group(3) + REDACTED + (match.group(4) or "")
    return REDACTED


def json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def json_loads(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
