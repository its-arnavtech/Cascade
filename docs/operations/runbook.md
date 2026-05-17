# Cascade Operations Runbook

Cascade runs locally on kind in the `cascade-system` namespace and observes demo workloads in `cascade-targets`.

## Startup

Deploy phases in order when starting from a fresh cluster:

```powershell
.\scripts\deploy-phase-2.ps1
.\scripts\deploy-phase-3.ps1
.\scripts\deploy-phase-4.ps1
.\scripts\deploy-phase-5.ps1
.\scripts\deploy-phase-6.ps1
.\scripts\deploy-phase-7.ps1
.\scripts\deploy-phase-8.ps1
.\scripts\deploy-phase-9.ps1
```

For a cluster that already has Phase 8 healthy, Phase 9 can be refreshed directly:

```powershell
.\scripts\deploy-phase-9.ps1 -SkipPhase8Deploy
```

## Acceptance

```powershell
.\scripts\accept-phase-9.ps1
.\scripts\accept-all.ps1
```

Use `-ContinueOnFailure` on `accept-all.ps1` when collecting a full failure matrix.

## Access

Command Center:

```powershell
kubectl port-forward -n cascade-system svc/command-center 18300:8030
```

Open `http://localhost:18300`.

Online Boutique target workload:

```powershell
kubectl get pods -n cascade-targets
kubectl get svc -n cascade-targets
kubectl port-forward -n cascade-targets svc/frontend 18099:80
```

Open `http://localhost:18099`. Online Boutique is the observed demo workload, not Cascade product code. Its Java `adservice` exists because upstream Online Boutique uses Java for that service. Generated Gradle/build folders under `targets/online-boutique-src/` are ignored; if editing target code in VS Code, use Java/Gradle extension setup and avoid treating generated reports or class output as source.

Common service forwards:

```powershell
kubectl port-forward -n cascade-system svc/clickhouse 18123:8123
kubectl port-forward -n cascade-system svc/qdrant 16333:6333
kubectl port-forward -n cascade-system svc/retrieval-service 18012:8012
```

## Debugging

Collect a support bundle:

```powershell
.\scripts\debug-all.ps1
```

Phase-specific scripts remain available, including `debug-phase-9.ps1` for Command Center resources and proxy checks.

## Backups

```powershell
.\scripts\backup-clickhouse.ps1
.\scripts\backup-qdrant.ps1
```

Restore scripts are dry-run by default and require `-ConfirmRestore`.

## Safety Notes

- Real remediation execution is disabled by default.
- The Command Center proxy blocks real remediation and real chaos execution unless explicitly reconfigured.
- Phase 7 acceptance should use `-DryRunOnly` for normal validation.
- Local rate limiting is in-memory and applies only to the `command-center-api` pod.

## Reset And Cleanup

Use phase reset scripts when a local demo has accumulated too much state:

```powershell
.\scripts\reset-phase-9.ps1
.\scripts\reset-phase-8.ps1
.\scripts\reset-phase-7.ps1
```

Repeated demos create additional ClickHouse rows. For latest run views, query by the relevant timestamp field and group by run or plan identifier instead of treating raw transition rows as unique final states.
