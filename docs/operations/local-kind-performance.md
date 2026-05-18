# Local Kind Performance Profile

Cascade keeps every service separate in local kind, but all Deployment manifests now carry CPU and memory requests/limits so Docker Desktop can schedule predictably instead of allowing one process to starve the node.

## Profiles

### Normal Mode

Normal mode is the default path used by the existing PowerShell deploy scripts. The scripts still apply the same per-service manifest directories, so `.\scripts\deploy.ps1` and the phase-specific deploy scripts do not require new flags.

Use normal mode when Docker Desktop has at least 6 to 8 GiB available to Kubernetes and you want more headroom for anomaly scoring, retrieval, ClickHouse, Redpanda, and Qdrant.

Key defaults:

- FastAPI service Deployments set `WEB_CONCURRENCY=1`.
- Redpanda runs as one local broker with `--mode dev-container`, `--overprovisioned`, `--smp 1`, and `--memory 768M`.
- ClickHouse is capped with `--max_server_memory_usage=1073741824`, `--max_thread_pool_size=100`, and `--max_concurrent_queries=20`.
- Qdrant caps service workers, search threads, and optimization threads with `QDRANT__...` environment settings.
- Core infra images are pinned instead of using `latest`.

### Low-Resource Mode

Low-resource mode is a kustomize overlay for constrained laptops or Docker Desktop settings around 4 GiB. It preserves the service topology and replica counts, but reduces requests/limits and tightens ClickHouse and Redpanda runtime caps.

Render or apply the overlay with:

```powershell
kubectl kustomize infra/kubernetes/overlays/low-resource
kubectl apply -k infra/kubernetes/overlays/low-resource
```

Use the normal deploy scripts first if you need to build and load local `cascade-*:dev` images into kind. The overlay changes Kubernetes manifests only; it does not build images.

The overlay uses `infra/kubernetes/base/resources.yaml` as a kustomize-safe bundle because this repo's default deploy scripts still apply individual service directories. If base manifest resources change, regenerate the bundle from `infra/kubernetes/kustomization.yaml` before running the overlay validation.

Low-resource overrides:

- Most FastAPI services: `50m` CPU request, `96Mi` memory request, `300m` CPU limit, `384Mi` memory limit.
- Anomaly detector: `100m` CPU request, `256Mi` memory request, `700m` CPU limit, `768Mi` memory limit.
- Retrieval and memory indexer: memory limits stay at `512Mi`.
- ClickHouse: `150m` CPU request, `512Mi` memory request, `700m` CPU limit, `1Gi` memory limit, `805306368` byte server memory cap, smaller background pools, and `10` concurrent queries.
- Redpanda: `150m` CPU request, `384Mi` memory request, `700m` CPU limit, `768Mi` memory limit, and `--memory 512M`.
- Qdrant: `75m` CPU request, `256Mi` memory request, `600m` CPU limit, `768Mi` memory limit.

## Tunables

Tune these first when a local kind cluster is still under pressure:

- Docker Desktop memory and CPU allocation.
- `infra/kubernetes/redpanda/deployment.yaml`: `--memory`, resource requests, and resource limits.
- `infra/kubernetes/clickhouse/deployment.yaml`: `--max_server_memory_usage`, `--max_thread_pool_size`, `--background_pool_size`, `--background_schedule_pool_size`, and `--max_concurrent_queries`.
- `infra/kubernetes/qdrant/deployment.yaml`: `QDRANT__SERVICE__MAX_WORKERS`, `QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS`, and `QDRANT__STORAGE__OPTIMIZERS__MAX_OPTIMIZATION_THREADS`.
- Individual service `resources` blocks when a specific pod is repeatedly `OOMKilled` or throttled.
- `.env.example` has `WEB_CONCURRENCY=1` for local non-Kubernetes runs.

## Validation

Run these checks after changing resource profiles:

```powershell
python -m pytest tests/test_k8s_resource_profiles.py
kubectl kustomize infra/kubernetes/overlays/low-resource
python -m compileall services tests
python -m ruff check services tests
```
