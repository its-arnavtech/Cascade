param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [switch]$ClearPhase7Tables
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function CH { param([string]$Query) $pod = (kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath="{.items[0].metadata.name}"); if ($pod) { kubectl -n $Namespace exec $pod -- clickhouse-client --query $Query; Assert-NativeSuccess "ClickHouse query" } }

Write-Section "Reset Cascade Phase 7"
kubectl config use-context "kind-$ClusterName" | Out-Null

Write-Section "Cleanup Cascade-managed Chaos Mesh Resources"
foreach ($kind in @("podchaos", "networkchaos", "stresschaos")) {
    kubectl -n $TargetNamespace delete $kind -l cascade.io/phase=phase7 --ignore-not-found=true
}

kubectl -n $Namespace delete deployment chaos-planner-service chaos-executor-service --ignore-not-found=true
kubectl -n $Namespace delete service chaos-planner-service chaos-executor-service --ignore-not-found=true
kubectl delete -f infra/kubernetes/chaos-executor-service/rbac.yaml --ignore-not-found=true

if ($ClearPhase7Tables) {
    Write-Section "Clear Phase 7 Tables"
    foreach ($table in @("chaos_experiment_plans", "chaos_experiment_runs", "chaos_observations", "resilience_scores", "chaos_safety_violations")) {
        CH "TRUNCATE TABLE IF EXISTS cascade.$table"
    }
}

Write-Section "Redeploy Phase 7"
& .\scripts\deploy-phase-7.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipPhase6Deploy
Assert-NativeSuccess "Deploy Phase 7"
Write-Host "PHASE 7 RESET: PASS"
