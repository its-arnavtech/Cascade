from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def remediation_steps(action_type: str, service: str, namespace: str) -> list[str]:
    if action_type == "restart_deployment":
        return [
            f"Confirm recent anomaly and investigation evidence for deployment/{service} in namespace {namespace}.",
            f"Run server-side dry-run validation for deployment/{service}.",
            f"If approved and execution is explicitly enabled, restart only deployment/{service} in {namespace}.",
            "Watch rollout status and service health before closing the plan.",
        ]
    if action_type == "scale_deployment_noop":
        return [
            f"Read current replica count for deployment/{service} in {namespace}.",
            "Validate a server-side dry-run scale request using the same replica count.",
            "Do not change the live replica count during default Phase 8 workflows.",
        ]
    if action_type == "rollback_deployment":
        return [
            f"Inspect rollout history for deployment/{service} in {namespace}.",
            "Identify the last known healthy revision from incident and deployment history.",
            "Prepare rollback command text for human review; Phase 8 does not execute rollback by default.",
        ]
    if action_type == "cleanup_cascade_chaos_resource":
        return [
            "List Cascade-managed Chaos Mesh resources with required phase7 labels.",
            "Dry-run deletion of only the named managed chaos resource.",
            "Execute cleanup only when labels match the safety policy and execution is explicitly enabled.",
        ]
    return [
        "Review the linked anomaly, incident, investigation, chaos, and runbook evidence.",
        f"Inspect deployment/{service} and related pods in {namespace}.",
        "Collect fresh telemetry after the investigation window before considering any mutation.",
    ]


def rollback_steps(action_type: str, service: str, namespace: str) -> list[str]:
    if action_type == "restart_deployment":
        return [
            f"Monitor deployment/{service} rollout status in {namespace}.",
            "If health worsens, stop further action and keep the previous ReplicaSet available.",
            "Escalate to manual rollback only after reviewing deployment rollout history.",
        ]
    if action_type == "scale_deployment_noop":
        return ["No live replica change is made by this template; rollback is not required."]
    if action_type == "cleanup_cascade_chaos_resource":
        return ["If cleanup removes an active experiment unexpectedly, recreate only from the previously stored Phase 7 plan after review."]
    return ["No mutation is performed by this recommendation; rollback is to stop and reassess evidence."]


def pre_checks(service: str, namespace: str) -> list[str]:
    return [
        f"Verify deployment/{service} exists in {namespace}.",
        "Verify recent telemetry still shows the suspected symptom.",
        "Verify no denied namespace or broad selector is in scope.",
    ]


def post_checks(service: str, namespace: str) -> list[str]:
    return [
        f"Check deployment/{service} readiness in {namespace}.",
        "Check recent anomaly count and service health.",
        "Record outcome in remediation execution evidence.",
    ]


def dry_run_manifest(action_type: str, service: str, namespace: str) -> dict[str, Any]:
    if action_type in {"restart_deployment", "scale_deployment_noop", "rollback_deployment"}:
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": service,
                "namespace": namespace,
                "annotations": {"cascade.io/remediation-dry-run": datetime.now(UTC).isoformat()},
            },
        }
    if action_type == "cleanup_cascade_chaos_resource":
        return {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": "PodChaos",
            "metadata": {"name": service, "namespace": namespace, "labels": {"cascade.io/phase": "phase7", "cascade.io/managed-by": "chaos-executor-service"}},
        }
    return {}


def command_preview(action_type: str, service: str, namespace: str) -> list[str]:
    if action_type == "restart_deployment":
        return [f"kubectl -n {namespace} rollout restart deployment/{service}", f"kubectl -n {namespace} rollout status deployment/{service}"]
    if action_type == "scale_deployment_noop":
        return [f"kubectl -n {namespace} scale deployment/{service} --replicas=<current-replicas> --dry-run=server"]
    if action_type == "rollback_deployment":
        return [f"kubectl -n {namespace} rollout history deployment/{service}", f"kubectl -n {namespace} rollout undo deployment/{service} --dry-run=server"]
    return []

