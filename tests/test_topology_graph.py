from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from services.shared.topology.graph import TopologyGraph


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_SERVICE = ROOT / "services" / "topology-service"
if str(TOPOLOGY_SERVICE) not in sys.path:
    sys.path.insert(0, str(TOPOLOGY_SERVICE))

from app.main import app  # noqa: E402


SOCK_SHOP = {
    "front-end": ["catalogue", "carts", "orders", "payment", "user"],
    "catalogue": ["catalogue-db"],
    "catalogue-db": [],
    "carts": ["carts-db"],
    "carts-db": [],
    "orders": ["orders-db", "payment", "shipping", "user"],
    "orders-db": [],
    "payment": [],
    "shipping": ["rabbitmq"],
    "queue-master": ["rabbitmq"],
    "rabbitmq": [],
    "user": ["user-db"],
    "user-db": [],
}


class TopologyGraphTests(unittest.TestCase):
    def test_sock_shop_downstream_upstream_and_hops(self) -> None:
        graph = TopologyGraph.from_dependencies(SOCK_SHOP, source="test")

        self.assertEqual(graph.downstream("front-end"), ["catalogue", "carts", "orders", "payment", "user"])
        self.assertEqual(graph.upstream("rabbitmq"), ["queue-master", "shipping"])
        self.assertEqual(
            graph.downstream("front-end", hops=2),
            ["catalogue", "carts", "orders", "payment", "user", "catalogue-db", "carts-db", "orders-db", "shipping", "user-db"],
        )

    def test_cycle_safe_traversal_and_critical_paths(self) -> None:
        graph = TopologyGraph.from_dependencies({"a": ["b"], "b": ["c"], "c": ["a", "d"], "d": []}, source="cycle-test")

        self.assertEqual(graph.downstream("a", hops=10), ["b", "c", "d"])
        self.assertEqual(graph.upstream("a", hops=10), ["c", "b"])
        paths = graph.critical_paths("a", depth_cap=10)
        self.assertIn(["a", "b", "c", "d"], [path.nodes for path in paths])
        self.assertNotIn(["a", "b", "c", "a"], [path.nodes for path in paths])

    def test_critical_paths_respect_depth_cap(self) -> None:
        graph = TopologyGraph.from_dependencies(SOCK_SHOP, source="test")

        paths = graph.critical_paths("front-end", depth_cap=2, limit=10)

        self.assertTrue(paths)
        self.assertTrue(all(path.depth <= 2 for path in paths))
        self.assertIn(["front-end", "orders", "shipping"], [path.nodes for path in paths])

    def test_blast_radius_scoring_increases_with_reach(self) -> None:
        graph = TopologyGraph.from_dependencies(SOCK_SHOP, source="test")

        front_end = graph.blast_radius("front-end", hops=3, depth_cap=4)
        payment = graph.blast_radius("payment", hops=3, depth_cap=4)

        self.assertGreater(front_end.score, payment.score)
        self.assertEqual(front_end.severity, "high")
        self.assertIn("downstream_ratio", front_end.formula)
        self.assertIn("orders", front_end.affected_services)

    def test_topology_service_preserves_impact_and_exposes_graph_api(self) -> None:
        client = TestClient(app)

        topology = client.get("/topology").json()
        self.assertIn("dependencies", topology)
        impact = client.post("/topology/impact", json={"root_service": "front-end"}).json()
        self.assertEqual(impact["root_service"], "front-end")
        self.assertIn("orders", impact["affected_services"])

        graph = client.get("/topology/graph").json()
        self.assertIn("nodes", graph)
        deps = client.get("/topology/orders/dependencies?hops=2&direction=downstream").json()
        self.assertIn("rabbitmq", deps["dependencies"])
        blast = client.post("/topology/blast-radius", json={"root_service": "front-end", "hops": 2}).json()
        self.assertIn("score", blast)
        critical = client.post("/topology/critical-paths", json={"root_service": "front-end", "depth_cap": 3}).json()
        self.assertTrue(critical["critical_paths"])


if __name__ == "__main__":
    unittest.main()
