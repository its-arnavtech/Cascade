from __future__ import annotations

from typing import Any

from kubernetes import client, config
from kubernetes.client import ApiException


PLURALS = {"PodChaos": "podchaos", "NetworkChaos": "networkchaos", "StressChaos": "stresschaos"}


class KubernetesChaosClient:
    def __init__(self) -> None:
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self.custom = client.CustomObjectsApi()
        self.core = client.CoreV1Api()
        self.apiext = client.ApiextensionsV1Api()

    def ready(self, namespace: str = "cascade-targets") -> bool:
        try:
            self.core.list_namespaced_pod(namespace=namespace, limit=1)
            return True
        except Exception:
            return False

    def chaos_crds_ready(self) -> bool:
        try:
            self.apiext.read_custom_resource_definition("podchaos.chaos-mesh.org")
            return True
        except Exception:
            return False

    def target_count(self, namespace: str, service: str) -> int:
        pods = self.core.list_namespaced_pod(namespace=namespace, label_selector=f"app={service}")
        return len(pods.items)

    def create(self, manifest: dict[str, Any]) -> dict[str, Any]:
        kind = manifest["kind"]
        namespace = manifest["metadata"]["namespace"]
        return self.custom.create_namespaced_custom_object("chaos-mesh.org", "v1alpha1", namespace, PLURALS[kind], manifest)

    def delete(self, kind: str, namespace: str, name: str) -> str:
        try:
            self.custom.delete_namespaced_custom_object("chaos-mesh.org", "v1alpha1", namespace, PLURALS[kind], name)
            return "cleaned_up"
        except ApiException as exc:
            if exc.status == 404:
                return "not_found"
            raise

    def get(self, kind: str, namespace: str, name: str) -> dict[str, Any] | None:
        try:
            return self.custom.get_namespaced_custom_object("chaos-mesh.org", "v1alpha1", namespace, PLURALS[kind], name)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def list_managed(self, namespace: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for plural in PLURALS.values():
            try:
                result = self.custom.list_namespaced_custom_object("chaos-mesh.org", "v1alpha1", namespace, plural, label_selector="cascade.io/phase=phase7")
                items.extend(result.get("items", []))
            except Exception:
                continue
        return items
