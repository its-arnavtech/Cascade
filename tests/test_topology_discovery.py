from __future__ import annotations

import unittest

from services.shared.targets.catalog import SOCK_SHOP
from services.shared.topology.discovery import build_discovered_topology, service_dependency_graph


class TopologyDiscoveryTests(unittest.TestCase):
    def test_merges_static_catalog_with_kubernetes_selectors_and_owner_refs(self) -> None:
        payload = build_discovered_topology(
            SOCK_SHOP,
            services=[
                {
                    "metadata": {"name": "catalogue", "namespace": "cascade-targets", "labels": {"app": "catalogue"}},
                    "spec": {"selector": {"app": "catalogue"}},
                }
            ],
            deployments=[
                {
                    "metadata": {"name": "catalogue", "namespace": "cascade-targets", "labels": {"app": "catalogue"}},
                    "spec": {
                        "selector": {"matchLabels": {"app": "catalogue"}},
                        "template": {"spec": {"containers": [{"name": "app", "env": [{"name": "DB_HOST", "value": "catalogue-db"}]}]}},
                    },
                    "status": {"replicas": 1, "readyReplicas": 1},
                }
            ],
            replica_sets=[
                {
                    "metadata": {
                        "name": "catalogue-76f8d7",
                        "namespace": "cascade-targets",
                        "ownerReferences": [{"kind": "Deployment", "name": "catalogue"}],
                    }
                }
            ],
            pods=[
                {
                    "metadata": {
                        "name": "catalogue-76f8d7-x",
                        "namespace": "cascade-targets",
                        "labels": {"app": "catalogue"},
                        "ownerReferences": [{"kind": "ReplicaSet", "name": "catalogue-76f8d7"}],
                    },
                    "status": {"phase": "Running", "containerStatuses": [{"ready": True, "restartCount": 0}]},
                }
            ],
        )

        self.assertEqual(payload["discovery_status"], "discovered")
        self.assertEqual(payload["source"], "live_discovery")
        edges = {(edge["source"], edge["target"], edge["relation"], edge["source_type"]) for edge in payload["edges"]}
        self.assertIn(("front-end", "catalogue", "depends_on", "static_catalog"), edges)
        self.assertIn(("catalogue", "catalogue-76f8d7-x", "selects_pod", "kubernetes_selector"), edges)
        self.assertIn(("catalogue", "catalogue-76f8d7-x", "owns_pod", "kubernetes_owner_reference"), edges)
        self.assertIn(("catalogue", "catalogue-db", "depends_on", "static_catalog"), edges)
        catalogue = next(node for node in payload["nodes"] if node["id"] == "catalogue")
        self.assertEqual(catalogue["source_type"], "kubernetes_selector")
        self.assertGreaterEqual(catalogue["confidence"], 0.9)

    def test_static_fallback_is_labeled_and_keeps_dependency_graph(self) -> None:
        payload = build_discovered_topology(SOCK_SHOP, discovery_status="static_fallback", warnings=["no token"])

        self.assertEqual(payload["source"], "static_catalog")
        self.assertEqual(payload["discovery_status"], "static_fallback")
        self.assertIn("static_catalog", payload["source_summary"]["edges"])
        self.assertIn("front-end", payload["dependencies"])
        self.assertIn("orders", payload["dependencies"]["front-end"])
        self.assertTrue(payload["limitations"])

    def test_service_dependency_graph_ignores_pod_relationship_edges(self) -> None:
        payload = {
            "nodes": [
                {"id": "api", "kind": "service"},
                {"id": "db", "kind": "service"},
                {"id": "api-pod", "kind": "pod"},
            ],
            "edges": [
                {"source": "api", "target": "db", "relation": "depends_on", "source_type": "static_catalog"},
                {"source": "api", "target": "api-pod", "relation": "selects_pod", "source_type": "kubernetes_selector"},
            ],
        }

        self.assertEqual(service_dependency_graph(payload), {"api": ["db"], "db": []})

    def test_traffic_events_create_request_direction_edges(self) -> None:
        payload = build_discovered_topology(
            SOCK_SHOP,
            telemetry_events=[
                {
                    "event_id": "edge-1",
                    "source_service": "front-end",
                    "target_service": "orders",
                    "namespace": "cascade-targets",
                    "request_count": 25,
                    "error_count": 2,
                    "latency_p95_ms": 240.0,
                    "observed_at": "2026-05-21T12:00:00Z",
                },
                {
                    "event_id": "edge-2",
                    "source_service": "front-end",
                    "target_service": "orders",
                    "namespace": "cascade-targets",
                    "request_count": 10,
                    "latency_p95_ms": 260.0,
                    "observed_at": "2026-05-21T12:01:00Z",
                },
            ],
        )

        edge = next(item for item in payload["edges"] if item["source"] == "front-end" and item["target"] == "orders" and item["source_type"] == "traffic_inferred")
        self.assertEqual(edge["relation"], "depends_on")
        self.assertGreater(edge["confidence"], 0.6)
        self.assertEqual(edge["metadata"]["request_count"], 35.0)
        self.assertEqual(edge["metadata"]["error_count"], 2.0)
        self.assertTrue(payload["traffic_summary"]["has_request_direction_evidence"])


if __name__ == "__main__":
    unittest.main()
