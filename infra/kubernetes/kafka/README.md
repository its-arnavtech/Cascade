# Apache Kafka for Cascade Phase 2.2

This directory deploys a single Apache Kafka broker in KRaft mode for local kind development.

## Why This Configuration

- `KAFKA_LISTENERS` binds to `0.0.0.0` so Kafka listens on the pod network interfaces.
- `KAFKA_ADVERTISED_LISTENERS` uses `kafka.cascade-system.svc.cluster.local:9092` so in-cluster clients receive a reachable service DNS name.
- `KAFKA_ADVERTISED_LISTENERS` must never use `0.0.0.0`; clients cannot connect to that address.
- `KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093` because this is a single-node KRaft broker/controller process. The controller quorum must point at the local controller listener, not the Kubernetes service.

## Clean Retry From Phase 2.1

From the repo root:

```powershell
.\scripts\reset-phase-2-2-kafka.ps1

docker build -f services/observation-service/Dockerfile -t cascade-observation-service:dev .
docker build -f services/stream-enricher/Dockerfile -t cascade-stream-enricher:dev .

kind load docker-image cascade-observation-service:dev --name cascade
kind load docker-image cascade-stream-enricher:dev --name cascade

kubectl apply -f infra/kubernetes/kafka/namespace.yaml
kubectl apply -f infra/kubernetes/kafka/deployment.yaml
kubectl apply -f infra/kubernetes/kafka/service.yaml
kubectl rollout status deployment/kafka -n cascade-system

kubectl apply -f infra/kubernetes/kafka/topics-job.yaml

kubectl apply -f infra/kubernetes/observation-service/
kubectl apply -f infra/kubernetes/stream-enricher/

.\scripts\accept-phase-2-2.ps1
```

If the kind cluster was recreated, rebuilding and `kind load`-ing both service images is required before applying the service deployments.

## Verify Kafka

```powershell
kubectl get pods -n cascade-system -l app=kafka
kubectl logs deployment/kafka -n cascade-system --tail=100
kubectl get endpoints kafka -n cascade-system
kubectl exec -n cascade-system deployment/kafka -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Expected topics:

- `telemetry.raw`
- `telemetry.enriched`
- `experiments.events`
