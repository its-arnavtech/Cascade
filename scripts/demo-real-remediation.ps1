param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [ValidateSet("catalogue", "carts", "orders", "payment", "shipping", "queue-master", "user")]
    [string]$TargetService = "catalogue",
    [string]$ExpectedContext = "kind-cascade",
    [switch]$ConfirmLocalKind,
    [switch]$AllowContextOverride
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 240 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 240 } }

try {
    if (-not $ConfirmLocalKind) { throw "Refusing real remediation without -ConfirmLocalKind." }
    $context = (& kubectl config current-context 2>&1).Trim()
    if ($context -ne $ExpectedContext -and -not $AllowContextOverride) { throw "Refusing context '$context'. Expected '$ExpectedContext'." }

    Invoke-Checked "Verify target namespace" { kubectl get namespace $TargetNamespace }
    Invoke-Checked "Verify target deployment" { kubectl -n $TargetNamespace get deployment $TargetService }
    Invoke-Checked "Enable live remediation flags on executor" {
        kubectl -n $Namespace set env deployment/remediation-executor-service `
            EXECUTION_ENABLED=true ENABLE_DANGEROUS_ACTIONS=true ENABLE_REAL_REMEDIATION=true CASCADE_LIVE_DEMO_MODE=true `
            CASCADE_ACTIVE_CLUSTER_CONTEXT=$ExpectedContext CASCADE_ALLOWED_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_TARGET_NAMESPACE=$TargetNamespace CASCADE_REQUIRE_APPROVAL=true CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }
    Invoke-Checked "Wait for remediation executor rollout" { kubectl -n $Namespace rollout status deployment/remediation-executor-service --timeout=180s }

    Start-PF "remediation-recommender-service" "8021:8021"
    Start-PF "approval-service" "8022:8022"
    Start-PF "remediation-executor-service" "8023:8023"

    $plan = HttpJson POST "http://localhost:8021/plans" @{ trigger_type = "manual"; service = $TargetService; namespace = $TargetNamespace; objective = "Local demo restart for $TargetService after dry-run validation"; preferred_action_type = "restart_deployment" }
    $planId = $plan.plan_id
    if (-not $plan.plan.rollback_steps -or -not $plan.plan.plan.post_checks) { throw "Plan is missing rollback steps or post-checks." }
    $approval = HttpJson POST "http://localhost:8022/approvals" @{ plan_id = $planId; decision = "approved"; approver = "local-demo-user"; approver_role = "developer"; reason = "Approved local demo remediation after dry-run"; expires_minutes = 30 }
    $dry = HttpJson POST "http://localhost:8023/executions/dry-run" @{ plan_id = $planId; approval_id = $approval.approval.approval_id; dry_run = $true }
    if ($dry.execution.validation_status -notin @("passed", "degraded")) { throw "Remediation dry-run did not pass." }
    $execution = HttpJson POST "http://localhost:8023/executions" @{ plan_id = $planId; approval_id = $approval.approval.approval_id; dry_run = $false }
    $execution | ConvertTo-Json -Depth 40
    Invoke-Checked "Verify deployment recovers" { kubectl -n $TargetNamespace rollout status "deployment/$TargetService" --timeout=180s }

    Write-Host ""
    Write-Host "Rollback/recovery commands:"
    Write-Host "kubectl -n $TargetNamespace rollout status deployment/$TargetService --timeout=180s"
    Write-Host "kubectl -n $TargetNamespace rollout restart deployment/$TargetService"
    Write-Host "kubectl -n $Namespace set env deployment/remediation-executor-service EXECUTION_ENABLED=false ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_REMEDIATION=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-"
} finally {
    Stop-PF
}
