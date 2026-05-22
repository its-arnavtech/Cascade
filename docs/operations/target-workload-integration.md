# Target Workload Integration

A target workload is the Kubernetes application Cascade observes and reasons about. Sock Shop remains the canonical demo target, but Cascade can also observe an application you own by using a target config file and a monitored namespace.

Cascade uses the target workload in four places:

- `observation-service` collects pod and service telemetry from the target namespace.
- `topology-service` builds the dependency graph from `dependency_edges`.
- Chaos and remediation policy use `safe_chaos_services` and `protected_services`.
- Causality and blast-radius views combine telemetry windows with the topology graph.

## Safe Quick Path

```powershell
cd C:\Cascade

.\scripts\deploy.ps1

kubectl create namespace cascade-targets --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace cascade-targets cascade.io/monitored=true --overwrite
kubectl apply -n cascade-targets -f path\to\your-app.yaml

.\scripts\validate-target.ps1 -Namespace cascade-targets -ExpectedServices frontend,api -ShowLabels
```

Create a target config, then register it:

```powershell
Copy-Item -Recurse targets\template targets\my-app
notepad targets\my-app\target.yaml

.\scripts\validate-target.ps1 -Namespace cascade-targets -TargetConfig targets\my-app\target.yaml -Strict
.\scripts\configure-target.ps1 -TargetConfig targets\my-app\target.yaml
.\scripts\ensure-redpanda-topics.ps1
.\scripts\accept-telemetry.ps1
```

Open the Command Center:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Browse to `http://localhost:18300`.

## Required Labels

Use stable service labels on Pods and Services:

```yaml
labels:
  app: frontend
  app.kubernetes.io/name: frontend
  app.kubernetes.io/part-of: my-app
```

The namespace must be explicitly monitored:

```powershell
kubectl label namespace cascade-targets cascade.io/monitored=true --overwrite
```

## Target Config

Cascade defaults to Sock Shop. To select another target, provide a YAML or JSON config and set `CASCADE_TARGET_CONFIG` for the topology, chaos, and remediation services. The helper script does this by creating a ConfigMap and mounting it into those deployments.

Example:

```yaml
name: my-app
namespace: cascade-targets
frontend_service: frontend
services:
  - frontend
  - api
  - worker
  - postgres
dependency_edges:
  - from: frontend
    to: api
  - from: api
    to: worker
  - from: api
    to: postgres
safe_chaos_services:
  - frontend
  - api
  - worker
protected_services:
  - postgres
load_generator:
  name: load-generator
  image: curlimages/curl:8.11.1
  target_url: http://frontend.cascade-targets.svc.cluster.local/
  users: 5
  spawn_rate: 1
```

Register:

```powershell
.\scripts\configure-target.ps1 -TargetConfig targets\my-app\target.yaml
```

Preview without changing the cluster:

```powershell
.\scripts\configure-target.ps1 -TargetConfig targets\my-app\target.yaml -DryRun
```

## Protected And Safe Services

Put stateful or high-risk components in `protected_services`:

- databases
- brokers and queues
- caches
- auth and identity stores
- payment or external-integration adapters
- anything with persistent volumes

Put only stateless services you own in `safe_chaos_services`. If a service is not listed there, Cascade policy will not treat it as an allowed live chaos/remediation target.

## Traffic Generation

Telemetry and causality need activity. Use a small load generator in local/dev/staging, or point existing synthetic traffic at the frontend service. The template includes a harmless curl loop.

## Telemetry Validation

```powershell
.\scripts\ensure-redpanda-topics.ps1
.\scripts\accept-telemetry.ps1
```

If you changed namespaces, confirm the observation deployment has the right target:

```powershell
kubectl -n cascade-system get deployment observation-service -o jsonpath="{.spec.template.spec.containers[0].env[?(@.name=='TARGET_NAMESPACE')].value}"
```

## Dry-Run Workflow

Dry-run is the default. Use dry-run chaos and remediation first from the Command Center or acceptance scripts:

```powershell
.\scripts\accept-chaos.ps1 -DryRunOnly
.\scripts\accept-remediation.ps1
```

Review the topology, blast-radius, policy findings, and rollback notes before any live local demo.

## Optional Live Local Demo

Live controlled failure injection and remediation are opt-in only. Use them only for workloads you own in local/dev/staging, never production.

```powershell
.\scripts\install-chaos-mesh.ps1 -ConfirmLocalKind
.\scripts\verify-chaos-mesh.ps1
.\scripts\demo-real-chaos.ps1 -ConfirmLocalKind
.\scripts\demo-real-remediation.ps1 -ConfirmLocalKind
```

These paths remain policy-gated, approval-aware, and dry-run-first.

## Troubleshooting

No pods found:

```powershell
kubectl get namespace cascade-targets
kubectl -n cascade-targets get pods,svc
```

No telemetry:

```powershell
kubectl -n cascade-system logs deployment/observation-service --tail=100
.\scripts\ensure-redpanda-topics.ps1
.\scripts\accept-telemetry.ps1
```

RED metrics missing or marked insufficient:

```powershell
kubectl port-forward -n cascade-system svc/observation-service 18000:8000
Invoke-RestMethod "http://localhost:18000/snapshot" | ConvertTo-Json -Depth 8
```

Review `query_status`, `missing_metrics`, `collection_warnings`, and `evidence_quality`. Cascade can still use Kubernetes readiness, restarts, labels, and warning events, but request-rate/error-rate/latency gaps should lower RCA confidence until the workload exports compatible Prometheus RED series.

Service labels missing:

```powershell
.\scripts\validate-target.ps1 -Namespace cascade-targets -ShowLabels
```

Protected service denied:

Review `protected_services` and `safe_chaos_services`. Databases, brokers, queues, caches, auth stores, and stateful services should stay protected.

Prometheus unavailable:

```powershell
kubectl -n monitoring get pods,svc
kubectl -n cascade-system logs deployment/observation-service --tail=100
```

Redpanda topics missing:

```powershell
.\scripts\ensure-redpanda-topics.ps1
kubectl -n cascade-system get pods -l app=redpanda
```

Command Center empty states:

```powershell
kubectl -n cascade-system rollout status deployment/topology-service
kubectl -n cascade-system rollout status deployment/command-center-api
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Then refresh `http://localhost:18300`.
