# Anomaly detection - ML Anomaly Detection

Anomaly detection adds local, explainable anomaly detection on top of the completed storage and memory layer.

## Architecture

```text
ClickHouse telemetry_events
-> feature-extractor-service
-> ClickHouse telemetry_feature_windows
-> anomaly-detector-service
-> ClickHouse anomaly_events + model_runs
-> Redpanda anomalies.detected
-> retrieval-service anomaly APIs
```

## Data Flow

1. Storage and memory archives `telemetry.enriched` into `telemetry_events`.
2. `feature-extractor-service` groups recent telemetry by service, namespace, workload, and time window.
3. Feature windows are stored in `telemetry_feature_windows`.
4. `anomaly-detector-service` runs threshold, rolling z-score, and optional Isolation Forest detectors.
5. Detected anomalies are stored in `anomaly_events`.
6. Published anomaly events flow to the Redpanda topic `anomalies.detected`.
7. `retrieval-service` exposes feature and anomaly query APIs.

## Feature Extraction

Default window: 5 minutes.

Default lookback: 30 minutes.

Feature vectors include:

- event counts
- healthy, warning, error, and unhealthy counts
- restart signal counts
- CPU and memory aggregates
- latency fields, currently zero when telemetry does not include latency
- error, restart, and unhealthy rates
- experiment and incident context counts

Feature window IDs are deterministic from service, namespace, workload, and window bounds.

## ClickHouse Tables

Anomaly detection adds:

- `telemetry_feature_windows`
- `anomaly_events`
- `model_runs`

The existing ClickHouse schema job creates these idempotently.

`anomaly_id` is stable for a feature window and detector evidence. Before inserting new anomaly rows, the detector checks existing IDs and skips already-persisted IDs, including duplicates inside the same detection batch. Re-running synthetic demo detection for the same labeled feature window should therefore publish only genuinely new anomaly IDs instead of inflating `anomaly_events` with repeated copies.

## Model Design

### Threshold Detector

The threshold detector works even with very little history. It flags high unhealthy, error, restart, or event-count rates. It is deterministic and emits explanations like `unhealthy_rate 0.900 >= 0.500`.

### Rolling Z-Score

The z-score detector compares a service's current feature window to recent historical windows for the same service. It handles zero standard deviation and low history safely.

### Isolation Forest

Isolation Forest uses `scikit-learn` when available. It requires enough feature-window history before scoring. Its `decision_function` output is not treated as a probability; Cascade maps it into a local risk score for operational ranking only.

## Risk And Severity

Cascade combines detector outputs into `risk_score` from `0.0` to `1.0`.

- `>= 0.85`: critical
- `>= 0.65`: high
- `>= 0.40`: medium
- `>= 0.20`: low
- otherwise normal

## Redpanda Topic

Topic: `anomalies.detected`

Events follow `schemas/anomaly-event.schema.json` and include model evidence, explanation, feature vector, severity, and risk score.

## Retrieval APIs

New retrieval-service endpoints:

- `GET /features/recent`
- `GET /anomalies/recent`
- `GET /anomalies/service/{service_name}`
- `GET /anomalies/{anomaly_id}`
- `GET /debug/counts` includes Anomaly detection counts

## Deployment

```powershell
.\scripts\deploy-anomaly-detection.ps1
.\scripts\accept-anomaly-detection.ps1
.\scripts\demo-anomaly-detection.ps1 -Synthetic
```

## Acceptance

`accept-anomaly-detection.ps1` verifies:

- Storage and memory baseline tables and topics
- Anomaly detection tables
- `anomalies.detected` topic
- feature extraction from real telemetry
- a clearly labeled synthetic feature window for reliable local anomaly proof
- anomaly persistence
- anomaly event publication
- retrieval-service feature and anomaly APIs
- repeated runs do not insert duplicate rows for already-seen stable anomaly IDs

## Troubleshooting

```powershell
.\scripts\debug-anomaly-detection.ps1
```

This collects service state, logs, Redpanda topics, ClickHouse counts, recent feature rows, recent anomaly rows, model runs, and health/readiness outputs.

## Known Limitations

- Baseline models only.
- Local deterministic/statistical ML, not deep learning.
- Isolation Forest needs enough historical feature windows.
- Synthetic demo anomalies may be used for reliable local demonstration and are labeled as such.
- No RAG yet.
- No LangGraph agents yet.
- No remediation execution yet.
- No UI yet.
