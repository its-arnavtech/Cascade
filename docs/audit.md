# Cascade Audit Trail

Cascade records a unified audit event for important system actions across RCA, policy, remediation, verification, rollback, Autopilot, chaos, topology, and campaigns.

Audit events are stored in ClickHouse in `cascade.audit_events`. Payloads are redacted before storage so tokens, kubeconfigs, passwords, API keys, connection strings, authorization headers, and sensitive environment-style values are safe for demos and screenshots.

## Event Shape

Each event includes:

- `event_id`, `timestamp`, `event_type`, `subsystem`, `severity`
- `run_id`, `correlation_id`, `service`, `namespace`, `actor`
- `action`, `decision`, `status`, `risk_level`
- IDs for related policy decisions, remediation executions, verification results, rollback plans, Autopilot runs, chaos experiments or campaigns, RCA reports, and topology nodes/edges
- `evidence_summary`, `raw_payload_json`, `user_safe_message`

## APIs

```http
GET /audit/events?subsystem=policy&severity=warning&service=catalogue
GET /audit/events/{event_id}
GET /audit/timeline?correlation_id=rem_exec_123
GET /audit/service/{namespace}/{service}
GET /audit/autopilot/{run_id}
```

From Command Center, these are proxied under `/api/retrieval/...`, and the Audit page shows filters, a chronological timeline, correlation view, expandable evidence, and raw redacted payloads.

## Example

```json
{
  "event_type": "remediation.execution.completed",
  "subsystem": "remediation",
  "severity": "info",
  "correlation_id": "rem_exec_4f2a",
  "service": "catalogue",
  "namespace": "cascade-targets",
  "actor": "cascade-system",
  "action": "restart_deployment",
  "status": "completed",
  "remediation_execution_id": "rem_exec_4f2a",
  "evidence_summary": "Execution completed",
  "user_safe_message": "Execution completed"
}
```

## Emission Points

Current emission points include RCA report creation, policy evaluation, remediation plan and execution lifecycle, verification completion, rollback plan status changes, Autopilot run and step updates, chaos plan/run lifecycle, campaign lifecycle and steps, approvals, and topology refresh.
