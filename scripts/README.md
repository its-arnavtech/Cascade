# Cascade Scripts

## Full Phase 2 Deploy, Acceptance, And Demo

Deploy every Phase 2 component into the local `cascade` kind cluster:

```powershell
.\scripts\deploy-phase-2.ps1
```

Run the final Phase 2 acceptance gate:

```powershell
.\scripts\accept-phase-2.ps1
```

Run the final demo flow and print a Markdown incident report:

```powershell
.\scripts\demo-phase-2.ps1
```

`PHASE 2 ACCEPTANCE: PASS` means Phase 2.1 still works, Redpanda is running as the Kafka-compatible broker, `telemetry.raw`, `telemetry.enriched`, and `experiments.events` all flow, and the experiment tracker, topology, causal reconstruction, and incident timeline services can generate a deterministic incident report.

If the full gate fails, start with the first failed check. Redpanda/topic failures usually belong in `infra/kubernetes/redpanda/`; telemetry failures usually belong in observation-service or stream-enricher; incident/report failures usually belong in the Phase 2.3-2.6 services.

## Reset To Stable Phase 2.1

Reset the active kind cluster to the stable Phase 2.1 observation-service baseline:

```powershell
.\scripts\reset-to-phase-2-1.ps1
```

If the `cascade` kind cluster is missing and you want the script to create it:

```powershell
.\scripts\reset-to-phase-2-1.ps1 -CreateKindIfMissing
```

The reset script removes active Phase 2.2 Kubernetes resources for Kafka and stream-enricher, but it does not delete source code. It rebuilds `cascade-observation-service:dev`, loads it into kind, redeploys only observation-service, and waits for rollout.

## Phase 2.1 Acceptance

Verify the restored baseline:

```powershell
.\scripts\accept-phase-2-1.ps1
```

`PHASE 2.1 ACCEPTANCE: PASS` means observation-service is running in Kubernetes and these endpoints work:

- `GET /health`
- `GET /metrics/raw?query=up`
- `GET /snapshot`

Before retrying Phase 2.2, make sure Phase 2.1 acceptance passes and read:

```powershell
docs\phase-2-reset.md
```

## Phase 2.2 Redpanda Clean Retry

Use this sequence to retry the Kafka-compatible event backbone from a stable Phase 2.1 cluster. Redpanda is Kafka API-compatible, so the services still use `KAFKA_BOOTSTRAP_SERVERS`.

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

If the kind cluster was recreated, rebuild and `kind load` both service images before applying the deployments.

`PHASE 2.2 ACCEPTANCE: PASS` means Redpanda is running as the Kafka-compatible broker, topics exist, observation-service publishes `telemetry.raw`, stream-enricher publishes `telemetry.enriched`, and enriched events have the expected JSON shape.

## Phase 2.2 Kubernetes Debugger

Run the full Redpanda, observation-service, and stream-enricher diagnostic report:

```powershell
.\scripts\debug-phase-2-2.ps1
```

The script is read-only by default. It prints namespace state, pods, deployments, services, Redpanda pod details, Redpanda logs, service endpoints, in-cluster DNS checks, topic checks, client logs, environment variables, optional resource usage, and diagnosis hints.

Useful options:

```powershell
.\scripts\debug-phase-2-2.ps1 -FixImagePullPolicy
.\scripts\debug-phase-2-2.ps1 -Restart
.\scripts\debug-phase-2-2.ps1 -Watch
```

- `-FixImagePullPolicy` patches `observation-service` and `stream-enricher` to `imagePullPolicy: Never` for local kind images.
- `-Restart` restarts `redpanda`, `observation-service`, and `stream-enricher`.
- `-Watch` watches pods after the report.

## Common Diagnoses

- Redpanda pod not Ready: check Redpanda logs and `kubectl describe pod`; resource pressure or image pull state is likely.
- Service has no endpoints: Redpanda pod is not Ready or `service/redpanda` selectors do not match pod labels.
- Topic commands fail: verify `rpk -X brokers=localhost:9092 topic list` from the Redpanda pod.
- Exit code `137` or `OOMKilled`: Redpanda likely needs more memory or a lighter configuration.
- App clients show `KafkaConnectionError`: Redpanda is not reachable, not ready, or `KAFKA_BOOTSTRAP_SERVERS` is wrong.
- Container name mismatch: use pod JSON/container discovery instead of assuming a pod name.

## Next Commands After Failure

```powershell
kubectl -n cascade-system describe pod -l app=redpanda
kubectl -n cascade-system logs deployment/redpanda --tail=200
kubectl -n cascade-system get endpoints redpanda
kubectl -n cascade-system describe svc redpanda
kubectl -n cascade-system rollout restart deployment/redpanda
```

After fixing manifests:

```powershell
kubectl apply -f infra/kubernetes/redpanda/
kubectl apply -f infra/kubernetes/observation-service/
kubectl apply -f infra/kubernetes/stream-enricher/
```

## Phase 2.2 Acceptance Test

Run the final end-to-end acceptance gate before moving to Phase 2.3:

```powershell
.\scripts\accept-phase-2-2.ps1
```

Optional chaos smoke test:

```powershell
.\scripts\accept-phase-2-2.ps1 -ChaosSmoke
```

The acceptance test verifies:

- `cascade-system` exists.
- `redpanda`, `observation-service`, and `stream-enricher` deployments are available.
- Required pods are Running and Redpanda is `1/1`.
- `service/redpanda` has endpoints.
- Kafka-compatible topics exist: `telemetry.raw`, `telemetry.enriched`, `experiments.events`.
- observation-service `/health` is ok and `/snapshot` includes `cascade-targets` pods.
- stream-enricher `/health` and `/stats` are reachable when exposed.
- `telemetry.raw` and `telemetry.enriched` both receive messages.
- One enriched message has the required Phase 2.2 shape.
- Recent logs do not show obvious connection or crash symptoms.

`PHASE 2.2 ACCEPTANCE: PASS` means the Kafka-compatible event backbone is working end to end: Prometheus telemetry is being published to Redpanda, stream-enricher is consuming and republishing, and the enriched event contract is present.

Common failures usually mean:

- Redpanda not `1/1 Running`: inspect Redpanda logs, resources, and probes.
- `service/redpanda` has no endpoints: Redpanda pod is not Ready or service selectors are wrong.
- Missing topics: rerun the Redpanda topics job or inspect Redpanda startup.
- observation-service health/snapshot failure: Prometheus or target namespace telemetry is not available.
- `telemetry.raw` has no messages: observation-service publisher loop cannot publish.
- `telemetry.enriched` has no messages: stream-enricher cannot consume or produce.
- Enriched shape failure: stream-enricher model/schema generation is wrong.
