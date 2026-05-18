# Stream Enricher

The stream enricher consumes `telemetry.raw`, applies simple rule-based enrichment, and publishes `telemetry.enriched`.

## Enrichment Rules

- `cpu_percent > 80` adds `high_cpu`
- `memory > HIGH_MEMORY_THRESHOLD_BYTES` adds `high_memory`
- `restart_count > 0` adds `unstable`
- `pod_phase != Running` adds `degraded`

`derived_status` is:

- `healthy` when there are no anomaly flags
- `warning` when anomalies exist but the pod is still running
- `degraded` when the pod phase is not `Running`

## Configuration

| Environment variable | Default |
| --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` |
| `KAFKA_RAW_TOPIC` | `telemetry.raw` |
| `KAFKA_ENRICHED_TOPIC` | `telemetry.enriched` |
| `KAFKA_CONSUMER_GROUP` | `stream-enricher` |
| `HIGH_MEMORY_THRESHOLD_BYTES` | `536870912` |

## Run Locally

For current kind-based development, use Redpanda through `.\scripts\deploy-telemetry.ps1`. The old Docker Compose Apache Kafka setup remains available only as a legacy local compatibility path:

```powershell
docker compose -f the legacy Kafka archive up -d
```

Run the service:

```powershell
cd services/stream-enricher
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

## Build Docker Image

From the repo root:

```powershell
docker build -f services/stream-enricher/Dockerfile -t cascade-stream-enricher:dev .
```
