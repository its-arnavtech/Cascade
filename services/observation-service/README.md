# Observation Service

The observation service is Cascade's telemetry ingress service. It queries Prometheus, tolerates missing metrics, returns pod-level telemetry for the configured target namespace, and publishes continuous `telemetry.raw` Kafka events.

## API

### `GET /health`

```json
{
  "status": "ok",
  "service": "observation-service"
}
```

### `GET /snapshot`

Queries Prometheus for pod CPU, memory, restart count, pod phase, pod readiness, and RED service metrics in `TARGET_NAMESPACE`. RED metrics are collected when compatible `http_requests_total` and `http_request_duration_seconds_bucket` series exist.

Example response:

```json
{
  "namespace": "cascade-targets",
  "timestamp": "2026-05-12T22:15:30.123456Z",
  "pods": [
    {
      "service_name": "carts",
      "pod_name": "carts-7b8c9d45f6-abc12",
      "namespace": "cascade-targets",
      "pod_phase": "Running",
      "cpu_usage_cores": 0.0123,
      "memory_working_set_bytes": 73400320,
      "restart_count": 0,
      "request_rate": null,
      "error_rate": null,
      "latency_p95_ms": null,
      "missing_metrics": ["request_rate", "error_rate", "latency_p95_ms"],
      "metric_status": {
        "request_rate": "empty"
      },
      "evidence_quality": "insufficient_data",
      "used_kubernetes_fallback": false
    }
  ],
  "query_status": {
    "request_rate": {
      "status": "empty",
      "result_count": 0,
      "warning": "Prometheus query succeeded but returned no samples."
    }
  }
}
```

If a metric is unavailable, that field is returned as `null`, the metric name appears in `missing_metrics`, and query-level status explains whether the query was empty or failed. If Prometheus returns no pod samples, the service falls back to Kubernetes pod status and marks `used_kubernetes_fallback=true`.

### `GET /metrics/raw?query=<promql>`

Passes a single instant PromQL expression through to Prometheus and returns the raw Prometheus JSON response plus `query_status`. Failed or empty queries are reported in-band so callers can distinguish missing data from healthy data.

Example:

```powershell
curl "http://localhost:8000/metrics/raw?query=up"
```

## Configuration

| Environment variable | Default |
| --- | --- |
| `PROMETHEUS_URL` | `http://prometheus-stack-kube-prom-prometheus.monitoring.svc.cluster.local:9090` |
| `TARGET_NAMESPACE` | `cascade-targets` |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` |
| `KAFKA_RAW_TOPIC` | `telemetry.raw` |
| `TELEMETRY_PUBLISH_INTERVAL_SECONDS` | `10` |

## Run Locally

From `services/observation-service`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PROMETHEUS_URL = "http://localhost:9090"
$env:TARGET_NAMESPACE = "cascade-targets"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

For current kind-based development, use Redpanda through `.\scripts\deploy-telemetry.ps1`. When running this service outside the cluster, port-forward Redpanda before starting the process:

```powershell
kubectl -n cascade-system port-forward svc/redpanda 9092:9092
```

If Prometheus is running in Kubernetes, port-forward it first:

```powershell
kubectl -n monitoring port-forward svc/prometheus-stack-kube-prom-prometheus 9090:9090
```

## Build Docker Image

From the repo root:

```powershell
docker build -f services/observation-service/Dockerfile -t cascade-observation-service:dev .
```

For a local kind cluster:

```powershell
kind load docker-image cascade-observation-service:dev
```

## Deploy to Kubernetes

From the repo root:

```powershell
kubectl create namespace cascade-system --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f infra/kubernetes/observation-service/
```

Port-forward and test:

```powershell
.\scripts\test-observation-service.ps1
```
