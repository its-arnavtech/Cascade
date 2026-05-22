from __future__ import annotations

from typing import Any

from kubernetes import client, config
from kubernetes.client import ApiException


class KubernetesRemediationClient:
    def __init__(self) -> None:
        self.active_context = ""
        try:
            config.load_incluster_config()
            self.active_context = "in-cluster"
        except Exception:
            _, active_context = config.list_kube_config_contexts()
            config.load_kube_config()
            self.active_context = str((active_context or {}).get("name") or "")
        self.apps = client.AppsV1Api()
        self.core = client.CoreV1Api()

    def ready(self, namespace: str = "cascade-targets") -> bool:
        try:
            self.core.list_namespaced_pod(namespace=namespace, limit=1)
            return True
        except Exception:
            return False

    def current_context(self) -> str:
        return self.active_context

    def deployment_exists(self, namespace: str, name: str) -> bool:
        try:
            self.apps.read_namespaced_deployment(name=name, namespace=namespace)
            return True
        except ApiException as exc:
            if exc.status == 404:
                return False
            raise

    def current_replicas(self, namespace: str, name: str) -> int:
        deployment = self.apps.read_namespaced_deployment(name=name, namespace=namespace)
        return int(deployment.spec.replicas or 0)

    def deployment_snapshot(self, namespace: str, name: str) -> dict[str, Any]:
        deployment = self.apps.read_namespaced_deployment(name=name, namespace=namespace)
        selector = deployment.spec.selector.match_labels or {}
        label_selector = ",".join(f"{key}={value}" for key, value in selector.items())
        pods = self.core.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items if label_selector else []
        events = self.core.list_namespaced_event(namespace=namespace, limit=100).items
        pod_rows = []
        ready_pods = 0
        restart_count = 0
        for pod in pods:
            statuses = pod.status.container_statuses or []
            pod_ready = any(condition.type == "Ready" and condition.status == "True" for condition in (pod.status.conditions or []))
            ready_pods += 1 if pod_ready else 0
            restarts = sum(int(status.restart_count or 0) for status in statuses)
            restart_count += restarts
            pod_rows.append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "ready": pod_ready,
                "restart_count": restarts,
            })
        related_events = [
            {
                "type": event.type,
                "reason": event.reason,
                "message": event.message,
                "object_kind": event.involved_object.kind if event.involved_object else "",
                "object_name": event.involved_object.name if event.involved_object else "",
            }
            for event in events
            if _event_mentions(event, name, {pod["name"] for pod in pod_rows})
        ][:20]
        replicas = int(deployment.spec.replicas or 0)
        available = int(deployment.status.available_replicas or 0)
        ready = int(deployment.status.ready_replicas or 0)
        return {
            "kind": "Deployment",
            "name": deployment.metadata.name,
            "namespace": deployment.metadata.namespace,
            "replicas": replicas,
            "available_replicas": available,
            "ready_replicas": ready,
            "updated_replicas": int(deployment.status.updated_replicas or 0),
            "observed_generation": int(deployment.status.observed_generation or 0),
            "pod_count": len(pod_rows),
            "ready_pods": ready_pods,
            "restart_count": restart_count,
            "availability": (available / replicas) if replicas else 0.0,
            "template_metadata": {
                "labels": dict((deployment.spec.template.metadata.labels or {}).items()),
                "annotations": dict((deployment.spec.template.metadata.annotations or {}).items()),
            },
            "pods": pod_rows,
            "warning_events_count": len([event for event in related_events if str(event.get("type", "")).lower() == "warning"]),
            "events": related_events,
        }

    def dry_run_deployment_annotation(self, namespace: str, name: str, plan_id: str) -> dict[str, Any]:
        body = {"spec": {"template": {"metadata": {"annotations": {"cascade.io/remediation-plan": plan_id}}}}}
        result = self.apps.patch_namespaced_deployment(name=name, namespace=namespace, body=body, dry_run="All")
        return {"kind": "Deployment", "name": result.metadata.name, "namespace": result.metadata.namespace, "dry_run": True}

    def dry_run_scale_noop(self, namespace: str, name: str) -> dict[str, Any]:
        replicas = self.current_replicas(namespace, name)
        body = {"spec": {"replicas": replicas}}
        result = self.apps.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body, dry_run="All")
        return {"kind": "Deployment", "name": result.metadata.name, "namespace": result.metadata.namespace, "replicas": replicas, "dry_run": True}

    def restart_deployment(self, namespace: str, name: str, plan_id: str) -> dict[str, Any]:
        body = {"spec": {"template": {"metadata": {"annotations": {"cascade.io/restarted-by": "remediation-executor-service", "cascade.io/remediation-plan": plan_id}}}}}
        result = self.apps.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
        return {"kind": "Deployment", "name": result.metadata.name, "namespace": result.metadata.namespace, "executed": True}

    def scale_noop(self, namespace: str, name: str) -> dict[str, Any]:
        replicas = self.current_replicas(namespace, name)
        body = {"spec": {"replicas": replicas}}
        result = self.apps.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
        return {"kind": "Deployment", "name": result.metadata.name, "namespace": result.metadata.namespace, "replicas": replicas, "executed": True}

    def rollback_replicas(self, namespace: str, name: str, replicas: int) -> dict[str, Any]:
        body = {"spec": {"replicas": int(replicas)}}
        result = self.apps.patch_namespaced_deployment_scale(name=name, namespace=namespace, body=body)
        return {"kind": "Deployment", "name": result.metadata.name, "namespace": result.metadata.namespace, "replicas": int(replicas), "rolled_back": True}


def local_dry_run(plan: dict[str, Any], kube: KubernetesRemediationClient | None) -> dict[str, Any]:
    action = plan.get("action_type")
    namespace = plan.get("namespace")
    service = plan.get("service")
    if action == "investigate_only":
        return {"validation_status": "passed", "summary": "Text-only investigate action requires no Kubernetes mutation.", "output": {}}
    if kube is None:
        return {"validation_status": "degraded", "summary": "Kubernetes client unavailable; safety policy validation completed only.", "output": {}}
    if not kube.deployment_exists(namespace, service):
        return {"validation_status": "failed", "summary": f"deployment/{service} not found in {namespace}", "output": {}}
    if action == "scale_deployment_noop":
        return {"validation_status": "passed", "summary": "Server-side dry-run no-op scale validated.", "output": kube.dry_run_scale_noop(namespace, service)}
    if action in {"restart_deployment", "rollback_deployment"}:
        return {"validation_status": "passed", "summary": "Server-side dry-run deployment patch validated.", "output": kube.dry_run_deployment_annotation(namespace, service, plan["plan_id"])}
    return {"validation_status": "passed", "summary": "No Kubernetes dry-run template is required for this action.", "output": {}}


def _event_mentions(event: Any, deployment_name: str, pod_names: set[str]) -> bool:
    involved = event.involved_object
    if involved and involved.name in ({deployment_name} | pod_names):
        return True
    message = str(event.message or "")
    return deployment_name in message or any(name in message for name in pod_names)

