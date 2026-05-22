from __future__ import annotations

import unittest

from services.shared.audit import REDACTED, build_audit_event, emit_audit_event, redact
from services.shared.storage.clickhouse_client import ClickHouseClient


class FakeAuditClient:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def insert_audit_event(self, row: dict) -> int:
        self.rows.append(row)
        return 1


class CapturingClickHouseClient(ClickHouseClient):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    async def fetch_json_rows(self, query: str) -> list[dict]:
        self.queries.append(query)
        return [{"event_id": "audit_1", "correlation_id": "corr-1"}]


class AuditCoreTests(unittest.IsolatedAsyncioTestCase):
    def test_redacts_sensitive_nested_payloads(self) -> None:
        payload = {
            "token": "abc123",
            "nested": {"api_key": "secret", "url": "https://example.test?token=abc123"},
            "items": [{"password": "pw"}],
        }

        redacted = redact(payload)

        self.assertEqual(redacted["token"], REDACTED)
        self.assertEqual(redacted["nested"]["api_key"], REDACTED)
        self.assertIn(f"token={REDACTED}", redacted["nested"]["url"])
        self.assertEqual(redacted["items"][0]["password"], REDACTED)

    async def test_event_creation_and_writer_store_safe_payload(self) -> None:
        client = FakeAuditClient()
        event = build_audit_event(
            "remediation.execution.completed",
            "remediation",
            payload={"service": "catalogue", "authorization": "Bearer secret-token"},
            run_id="rem_exec_1",
            service="catalogue",
            namespace="cascade-targets",
            status="completed",
            remediation_execution_id="rem_exec_1",
            evidence_summary="Execution completed",
        )

        await emit_audit_event(client, event)

        self.assertEqual(len(client.rows), 1)
        row = client.rows[0]
        self.assertEqual(row["event_type"], "remediation.execution.completed")
        self.assertEqual(row["correlation_id"], "rem_exec_1")
        self.assertEqual(row["remediation_execution_id"], "rem_exec_1")
        self.assertNotIn("secret-token", row["raw_payload_json"])
        self.assertIn(REDACTED, row["raw_payload_json"])

    async def test_storage_filtering_and_correlation_timeline_queries(self) -> None:
        client = CapturingClickHouseClient()

        rows = await client.recent_audit_events(25, subsystem="policy", severity="warning", service="catalogue", namespace="cascade-targets", status="blocked", start_time="2026-05-21 00:00:00", end_time="2026-05-21 23:59:59")
        timeline = await client.audit_timeline("corr-1")

        self.assertEqual(rows[0]["event_id"], "audit_1")
        self.assertEqual(timeline[0]["correlation_id"], "corr-1")
        filter_query = client.queries[0]
        self.assertIn("subsystem = 'policy'", filter_query)
        self.assertIn("severity = 'warning'", filter_query)
        self.assertIn("service = 'catalogue'", filter_query)
        self.assertIn("namespace = 'cascade-targets'", filter_query)
        self.assertIn("status = 'blocked'", filter_query)
        self.assertIn("parseDateTime64BestEffort", filter_query)
        self.assertIn("ORDER BY timestamp ASC", client.queries[1])


if __name__ == "__main__":
    unittest.main()
