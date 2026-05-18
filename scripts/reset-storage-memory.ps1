param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$KeepData
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }

Write-Section "Reset Cascade Storage and memory"
kubectl config use-context "kind-$ClusterName" | Out-Null

foreach ($resource in @(
    "deployment/retrieval-service",
    "deployment/memory-indexer",
    "deployment/telemetry-archiver",
    "service/retrieval-service",
    "service/memory-indexer",
    "service/telemetry-archiver",
    "job/clickhouse-schema-init",
    "job/qdrant-collection-init"
)) {
    kubectl -n $Namespace delete $resource --ignore-not-found=true
}

if (-not $KeepData) {
    foreach ($resource in @(
        "deployment/clickhouse",
        "service/clickhouse",
        "deployment/qdrant",
        "service/qdrant"
    )) {
        kubectl -n $Namespace delete $resource --ignore-not-found=true
    }
}

Write-Section "Redeploy Storage and memory"
& .\scripts\deploy-storage-memory.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipTelemetryDeploy

