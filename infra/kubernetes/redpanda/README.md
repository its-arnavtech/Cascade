# Redpanda Kafka-Compatible Backbone

Cascade uses Redpanda as the local kind broker for the Kafka-compatible event backbone. The application code still uses `aiokafka`, the same topic names, and the same `KAFKA_BOOTSTRAP_SERVERS` environment variable.

Redpanda is Kafka API-compatible, so `observation-service` publishes `telemetry.raw` and `stream-enricher` consumes and republishes `telemetry.enriched` without code changes.

We switched away from a hand-rolled Apache Kafka deployment only for local development reliability in kind. The architecture remains a Kafka-compatible event streaming backbone.

## Deploy

From the repo root:

```powershell
.\scripts\deploy-telemetry.ps1
.\scripts\accept-telemetry.ps1
```

If the kind cluster was recreated, `deploy-telemetry.ps1` rebuilds and `kind load`s the Telemetry pipeline service images before applying the deployments.

## Verify

```powershell
kubectl get pods -n cascade-system -l app=redpanda
kubectl logs deployment/redpanda -n cascade-system --tail=100
kubectl get endpoints redpanda -n cascade-system
kubectl exec -n cascade-system deployment/redpanda -- rpk -X brokers=localhost:9092 topic list
```

Expected topics:

- `telemetry.raw`
- `telemetry.enriched`
- `experiments.events`
