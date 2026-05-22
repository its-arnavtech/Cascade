param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$ConfirmWipe
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }

Write-Section "Wipe Cascade persistent state"

if (-not $ConfirmWipe) {
    Write-Host "This script deletes local persistent Cascade evidence and history PVCs:"
    Write-Host "  - clickhouse-data"
    Write-Host "  - redpanda-data"
    Write-Host "  - qdrant-data"
    Write-Host ""
    Write-Host "Re-run with -ConfirmWipe only when you intentionally want to remove all local state."
    exit 2
}

kubectl config use-context "kind-$ClusterName" | Out-Null

Write-Host "Deleting stateful deployments before PVC removal in namespace $Namespace."
foreach ($resource in @(
    "deployment/clickhouse",
    "deployment/redpanda",
    "deployment/qdrant"
)) {
    kubectl -n $Namespace delete $resource --ignore-not-found=true
}

Write-Host "Deleting PVCs. This permanently removes local evidence/history after volume reclaim."
kubectl -n $Namespace delete pvc clickhouse-data redpanda-data qdrant-data --ignore-not-found=true

Write-Host "Persistent state wipe requested and completed."
