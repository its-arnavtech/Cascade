param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$ClearAnomalyTables
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }

Write-Section "Reset Cascade Anomaly detection"
kubectl config use-context "kind-$ClusterName" | Out-Null
foreach ($resource in @(
    "deployment/feature-extractor-service",
    "deployment/anomaly-detector-service",
    "service/feature-extractor-service",
    "service/anomaly-detector-service"
)) {
    kubectl -n $Namespace delete $resource --ignore-not-found=true
}

if ($ClearAnomalyTables) {
    $pod = kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath='{.items[0].metadata.name}'
    if ($pod) {
        kubectl -n $Namespace exec $pod -- clickhouse-client --multiquery --query "TRUNCATE TABLE IF EXISTS cascade.telemetry_feature_windows; TRUNCATE TABLE IF EXISTS cascade.anomaly_events; TRUNCATE TABLE IF EXISTS cascade.model_runs"
    }
}

Write-Section "Redeploy Anomaly detection"
& .\scripts\deploy-anomaly-detection.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipStorageMemoryDeploy

