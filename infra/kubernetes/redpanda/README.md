# Redpanda Kafka-Compatible Backbone

Cascade Phase 2.2 uses Redpanda as the local kind broker for the Kafka-compatible event backbone. The application code still uses `aiokafka`, the same topic names, and the same `KAFKA_BOOTSTRAP_SERVERS` environment variable.

Redpanda is Kafka API-compatible, so `observation-service` publishes `telemetry.raw` and `stream-enricher` consumes and republishes `telemetry.enriched` without code changes.

We switched away from a hand-rolled Apache Kafka deployment only for local development reliability in kind. The architecture remains a Kafka-compatible event streaming backbone.

## Deploy

From the repo root:

```powershell
.\scripts\reset-phase-2-2-redpanda.ps1

docker build -f services/observation-service/Dockerfile -t cascade-observation-service:dev .
docker build -f services/stream-enricher/Dockerfile -t cascade-stream-enricher:dev .

kind load docker-image cascade-observation-service:dev --name cascade
kind load docker-image cascade-stream-enricher:dev --name cascade

kubectl apply -f infra/kubernetes/redpanda/deployment.yaml
kubectl apply -f infra/kubernetes/redpanda/service.yaml
kubectl rollout status deployment/redpanda -n cascade-system

kubectl apply -f infra/kubernetes/redpanda/topics-job.yaml

kubectl apply -f infra/kubernetes/observation-service/
kubectl apply -f infra/kubernetes/stream-enricher/

.\scripts\accept-phase-2-2.ps1
```

If the kind cluster was recreated, rebuild and `kind load` both service images before applying the service deployments.

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
