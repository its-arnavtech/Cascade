from __future__ import annotations

from typing import Any

import httpx


async def collect_observation(
    retrieval_service_url: str,
    agent_orchestrator_url: str,
    service: str,
    namespace: str,
    window_seconds: int,
    trigger_agent: bool = False,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        events = await _get(client, f"{retrieval_service_url.rstrip('/')}/events/service/{service}", {"limit": 25})
        anomalies = await _get(client, f"{retrieval_service_url.rstrip('/')}/anomalies/service/{service}", {"limit": 25})
        incidents = await _get(client, f"{retrieval_service_url.rstrip('/')}/incidents/recent", {"limit": 25, "service": service})
        debug = await _get(client, f"{retrieval_service_url.rstrip('/')}/debug/counts", {})
        investigation_id = ""
        if trigger_agent:
            try:
                response = await client.post(
                    f"{agent_orchestrator_url.rstrip('/')}/investigations",
                    json={
                        "trigger_type": "service",
                        "service": service,
                        "namespace": namespace,
                        "objective": f"Investigate impact of Phase 7 chaos experiment on {service}",
                        "mode": "deterministic",
                        "max_steps": 12,
                    },
                )
                if response.status_code < 500:
                    investigation_id = response.json().get("investigation_id", "")
            except Exception:
                investigation_id = ""
    event_rows = events.get("events", []) if isinstance(events, dict) else []
    anomaly_rows = anomalies.get("anomalies", []) if isinstance(anomalies, dict) else []
    incident_rows = incidents.get("incidents", []) if isinstance(incidents, dict) else []
    affected = sorted({service, *[str(row.get("service", "")) for row in anomaly_rows if row.get("service")], *[str(row.get("root_cause_service", "")) for row in incident_rows if row.get("root_cause_service")]})
    return {
        "observation_window_seconds": window_seconds,
        "telemetry_events_count": len(event_rows),
        "anomaly_events_count": len(anomaly_rows),
        "incidents_count": len(incident_rows),
        "investigation_id": investigation_id,
        "affected_services": [item for item in affected if item],
        "telemetry_summary": {"sample": event_rows[:5], "debug_counts": debug},
        "anomaly_summary": {"sample": anomaly_rows[:5]},
        "incident_summary": {"sample": incident_rows[:5]},
    }


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        response = await client.get(url, params={k: v for k, v in params.items() if v not in (None, "")})
        if response.status_code < 500:
            return response.json()
    except Exception:
        return {}
    return {}
