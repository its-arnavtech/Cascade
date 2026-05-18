param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [ValidateSet("catalogue", "carts", "orders", "payment", "shipping", "queue-master", "user")]
    [string]$TargetService = "catalogue",
    [int]$DurationSeconds = 15,
    [string]$ExpectedContext = "kind-cascade",
    [switch]$ConfirmLocalKind,
    [switch]$AllowContextOverride
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
. "$PSScriptRoot\lib\kafka-topics.ps1"

function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 240 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 240 } }

try {
    if (-not $ConfirmLocalKind) { throw "Refusing real chaos without -ConfirmLocalKind." }
    if ($DurationSeconds -lt 10 -or $DurationSeconds -gt 30) { throw "DurationSeconds must be between 10 and 30." }
    $context = (& kubectl config current-context 2>&1).Trim()
    if ($context -ne $ExpectedContext -and -not $AllowContextOverride) { throw "Refusing context '$context'. Expected '$ExpectedContext'." }

    Invoke-Checked "Verify Sock Shop target pods" { kubectl -n $TargetNamespace get pods -l "app=$TargetService" }
    Invoke-Checked "Verify Chaos Mesh" { & "$PSScriptRoot\verify-chaos-mesh.ps1" -ExpectedContext $ExpectedContext -TargetNamespace $TargetNamespace }
    $topics = Ensure-CascadeRedpandaTopics -Namespace $Namespace -Topics @("chaos.experiments", "experiments.events")
    if (-not $topics.Success) { throw "Required Redpanda topics missing: $($topics.Missing -join ', ')" }

    Invoke-Checked "Enable live chaos flags on executor" {
        kubectl -n $Namespace set env deployment/chaos-executor-service `
            ENABLE_DANGEROUS_ACTIONS=true ENABLE_REAL_CHAOS=true CASCADE_LIVE_DEMO_MODE=true `
            CASCADE_ACTIVE_CLUSTER_CONTEXT=$ExpectedContext CASCADE_ALLOWED_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_TARGET_NAMESPACE=$TargetNamespace CASCADE_REQUIRE_APPROVAL=true CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }
    Invoke-Checked "Wait for chaos executor rollout" { kubectl -n $Namespace rollout status deployment/chaos-executor-service --timeout=180s }

    Start-PF "chaos-planner-service" "8019:8019"
    Start-PF "chaos-executor-service" "8020:8020"
    Start-PF "approval-service" "8022:8022"

    $plan = HttpJson POST "http://localhost:8019/plans" @{ objective = "Local demo bounded pod kill for $TargetService"; target_service = $TargetService; target_namespace = $TargetNamespace; experiment_kind = "pod_kill"; duration_seconds = $DurationSeconds; dry_run = $true }
    $planId = $plan.plan_id
    $dry = HttpJson POST "http://localhost:8020/runs" @{ plan_id = $planId; dry_run = $true; approved = $false; observation_window_seconds = 5; trigger_agent_investigation = $false }
    if ($dry.status -ne "dry_run") { throw "Chaos dry-run did not pass." }
    $approval = HttpJson POST "http://localhost:8022/approvals" @{ plan_id = $planId; decision = "approved"; approver = "local-demo-user"; approver_role = "developer"; reason = "Approved local demo real chaos after dry-run"; expires_minutes = 30 }
    $run = HttpJson POST "http://localhost:8020/runs" @{ plan_id = $planId; approval_id = $approval.approval.approval_id; dry_run = $false; approved = $false; observation_window_seconds = 10; trigger_agent_investigation = $false }
    $run | ConvertTo-Json -Depth 40

    Invoke-Checked "Verify target deployment recovers" { kubectl -n $TargetNamespace rollout status "deployment/$TargetService" --timeout=180s }
    Invoke-Checked "Cleanup managed Chaos Mesh resources" { kubectl -n $TargetNamespace delete podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found=true }

    Write-Host ""
    Write-Host "Cleanup commands:"
    Write-Host "kubectl -n $TargetNamespace delete podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found=true"
    Write-Host "kubectl -n $Namespace set env deployment/chaos-executor-service ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_CHAOS=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-"
} finally {
    Stop-PF
}
