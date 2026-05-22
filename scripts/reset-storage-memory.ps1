param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$KeepData,
    [switch]$WipePersistentData
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }

if ($KeepData -and $WipePersistentData) {
    throw "Use either -KeepData or -WipePersistentData, not both."
}

Write-Section "Reset Cascade Storage and memory"
kubectl config use-context "kind-$ClusterName" | Out-Null
Write-Host "Default reset redeploys storage services and keeps persistent ClickHouse/Qdrant data."
Write-Host "Use -WipePersistentData to delete ClickHouse and Qdrant PVCs. Use scripts/wipe-cascade-state.ps1 -ConfirmWipe for ClickHouse, Redpanda, and Qdrant."

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

if ($WipePersistentData) {
    Write-Section "WIPE persistent storage"
    Write-Host "Deleting PVCs clickhouse-data and qdrant-data in namespace $Namespace."
    Write-Host "This removes local ClickHouse tables and Qdrant collections after the underlying storage class reclaims volumes."
    kubectl -n $Namespace delete pvc clickhouse-data qdrant-data --ignore-not-found=true
} else {
    Write-Host "Persistent PVCs were kept. Pass -WipePersistentData only for an intentional full local wipe."
}

Write-Section "Redeploy Storage and memory"
& .\scripts\deploy-storage-memory.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipTelemetryDeploy
