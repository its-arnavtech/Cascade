param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$ClearPhase8Tables
)

$ErrorActionPreference = "Stop"
function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }

Write-Section "Reset Cascade Phase 8 Resources"
kubectl config use-context "kind-$ClusterName" | Out-Null

foreach ($path in @(
    "infra/kubernetes/remediation-recommender-service/",
    "infra/kubernetes/approval-service/",
    "infra/kubernetes/remediation-executor-service/"
)) {
    kubectl delete -f $path --ignore-not-found=true
}
kubectl delete -f infra/kubernetes/remediation-executor-service/rbac.yaml --ignore-not-found=true

if ($ClearPhase8Tables) {
    Write-Section "Clear Phase 8 Tables"
    $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim()
    if ($pod) {
        foreach ($table in @("remediation_plans", "remediation_approvals", "remediation_executions", "remediation_safety_violations", "remediation_policy_audit")) {
            kubectl -n $Namespace exec $pod -- clickhouse-client --query "TRUNCATE TABLE IF EXISTS cascade.$table"
        }
    }
}

Write-Section "Redeploy Phase 8"
& .\scripts\deploy-phase-8.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipPhase7Deploy
if ($LASTEXITCODE -ne 0) { throw "Phase 8 redeploy failed" }
Write-Host "PHASE 8 RESET: PASS"

