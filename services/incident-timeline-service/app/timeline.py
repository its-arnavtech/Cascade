from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import TimelineEvent


def parse_timestamp(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def build_timeline(experiment: dict[str, Any] | None, incident: dict[str, Any], topology_impact: dict[str, Any] | None) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    if experiment:
        events.append(
            TimelineEvent(
                timestamp=parse_timestamp(experiment.get("started_at")),
                event_type="experiment_started",
                service=experiment.get("target_service"),
                message=f"{experiment.get('experiment_type', 'experiment')} started against {experiment.get('target_service')}",
                severity="info",
            )
        )

    for evidence in incident.get("evidence", []) or []:
        events.append(
            TimelineEvent(
                timestamp=parse_timestamp(evidence.get("timestamp")),
                event_type="telemetry_anomaly",
                service=evidence.get("service"),
                message=f"Observed {', '.join(evidence.get('anomaly_flags', [])) or 'anomaly'} with status {evidence.get('derived_status')}",
                severity="warning",
            )
        )

    if topology_impact:
        events.append(
            TimelineEvent(
                timestamp=datetime.now(UTC),
                event_type="impact_assessed",
                service=topology_impact.get("root_service"),
                message=f"Potential impact path: {' -> '.join(topology_impact.get('impact_path', []))}",
                severity="info",
            )
        )

    events.append(
        TimelineEvent(
            timestamp=datetime.now(UTC),
            event_type="incident_report_generated",
            service=incident.get("root_cause_service"),
            message=f"Generated incident report with {incident.get('confidence', 'low')} confidence",
            severity="info",
        )
    )
    return sorted(events, key=lambda item: item.timestamp)
