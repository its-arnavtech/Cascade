# Topology Discovery

Cascade now treats the target catalog as a fallback and override source, not the only topology source.

The topology service exposes an evidence-rich graph at:

```text
GET /topology/graph
POST /topology/refresh
GET /topology/evidence
GET /topology/catalog
POST /topology/traffic-inference
```

The Command Center API proxies these through `/api/topology/graph`, `/api/topology/topology/refresh`, and `/api/topology/evidence`.

## Sources

Edges are labeled with their source:

- `static_catalog`: declared in `CASCADE_TARGET_CONFIG` or the built-in Sock Shop catalog.
- `kubernetes_selector`: inferred from Service or Deployment selectors matching Pod labels.
- `kubernetes_owner_reference`: inferred from Pod and ReplicaSet owner references.
- `traffic_inferred`: aggregated from telemetry records that explicitly carry caller/dependency service fields plus request/error/latency counts.
- `telemetry_inferred`: reserved for older events that explicitly carry caller/dependency service fields.
- `trace_inferred`: reserved for trace-like records that explicitly carry caller/dependency service fields.
- `unknown/fallback`: low-confidence fallback evidence such as a deployment environment variable referencing a service name.

Each node and edge includes `source_type`, `confidence`, `last_seen`, and an `evidence` string. Conservative confidence is intentional: if Cascade cannot prove dependency direction, it marks the edge low-confidence instead of pretending certainty.

## Kubernetes Discovery

When running in-cluster with read access to the target namespace, topology discovery reads:

- Services
- Deployments
- ReplicaSets
- Pods
- labels and selectors
- owner references
- pod readiness and deployment replica status

Selector and owner-reference edges show live service-to-pod and deployment-to-pod relationships. Static catalog dependency edges remain present so custom target configs continue to work even when Kubernetes discovery is unavailable.

## Limitations

Kubernetes selectors prove wiring between Services, Deployments, and Pods. They do not prove request direction between application services. Cascade only marks service dependency direction as high-confidence when it comes from the target catalog, traces, or explicit telemetry fields. Environment-variable references are exposed as low-confidence `unknown/fallback` evidence.

If the topology service cannot read the Kubernetes API, `/topology/graph` returns `discovery_status=static_fallback` with static catalog data and warnings.

## Optional Traffic And Trace Inference

Cascade does not require Jaeger, Tempo, a service mesh, or any paid tracing service. It now has a lightweight ingestion shape for future trace-like edge evidence:

```json
{
  "source_service": "frontend",
  "target_service": "checkoutservice",
  "request_count": 120,
  "error_count": 3,
  "latency_p95_ms": 280,
  "observation_window": "2026-05-21T12:00:00Z/2026-05-21T12:05:00Z",
  "evidence_source": "trace"
}
```

When such records are supplied to topology discovery, Cascade creates `traffic_inferred` or `trace_inferred` `depends_on` edges with request count, error count, latency summary, confidence, and `last_seen` metadata. Kubernetes selector/owner edges remain separate and are not treated as request direction.

`GET /topology/evidence` includes `traffic_summary` and edge metadata so operators can distinguish static catalog direction from observed traffic direction.

`POST /topology/traffic-inference` is a local, optional analysis interface. It accepts trace-like edge records and returns a graph payload with `traffic_inferred` or `trace_inferred` edges. It does not call an external tracing service and does not mutate the cluster.
