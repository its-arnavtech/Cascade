# Target Workload Demo

Cascade is the reliability platform. Online Boutique is the demo application that Cascade observes, investigates, and safely targets with dry-run chaos and remediation workflows.

Online Boutique lives under `targets/online-boutique-src/` and is intentionally kept close to the upstream Google Cloud microservices demo. It includes services in multiple languages. The `adservice` is Java because upstream Online Boutique implements that service in Java; it is target workload code, not Cascade product code.

Generated target build artifacts such as Gradle `.gradle/` and `build/` directories are ignored. Do not change target service behavior unless a local build or deployment compatibility issue requires it.

## Verify Target Resources

```powershell
kubectl get pods -n cascade-targets
kubectl get svc -n cascade-targets
kubectl get deploy -n cascade-targets
```

Expected target services include `frontend`, `recommendationservice`, `adservice`, `cartservice`, `checkoutservice`, `currencyservice`, `emailservice`, `paymentservice`, `productcatalogservice`, `shippingservice`, and `redis-cart`.

## Open Online Boutique Locally

```powershell
kubectl port-forward -n cascade-targets svc/frontend 18099:80
```

Open `http://localhost:18099`.

## Generate Demo Traffic

With the port-forward running:

```powershell
1..60 | ForEach-Object {
  Invoke-WebRequest -UseBasicParsing http://localhost:18099/ | Out-Null
  Invoke-WebRequest -UseBasicParsing http://localhost:18099/product/OLJCESPC7Z | Out-Null
  Start-Sleep -Milliseconds 500
}
```

## Prometheus Checks

Use these queries to confirm Kubernetes target signals are present:

```promql
kube_pod_status_phase{namespace="cascade-targets"}
sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="cascade-targets", container!="", pod!=""}[5m]))
sum by (pod) (container_memory_working_set_bytes{namespace="cascade-targets", container!="", pod!=""})
sum by (pod) (kube_pod_container_status_restarts_total{namespace="cascade-targets", container!="", pod!=""})
```

## Validate Cascade Observation

Run the normal phase acceptance checks after target deployment:

```powershell
.\scripts\accept-telemetry.ps1
.\scripts\accept-anomaly-detection.ps1
.\scripts\accept-chaos.ps1 -DryRunOnly
.\scripts\accept-remediation.ps1
.\scripts\accept.ps1
.\scripts\accept-all.ps1
```

Telemetry pipeline proves telemetry flow, Anomaly detection proves anomaly detection, Chaos engineering proves safe chaos dry-runs against the target, Remediation proves remediation planning and dry-run validation, and Command Center UI proves the Command Center path.

## Safe Chaos Dry-Run

The normal demo target for chaos is `recommendationservice` in namespace `cascade-targets`. Keep demos in dry-run mode:

```powershell
.\scripts\accept-chaos.ps1 -DryRunOnly
```

The Command Center UI also exposes dry-run planning and dry-run execution only by default.

## Command Center Demo

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Open `http://localhost:18300`.

Recommended demo flow:

1. Use Online Boutique traffic to create fresh target activity.
2. Open Command Center Overview and confirm counts update.
3. Inspect `/telemetry` for target service events.
4. Inspect `/anomalies` and start a deterministic investigation if signals exist.
5. Search `/knowledge` for a runbook, for example `recommendationservice latency runbook`.
6. Use `/chaos` to create a dry-run plan against `recommendationservice`.
7. Use `/remediation` to create a safe plan, record approval, and run dry-run validation.
8. Use `/system` to confirm backend health.

## Editing Target Workload Code

If VS Code reports Java issues in `targets/online-boutique-src/src/adservice`, first check whether they come from generated Gradle folders or missing Java/Gradle extension state. Use `.vscode/settings.example.json` as a safe example for excluding generated files from watcher/search noise while keeping source diagnostics enabled.
