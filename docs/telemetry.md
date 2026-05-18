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
- `topology-service`: static Online Boutique dependency graph and impact paths.
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
- Telemetry can flow continuously through Kafka-compatible topics.
- Experiments can be tracked as events.
- Deterministic causal reconstruction can produce first-pass incident candidates.
- Static topology can estimate impact paths.
- Timeline/report generation can turn structured evidence into a readable incident report.

## Intentionally Deferred To Storage and memory

- LangGraph
- Qdrant
- ClickHouse
- ML-based anomaly detection
- agent runtime
- frontend UX
