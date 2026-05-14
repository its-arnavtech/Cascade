# Phase 2 Reset Safety Note

LEGACY / HISTORICAL: this note documents the earlier recovery path from the unstable hand-rolled Apache Kafka local deployment. The current supported Phase 2 path uses Redpanda and is validated by `.\scripts\accept-phase-2.ps1`.

Cascade is temporarily resetting to a stable Phase 2.1 baseline because the hand-rolled Apache Kafka Kubernetes deployment was unstable in local kind. Kafka entered repeated CrashLoopBackOff states, which caused `observation-service` and `stream-enricher` to retry against an unavailable broker instead of proving the event backbone.

This reset does not delete source code. Phase 2.2 files remain in the repository for review and reuse, but broker and stream-enricher Kubernetes resources are removed from the active cluster so Phase 2.1 can be validated cleanly.

## Stable Phase 2.1 Baseline

Phase 2.1 is stable when:

- the kind cluster is reachable through `kind-cascade`;
- `cascade-system` exists;
- `observation-service` is deployed and `1/1 Running`;
- `GET /health` returns `ok`;
- `GET /metrics/raw?query=up` returns Prometheus data;
- `GET /snapshot` returns telemetry for `cascade-targets`;
- observation-service logs do not contain Python tracebacks.

Run:

```powershell
.\scripts\reset-to-phase-2-1.ps1
.\scripts\accept-phase-2-1.ps1
```

## Before Retrying Phase 2.2

Do not reattempt Phase 2.2 until Phase 2.1 acceptance passes. The event backbone should be retried from a known-good telemetry service and healthy target system, not from a partially broken Kafka state.

Current broker strategy:

- Use Redpanda for local kind reliability while preserving Kafka API compatibility.
- Keep `KAFKA_BOOTSTRAP_SERVERS` unchanged in service configuration so the `aiokafka` producer and consumer code still works.
- Describe the platform as a Kafka-compatible event streaming backbone powered by Redpanda.
- The switch away from hand-rolled Apache Kafka is only for local development reliability, not a change to the event-driven architecture.
