from __future__ import annotations

from .schemas import InvestigationRequest


def build_plan(request: InvestigationRequest) -> list[str]:
    plan = ["supervisor"]
    if request.trigger_type == "anomaly":
        plan.extend(["anomaly_analyst", "telemetry_analyst"])
    elif request.trigger_type == "incident":
        plan.extend(["incident_historian", "telemetry_analyst"])
    elif request.trigger_type == "service":
        plan.extend(["anomaly_analyst", "telemetry_analyst"])
    else:
        plan.append("knowledge_analyst")
    plan.extend(["topology_analyst", "knowledge_analyst", "incident_historian", "report_writer", "verifier_critic"])
    deduped = []
    for node in plan:
        if node not in deduped:
            deduped.append(node)
    return deduped[: request.max_steps]
