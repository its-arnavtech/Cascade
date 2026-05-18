param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }

Write-Section "Reset Cascade Command Center UI"
kubectl config use-context "kind-$ClusterName" | Out-Null
Assert-NativeSuccess "Use kind context"

foreach ($path in @("infra/kubernetes/command-center/", "infra/kubernetes/command-center-api/")) {
    kubectl delete -f $path --ignore-not-found=true
    Assert-NativeSuccess "Delete $path"
}

Write-Section "Redeploy Command Center UI"
& .\scripts\deploy.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipRemediationDeploy
Assert-NativeSuccess "Redeploy Command Center UI"
Write-Host "COMMAND CENTER RESET: PASS"
