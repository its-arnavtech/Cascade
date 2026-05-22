from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from .schemas import AutopilotMode, AutopilotResult, AutopilotRunRecord, AutopilotRunRequest, AutopilotState, AutopilotStepRecord


class AutopilotServiceClient(Protocol):
    async def detect_anomalies(self, service: str, namespace: str) -> dict[str, Any]: ...
    async def recent_anomalies(self, service: str, namespace: str, limit: int = 5) -> list[dict[str, Any]]: ...
    async def anomaly_detail(self, anomaly_id: str) -> dict[str, Any] | None: ...
    async def start_investigation(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def investigation_detail(self, investigation_id: str) -> dict[str, Any]: ...
    async def create_remediation_plan(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def remediation_policy(self) -> dict[str, Any]: ...
    async def dry_run_remediation(self, plan_id: str) -> dict[str, Any]: ...
    async def approval_status(self, plan_id: str) -> dict[str, Any]: ...
    async def execute_remediation(self, plan_id: str, approval_id: str) -> dict[str, Any]: ...
    async def recent_telemetry(self, service: str, namespace: str, limit: int = 50) -> list[dict[str, Any]]: ...


class AutopilotRecorder(Protocol):
    async def save_run(self, run: AutopilotRunRecord) -> None: ...
    async def add_step(self, step: AutopilotStepRecord) -> None: ...
    async def list_runs(self, limit: int = 20, service: str | None = None, status: str | None = None) -> list[dict[str, Any]]: ...
    async def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    async def get_steps(self, run_id: str) -> list[dict[str, Any]]: ...


class InMemoryAutopilotRecorder:
    def __init__(self) -> None:
        self.runs: dict[str, AutopilotRunRecord] = {}
        self.steps: dict[str, list[AutopilotStepRecord]] = {}

    async def save_run(self, run: AutopilotRunRecord) -> None:
        self.runs[run.run_id] = run.model_copy(deep=True)

    async def add_step(self, step: AutopilotStepRecord) -> None:
        self.steps.setdefault(step.run_id, []).append(step.model_copy(deep=True))

    async def list_runs(self, limit: int = 20, service: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        rows = [run.model_dump() for run in self.runs.values()]
        if service:
            rows = [row for row in rows if row.get("service") == service]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
        return rows[:limit]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = self.runs.get(run_id)
        return run.model_dump() if run else None

    async def get_steps(self, run_id: str) -> list[dict[str, Any]]:
        return [step.model_dump() for step in self.steps.get(run_id, [])]


class AutopilotWorkflow:
    def __init__(self, client: AutopilotServiceClient, recorder: AutopilotRecorder) -> None:
        self.client = client
        self.recorder = recorder

    async def run(self, request: AutopilotRunRequest) -> AutopilotRunRecord:
        now = _now()
        run = AutopilotRunRecord(
            run_id="auto_" + uuid.uuid4().hex[:18],
            created_at=now,
            updated_at=now,
            status=AutopilotState.REQUESTED,
            mode=request.mode,
            trigger_type=request.trigger_type,
            trigger_id=request.trigger_id,
            service=request.service,
            namespace=request.namespace,
            objective=request.objective,
        )
        await self._transition(run, AutopilotState.REQUESTED, "Autopilot run requested", request.model_dump(), {})
        try:
            anomaly = await self._detect(run, request)
            investigation = await self._investigate(run, request, anomaly)
            await self._bundle_evidence(run, anomaly, investigation)
            plan = await self._recommend(run, request, investigation)
            policy = await self._policy_check(run, plan)

            if request.mode == AutopilotMode.READ_ONLY:
                await self._finish(run, AutopilotState.UNCHANGED, AutopilotResult.UNCHANGED, "Read-only Autopilot completed without dry-run or execution")
                return run

            before = await self._health_snapshot(run.service, run.namespace)
            dry_run = await self._dry_run(run, plan)

            if request.mode == AutopilotMode.LOCAL_DEMO_EXECUTE:
                approved = await self._approval_or_wait(run, plan, policy)
                if not approved:
                    return run
                await self._apply(run, plan, approved["approval_id"])

            await self._verify(run, before, dry_run)
            return run
        except Exception as exc:
            run.error_message = str(exc)
            await self._finish(run, AutopilotState.FAILED, AutopilotResult.FAILED, f"Autopilot failed: {exc}")
            return run

    async def _detect(self, run: AutopilotRunRecord, request: AutopilotRunRequest) -> dict[str, Any] | None:
        await self._transition(run, AutopilotState.DETECTING, "Resolving anomaly trigger", {}, {})
        anomaly: dict[str, Any] | None = None
        if request.trigger_type == "anomaly" and request.trigger_id:
            anomaly = await self.client.anomaly_detail(request.trigger_id)
        elif request.trigger_type == "latest_anomaly":
            await self.client.detect_anomalies(request.service, request.namespace)
            rows = await self.client.recent_anomalies(request.service, request.namespace)
            anomaly = rows[0] if rows else None
        if anomaly:
            run.anomaly_id = str(anomaly.get("anomaly_id") or request.trigger_id)
            run.service = run.service or str(anomaly.get("service") or "")
            run.namespace = run.namespace or str(anomaly.get("namespace") or request.namespace)
        await self._transition(run, AutopilotState.DETECTING, "Anomaly trigger resolved", {}, {"anomaly": _compact(anomaly)})
        return anomaly

    async def _investigate(self, run: AutopilotRunRecord, request: AutopilotRunRequest, anomaly: dict[str, Any] | None) -> dict[str, Any]:
        await self._transition(run, AutopilotState.INVESTIGATING, "Starting deterministic investigation", {}, {})
        service = run.service or request.service or str((anomaly or {}).get("service") or "")
        payload = {
            "trigger_type": "anomaly" if anomaly else request.trigger_type,
            "trigger_id": run.anomaly_id or request.trigger_id,
            "service": service,
            "namespace": run.namespace or request.namespace,
            "objective": request.objective or f"Investigate reliability signal for {service or 'target service'}",
            "mode": "deterministic",
            "max_steps": 12,
        }
        created = await self.client.start_investigation(payload)
        run.investigation_id = str(created.get("investigation_id") or "")
        detail = await self.client.investigation_detail(run.investigation_id) if run.investigation_id else created
        await self._transition(run, AutopilotState.INVESTIGATING, "Investigation completed", payload, {"investigation": _compact(created)})
        return detail

    async def _bundle_evidence(self, run: AutopilotRunRecord, anomaly: dict[str, Any] | None, investigation: dict[str, Any]) -> None:
        report = _record(investigation.get("report"))
        evidence = {
            "anomaly": _compact(anomaly),
            "investigation_id": run.investigation_id,
            "summary": report.get("summary") or _record(investigation.get("run")).get("final_summary") or "",
            "suspected_root_cause": report.get("suspected_root_cause", ""),
            "evidence_refs": report.get("evidence") or _record(investigation.get("run")).get("evidence_refs") or [],
            "recommended_next_steps": report.get("recommended_next_steps", []),
            "suggested_remediation": report.get("suggested_remediation", []),
        }
        run.evidence = evidence
        await self._transition(run, AutopilotState.EVIDENCE_BUNDLED, "Evidence bundle created", {}, evidence)

    async def _recommend(self, run: AutopilotRunRecord, request: AutopilotRunRequest, investigation: dict[str, Any]) -> dict[str, Any]:
        await self._transition(run, AutopilotState.RECOMMENDING, "Creating remediation recommendation", {}, {})
        payload = {
            "trigger_type": "investigation" if run.investigation_id else request.trigger_type,
            "trigger_id": run.investigation_id or run.anomaly_id or request.trigger_id,
            "service": run.service or request.service,
            "namespace": run.namespace or request.namespace,
            "objective": request.objective,
            "preferred_action_type": request.preferred_action_type,
        }
        response = await self.client.create_remediation_plan(payload)
        plan = _record(response.get("plan")) or response
        run.remediation_plan_id = str(response.get("plan_id") or plan.get("plan_id") or "")
        run.proposed_action = str(plan.get("action_type") or request.preferred_action_type)
        run.recommendation = {"plan": _compact(plan), "response": _compact(response)}
        await self._transition(run, AutopilotState.RECOMMENDING, "Recommendation created", payload, {"plan_id": run.remediation_plan_id, "action_type": run.proposed_action})
        return plan

    async def _policy_check(self, run: AutopilotRunRecord, plan: dict[str, Any]) -> dict[str, Any]:
        await self._transition(run, AutopilotState.POLICY_CHECKING, "Checking remediation executor policy", {}, {})
        policy = await self.client.remediation_policy()
        run.action["policy"] = _compact(policy)
        await self._transition(run, AutopilotState.POLICY_CHECKING, "Policy captured", {}, {"policy": _compact(policy)})
        return policy

    async def _dry_run(self, run: AutopilotRunRecord, plan: dict[str, Any]) -> dict[str, Any]:
        await self._transition(run, AutopilotState.DRY_RUNNING, "Executing remediation dry-run", {}, {})
        result = await self.client.dry_run_remediation(run.remediation_plan_id)
        execution = _record(result.get("execution"))
        run.dry_run_execution_id = str(execution.get("execution_id") or "")
        run.action["dry_run"] = _compact(result)
        await self._transition(run, AutopilotState.DRY_RUNNING, "Dry-run completed", {"plan_id": run.remediation_plan_id}, {"execution": _compact(execution), "safety": _compact(result.get("safety"))})
        return result

    async def _approval_or_wait(self, run: AutopilotRunRecord, plan: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any] | None:
        status = await self.client.approval_status(run.remediation_plan_id)
        approval = _record(status.get("approval"))
        if status.get("approved") is True and approval.get("approval_id"):
            run.approval_id = str(approval["approval_id"])
            run.action["approval"] = _compact(approval)
            return approval
        run.action["approval_status"] = _compact(status)
        await self._transition(run, AutopilotState.WAITING_FOR_APPROVAL, "Real execution requires a current approval", {"plan_id": run.remediation_plan_id}, status)
        await self.recorder.save_run(run)
        return None

    async def _apply(self, run: AutopilotRunRecord, plan: dict[str, Any], approval_id: str) -> None:
        await self._transition(run, AutopilotState.APPLYING, "Applying allowed local-demo remediation", {}, {})
        result = await self.client.execute_remediation(run.remediation_plan_id, approval_id)
        execution = _record(result.get("execution"))
        run.execution_id = str(execution.get("execution_id") or "")
        run.action["execution"] = _compact(result)
        await self._transition(run, AutopilotState.APPLYING, "Execution completed", {"plan_id": run.remediation_plan_id, "approval_id": approval_id}, {"execution": _compact(execution)})

    async def _verify(self, run: AutopilotRunRecord, before: dict[str, Any], dry_run: dict[str, Any]) -> None:
        await self._transition(run, AutopilotState.VERIFYING, "Verifying post-loop health", {}, {})
        after = await self._health_snapshot(run.service, run.namespace)
        dry_execution = _record(dry_run.get("execution"))
        validation = str(dry_execution.get("validation_status") or "").lower()
        executed = bool(_record(run.action.get("execution")).get("execution", {}).get("executed") or _record(run.action.get("execution")).get("executed"))
        if "fail" in validation:
            result = AutopilotResult.DEGRADED
        elif executed and after["anomaly_count"] < before["anomaly_count"]:
            result = AutopilotResult.FIXED
        elif after["anomaly_count"] > before["anomaly_count"]:
            result = AutopilotResult.DEGRADED
        else:
            result = AutopilotResult.UNCHANGED
        run.verification = {"before": before, "after": after, "decision": result.value, "dry_run_validation": validation}
        await self._finish(run, AutopilotState(result.value), result, f"Verification completed with result={result.value}")

    async def _health_snapshot(self, service: str, namespace: str) -> dict[str, Any]:
        anomalies = await self.client.recent_anomalies(service, namespace, limit=20)
        telemetry = await self.client.recent_telemetry(service, namespace, limit=50)
        return {
            "service": service,
            "namespace": namespace,
            "anomaly_count": len(anomalies),
            "telemetry_count": len(telemetry),
            "latest_anomaly_id": str(anomalies[0].get("anomaly_id", "")) if anomalies else "",
        }

    async def _finish(self, run: AutopilotRunRecord, state: AutopilotState, result: AutopilotResult, summary: str) -> None:
        run.final_result = result.value
        run.completed_at = _now()
        await self._transition(run, state, summary, {}, {"final_result": result.value})

    async def _transition(self, run: AutopilotRunRecord, state: AutopilotState, summary: str, input_: dict[str, Any], output: dict[str, Any]) -> None:
        run.status = state.value
        run.updated_at = _now()
        await self.recorder.save_run(run)
        await self.recorder.add_step(
            AutopilotStepRecord(
                step_id="auto_step_" + uuid.uuid4().hex[:16],
                run_id=run.run_id,
                created_at=run.updated_at,
                state=state.value,
                status="failed" if state == AutopilotState.FAILED else "ok",
                summary=summary,
                input=_compact(input_),
                output=_compact(output),
                error_message=run.error_message if state == AutopilotState.FAILED else "",
            )
        )


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _compact(value: Any, max_items: int = 8) -> Any:
    if isinstance(value, dict):
        return {str(k): _compact(v, max_items) for k, v in list(value.items())[:max_items]}
    if isinstance(value, list):
        return [_compact(item, max_items) for item in value[:max_items]]
    return value


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
