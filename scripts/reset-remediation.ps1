param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$ClearRemediationTables
)

$ErrorActionPreference = "Stop"
function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }

Write-Section "Reset Cascade Remediation Resources"
kubectl config use-context "kind-$ClusterName" | Out-Null

foreach ($path in @(
    "infra/kubernetes/remediation-recommender-service/",
    "infra/kubernetes/approval-service/",
    "infra/kubernetes/remediation-executor-service/"
)) {
    kubectl delete -f $path --ignore-not-found=true
}
kubectl delete -f infra/kubernetes/remediation-executor-service/rbac.yaml --ignore-not-found=true

if ($ClearRemediationTables) {
    Write-Section "Clear Remediation Tables"
    $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim()
    if ($pod) {
        foreach ($table in @("remediation_plans", "remediation_approvals", "remediation_executions", "remediation_safety_violations", "remediation_policy_audit")) {
            kubectl -n $Namespace exec $pod -- clickhouse-client --query "TRUNCATE TABLE IF EXISTS cascade.$table"
        }
    }
}

Write-Section "Redeploy Remediation"
& .\scripts\deploy-remediation.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipChaosDeploy
if ($LASTEXITCODE -ne 0) { throw "Remediation redeploy failed" }
Write-Host "REMEDIATION RESET: PASS"

