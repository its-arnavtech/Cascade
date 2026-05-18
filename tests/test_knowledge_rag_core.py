from __future__ import annotations

import unittest

from pydantic import ValidationError

from services.shared.embedding.deterministic import embed_text
from services.shared.knowledge.chunking import chunk_document
from services.shared.knowledge.context import assemble_context_pack
from services.shared.knowledge.documents import build_document, document_hash
from services.shared.knowledge.metadata import infer_metadata
from services.shared.knowledge.search import KnowledgeSearchRequest


class Phase5CoreTests(unittest.TestCase):
    def test_markdown_chunking_is_deterministic(self) -> None:
        doc = build_document("# Pod Restart\n\n" + ("restart anomaly " * 120), "docs/knowledge/runbook-pod-kill.md")
        first = chunk_document(doc, chunk_size=300, overlap=50)
        second = chunk_document(doc, chunk_size=300, overlap=50)
        self.assertEqual(first, second)
        self.assertGreater(len(first), 1)

    def test_chunk_overlap_works(self) -> None:
        doc = build_document("abcdefghijklmnopqrstuvwxyz" * 30, "docs/knowledge/latency.md")
        chunks = chunk_document(doc, chunk_size=220, overlap=40)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_text"][-40:], chunks[1]["chunk_text"][:40])

    def test_empty_documents_produce_no_chunks(self) -> None:
        doc = build_document("", "docs/knowledge/empty.md")
        self.assertEqual(chunk_document(doc), [])

    def test_document_hash_and_chunk_ids_are_stable(self) -> None:
        content = "# Service Latency\n\norders latency"
        self.assertEqual(document_hash(content), document_hash(content))
        doc = build_document(content, "docs/knowledge/runbook-service-latency.md")
        self.assertEqual(chunk_document(doc)[0]["chunk_id"], chunk_document(doc)[0]["chunk_id"])

    def test_metadata_extraction_handles_paths(self) -> None:
        meta = infer_metadata("docs/knowledge/runbook-pod-kill.md", "# Phase 5\ncatalogue critical restart", {})
        self.assertEqual(meta["document_type"], "runbook")
        self.assertEqual(meta["phase"], "phase-5")
        self.assertEqual(meta["service"], "catalogue")
        self.assertEqual(meta["severity"], "critical")

    def test_context_pack_includes_sources(self) -> None:
        pack = assemble_context_pack("pod restart", [{"chunk_id": "c1", "document_id": "d1", "title": "Runbook", "source_type": "repo_docs", "document_type": "runbook", "source_path": "docs/knowledge/runbook-pod-kill.md", "score": 0.9, "chunk_text": "Check restart_rate.", "metadata": {}}])
        self.assertEqual(len(pack["sources"]), 1)
        self.assertEqual(len(pack["evidence_chunks"]), 1)
        self.assertIn("No LLM", pack["limitations"][0])

    def test_context_pack_no_results_does_not_hallucinate(self) -> None:
        pack = assemble_context_pack("unknown failure", [])
        self.assertEqual(pack["sources"], [])
        self.assertIn("No relevant knowledge found", pack["suggested_context_summary"])

    def test_search_request_models_validate(self) -> None:
        req = KnowledgeSearchRequest(query="pod restart", limit=5, filters={"service": "carts", "tags": ["runbook"]})
        self.assertEqual(req.filters.service, "carts")
        with self.assertRaises(ValidationError):
            KnowledgeSearchRequest(query="", limit=5)

    def test_ingestion_run_records_are_buildable(self) -> None:
        doc = build_document("# Incident\n\nroot cause carts", "clickhouse/incidents/i1.json", "incident_history", metadata={"severity": "high"})
        chunk = chunk_document(doc)[0]
        self.assertEqual(doc.source_type, "incident_history")
        self.assertEqual(chunk["severity"], "high")

    def test_deterministic_embeddings_vector_size(self) -> None:
        vector = embed_text("pod restart unhealthy service anomaly", 128)
        self.assertEqual(len(vector), 128)
        self.assertEqual(vector, embed_text("pod restart unhealthy service anomaly", 128))


if __name__ == "__main__":
    unittest.main()
