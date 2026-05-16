# Redpanda Retention And Recovery

Cascade uses Redpanda as the local Kafka-compatible event backbone in kind. ClickHouse is the durable analytical source for accepted historical state; Redpanda topics are the transient event stream used to connect services.

## Required Topics

- `telemetry.raw`
- `telemetry.enriched`
- `experiments.events`
- `anomalies.detected`
- `agent.investigations`
- `chaos.experiments`
- `remediation.actions`

## Verify Topics

```powershell
kubectl -n cascade-system exec deployment/redpanda -- rpk -X brokers=localhost:9092 topic list
```

Or use the idempotent helper:

```powershell
.\scripts\ensure-redpanda-topics.ps1
```

## Recreate Topics

```powershell
kubectl -n cascade-system delete job redpanda-topics-init --ignore-not-found=true
kubectl apply -f infra/kubernetes/redpanda/topics-job.yaml
kubectl -n cascade-system wait --for=condition=complete job/redpanda-topics-init --timeout=180s
```

The helper script uses exact topic names and can also be rerun:

```powershell
.\scripts\ensure-redpanda-topics.ps1
```

## Inspect Recent Events

```powershell
kubectl -n cascade-system exec deployment/redpanda -- rpk -X brokers=localhost:9092 topic consume telemetry.enriched --num 3
kubectl -n cascade-system exec deployment/redpanda -- rpk -X brokers=localhost:9092 topic consume anomalies.detected --offset start --num 3
```

## Retention Assumptions

This repo does not tune Redpanda for production retention. In local kind, topic data should be treated as disposable and reproducible by rerunning deploy/demo flows. Persisted operational history lives in ClickHouse tables, and semantic memory lives in Qdrant collections.

For production-style deployment, define retention by topic, monitor broker disk usage, back up ClickHouse and Qdrant, and document which consumers can replay from earliest offsets.
