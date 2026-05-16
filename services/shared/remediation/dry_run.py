from __future__ import annotations

from typing import Any

from kubernetes import client, config
from kubernetes.client import ApiException


class KubernetesRemediationClient:
    def __init__(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self.apps = client.AppsV1Api()
        self.core = client.CoreV1Api()

    def ready(self, namespace: str = "cascade-targets") -> bool:
        try:
            self.core.list_namespaced_pod(namespace=namespace, limit=1)
            return True
        except Exception:
            return False

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

