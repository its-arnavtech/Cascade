from __future__ import annotations

from typing import Any, Awaitable, Callable

from .deterministic_planner import build_plan
from .reports import build_investigation_report
from .schemas import AgentState

ToolInvoker = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
StepRecorder = Callable[[str, str, str, dict[str, Any], dict[str, Any], str], Awaitable[None]]


class DeterministicGraphRuntime:
    def __init__(self, invoke_tool: ToolInvoker, record_step: StepRecorder | None = None) -> None:
        self.invoke_tool = invoke_tool
        self.record_step = record_step

    async def run(self, state: AgentState) -> dict[str, Any]:
        for node in build_plan(state.trigger):
            before = state.model_dump()
            output = await self._run_node(node, state)
            if self.record_step:
                await self.record_step(node, _role(node), "node", before, output, "ok")
        report = build_investigation_report(state)
        state.confidence = float(report["confidence"])
        state.conclusions = report
        return report

    async def _run_node(self, node: str, state: AgentState) -> dict[str, Any]:
        req = state.trigger
        if node == "supervisor":
            return {"plan": build_plan(req), "mode": req.mode}
        if node == "anomaly_analyst":
            if req.trigger_type == "anomaly" and req.trigger_id:
                result = await self._tool(state, "get_anomaly_by_id", {"anomaly_id": req.trigger_id})
                anomaly = result.get("data", {}).get("anomaly")
                if anomaly:
                    state.anomaly_refs.append(anomaly)
                    if not req.service:
                        req.service = anomaly.get("service")
            else:
                result = await self._tool(state, "get_recent_anomalies", {"limit": 5, "service": req.service, "namespace": req.namespace})
                state.anomaly_refs.extend(result.get("data", {}).get("anomalies", [])[:5])
                if state.anomaly_refs and not req.service:
                    req.service = state.anomaly_refs[0].get("service")
            return {"anomalies": len(state.anomaly_refs), "service": req.service}
        if node == "telemetry_analyst":
            service = req.service or _service(state)
            if service:
                workload = await self._tool(state, "get_target_workload", {"service": service, "limit": 10})
                data = workload.get("data", {})
                if data:
                    state.target_workload_evidence.append(data)
            if service:
                events = await self._tool(state, "get_service_events", {"service": service, "limit": 10})
                state.telemetry_evidence.extend(events.get("data", {}).get("events", [])[:10])
            features = await self._tool(state, "get_recent_feature_windows", {"limit": 10, "service": service})
            state.telemetry_evidence.extend(features.get("data", {}).get("features", [])[:10])
            return {"telemetry_items": len(state.telemetry_evidence)}
        if node == "topology_analyst":
            service = req.service or _service(state)
            if service:
                blast = await self._tool(state, "get_latest_blast_radius", {"root_service": service})
                if blast.get("data"):
                    state.blast_radius_evidence.append(blast["data"])
                impact = await self._tool(state, "get_service_impact", {"root_service": service})
                state.topology_evidence.append(impact.get("data", {}))
                up = await self._tool(state, "get_upstream_services", {"service": service})
                down = await self._tool(state, "get_downstream_services", {"service": service})
                state.topology_evidence.extend([up.get("data", {}), down.get("data", {})])
            else:
                topo = await self._tool(state, "get_topology", {})
                state.topology_evidence.append(topo.get("data", {}))
            return {"topology_items": len(state.topology_evidence)}
        if node == "knowledge_analyst":
            query = f"{req.objective} {req.service or _service(state)} anomaly incident runbook"
            search = await self._tool(state, "search_knowledge", {"query": query, "limit": 5, "filters": {}})
            state.knowledge_evidence.extend(search.get("data", {}).get("results", [])[:5])
            context = await self._tool(state, "build_knowledge_context", {"query": query, "limit": 5, "filters": {}})
            state.knowledge_evidence.extend(context.get("data", {}).get("evidence_chunks", [])[:5])
            return {"knowledge_items": len(state.knowledge_evidence)}
        if node == "incident_historian":
            service = req.service or _service(state)
            causal = await self._tool(state, "get_causal_report", {"incident_id": req.trigger_id, "service": service})
            if causal.get("data"):
                state.causal_report_evidence.append(causal["data"])
            incidents = await self._tool(state, "get_recent_incidents", {"limit": 5, "service": service})
            state.incident_refs.extend(incidents.get("data", {}).get("incidents", [])[:5])
            similar = await self._tool(state, "search_similar_incidents", {"query": req.objective, "limit": 5, "service": service})
            state.incident_refs.extend([item.get("payload", item) for item in similar.get("data", {}).get("results", [])[:5]])
            return {"incident_items": len(state.incident_refs)}
        if node == "report_writer":
            report = build_investigation_report(state)
            state.conclusions = report
            state.confidence = float(report["confidence"])
            return {"report_id": report["report_id"], "confidence": state.confidence}
        if node == "verifier_critic":
            evidence_count = sum(len(x) for x in [state.anomaly_refs, state.telemetry_evidence, state.topology_evidence, state.knowledge_evidence, state.incident_refs])
            state.conclusions["verification"] = "supported" if evidence_count else "low_evidence"
            if evidence_count == 0:
                state.confidence = min(state.confidence, 0.2)
            return {"evidence_count": evidence_count, "verification": state.conclusions["verification"]}
        return {"skipped": node}

    async def _tool(self, state: AgentState, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await self.invoke_tool(tool_name, payload)
        except Exception as exc:
            result = {"tool_name": tool_name, "status": "error", "data": {}, "evidence_refs": [], "error": f"{exc.__class__.__name__}: {exc}"}
        state.tool_call_history.append({
            "tool_name": tool_name,
            "status": result.get("status"),
            "evidence_refs": result.get("evidence_refs", []),
            "error": result.get("error") or "",
        })
        return result


def _role(node: str) -> str:
    return {
        "supervisor": "supervisor",
        "anomaly_analyst": "telemetry analyst",
        "telemetry_analyst": "telemetry analyst",
        "topology_analyst": "topology analyst",
        "knowledge_analyst": "knowledge analyst",
        "incident_historian": "incident historian",
        "report_writer": "report writer",
        "verifier_critic": "verifier/critic",
    }.get(node, "agent")


def _service(state: AgentState) -> str:
    for rows in [state.anomaly_refs, state.telemetry_evidence, state.incident_refs]:
        for row in rows:
            if row.get("service"):
                return str(row["service"])
            if row.get("root_cause_service"):
                return str(row["root_cause_service"])
    return ""
