# Cascade Telemetry pipeline

Telemetry pipeline proves Cascade can observe a live Kubernetes target, stream telemetry through a Kafka-compatible event backbone powered by Redpanda, track experiments, reconstruct deterministic causal chains, model service topology, and generate incident reports.

## Architecture

```text
Chaos Mesh / manual trigger
  -> experiment-tracker-service
  -> experiments.events

Prometheus
  -> observation-service
  -> telemetry.raw
  -> stream-enricher
  -> telemetry.enriched

telemetry.enriched + experiments.events
  -> topology-service
  -> causal-reconstruction-service
  -> incident-timeline-service
  -> final incident report
```

## Services

- `observation-service`: `/health`, `/snapshot`, `/metrics/raw`; publishes `telemetry.raw`.
- `stream-enricher`: consumes `telemetry.raw`, publishes `telemetry.enriched`, exposes `/health` and `/stats`.
- `experiment-tracker-service`: tracks experiment metadata and publishes `experiments.events`.
- `topology-service`: Sock Shop target catalog dependency graph and impact paths.
- `causal-reconstruction-service`: deterministic incident reconstruction from experiment and telemetry events.
- `incident-timeline-service`: JSON and Markdown incident reports.
- `redpanda`: Kafka API-compatible broker for local kind.

## Topics

- `telemetry.raw`
- `telemetry.enriched`
- `experiments.events`

## Deploy

```powershell
.\scripts\deploy-telemetry.ps1
```

## Accept

```powershell
.\scripts\accept-telemetry.ps1
```

Expected:

```text
TELEMETRY ACCEPTANCE: PASS
```

## Demo

```powershell
.\scripts\demo-telemetry.ps1
```

## What Telemetry pipeline Proves

- Prometheus telemetry can be normalized into pod/service snapshots.
- RED metrics are collected opportunistically when the target exposes compatible Prometheus series:
  - request rate from `http_requests_total`
  - error rate from HTTP `5xx` counters
  - latency p50/p95/p99 from `http_request_duration_seconds_bucket`
  - availability and readiness from Kubernetes status metrics and pod readiness
- Every Prometheus query now carries per-query status. Empty, malformed, or failed queries are reported as `missing_metrics`, `collection_warnings`, and `evidence_quality=insufficient_data` or `kubernetes_fallback`; Cascade does not invent confidence when RED series are absent.
- Kubernetes pod status remains the safe fallback for readiness, restarts, warning events, labels, and service availability hints.
- Telemetry can flow continuously through Kafka-compatible topics.
- Experiments can be tracked as events.
- Deterministic causal reconstruction can produce first-pass incident candidates.
- Static topology can estimate impact paths.
- Timeline/report generation can turn structured evidence into a readable incident report.

## RED Metric Truthfulness

`observation-service` exposes `/snapshot` with:

- `query_status`: status, result count, warning, and error per Prometheus query.
- `missing_metrics`: metrics that were empty or failed.
- `collection_warnings`: human-readable reasons for missing data.
- `used_kubernetes_fallback`: true when pod status came from the Kubernetes API because Prometheus did not return pod samples.
- `evidence_quality`: `red_metrics_available`, `partial_red_metrics`, `pod_metrics_available`, `kubernetes_fallback`, or `insufficient_data`.

If Prometheus is unavailable or the app lacks RED instrumentation, the dashboard should show fallback or insufficient-data states. That is expected and more truthful than silently treating missing request metrics as healthy.

## Intentionally Deferred To Storage and memory

- LangGraph
- Qdrant
- ClickHouse
- ML-based anomaly detection
- agent runtime
- frontend UX
