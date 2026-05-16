param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }

Write-Section "Reset Cascade Phase 9"
kubectl config use-context "kind-$ClusterName" | Out-Null
Assert-NativeSuccess "Use kind context"

foreach ($path in @("infra/kubernetes/command-center/", "infra/kubernetes/command-center-api/")) {
    kubectl delete -f $path --ignore-not-found=true
    Assert-NativeSuccess "Delete $path"
}

Write-Section "Redeploy Phase 9"
& .\scripts\deploy-phase-9.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipPhase8Deploy
Assert-NativeSuccess "Redeploy Phase 9"
Write-Host "PHASE 9 RESET: PASS"
