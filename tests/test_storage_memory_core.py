from __future__ import annotations

import unittest

from services.shared.embedding.deterministic import embed_text
from services.shared.events.mapping import (
    build_memory_document,
    build_memory_payload,
    map_experiment_event,
    map_telemetry_event,
)


class Phase3CoreTests(unittest.TestCase):
    def test_embedding_is_deterministic(self) -> None:
        text = "unhealthy pod restart latency service failure"
        self.assertEqual(embed_text(text, 128), embed_text(text, 128))

    def test_embedding_dimension(self) -> None:
        self.assertEqual(len(embed_text("carts degraded", 128)), 128)

    def test_embedding_handles_empty_input(self) -> None:
        self.assertEqual(embed_text("", 4), [0.0, 0.0, 0.0, 0.0])

    def test_telemetry_mapping_handles_missing_fields_and_preserves_json(self) -> None:
        row = map_telemetry_event({"service_name": "carts", "derived_status": "degraded"})
        self.assertEqual(row["service"], "carts")
        self.assertEqual(row["health_status"], "degraded")
        self.assertIn('"service_name":"carts"', row["raw_json"])

    def test_experiment_mapping_preserves_original_json(self) -> None:
        row = map_experiment_event({"experiment_id": "exp-1", "target_service": "orders", "status": "started"})
        self.assertEqual(row["experiment_id"], "exp-1")
        self.assertEqual(row["target_service"], "orders")
        self.assertIn('"status":"started"', row["event_json"])

    def test_memory_document_is_stable(self) -> None:
        payload = {"service_name": "carts", "derived_status": "degraded", "anomaly_flags": ["unstable"]}
        self.assertEqual(build_memory_document("telemetry_event", payload), build_memory_document("telemetry_event", payload))

    def test_memory_payload_contains_required_metadata(self) -> None:
        payload = build_memory_payload("telemetry_event", {"event_id": "evt-1", "service_name": "carts"}, "test")
        for key in ("memory_id", "memory_type", "event_id", "service", "namespace", "summary", "compact_json"):
            self.assertIn(key, payload)
        self.assertEqual(payload["memory_type"], "telemetry_event")
        self.assertEqual(payload["event_id"], "evt-1")

    def test_qdrant_init_uses_local_demo_indexing_threshold(self) -> None:
        manifest = open("infra/kubernetes/qdrant/collection-job.yaml", encoding="utf-8").read()
        self.assertIn('"optimizers_config":{"indexing_threshold":1000}', manifest)
        self.assertIn("PATCH http://qdrant:6333/collections/cascade_incident_memory", manifest)
        self.assertIn("PATCH http://qdrant:6333/collections/cascade_knowledge_base", manifest)


if __name__ == "__main__":
    unittest.main()
