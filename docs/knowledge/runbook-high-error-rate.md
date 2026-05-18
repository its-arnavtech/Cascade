# High Error Rate Runbook

Use this runbook when a service shows elevated error rate, warning rate, or unhealthy status.

## Expected Signals

- `telemetry_events` contains service-level health status and severity.
- `telemetry_feature_windows.error_rate` and `unhealthy_rate` rise above baseline.
- `anomaly_events` explains which detector flagged the window and includes feature evidence.
- `incident_reports` may describe the root cause service and affected services.

## Investigation Steps

1. Search anomalies for the service with severity `high` or `critical`.
2. Inspect recent telemetry events around the same `window_start` and `window_end`.
3. Check whether an experiment was active in `experiment_events`.
4. Use topology context to distinguish root cause symptoms from downstream impact.
5. Retrieve similar incident reports before writing an operator summary.

## Notes

Knowledge and RAG retrieval returns evidence and citations only. It does not claim final root cause without retrieved support.
