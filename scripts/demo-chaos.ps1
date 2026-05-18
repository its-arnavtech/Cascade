param(
    [string]$Namespace = "cascade-system",
    [string]$TargetService = "recommendationservice",
    [int]$ObservationWindowSeconds = 60,
    [switch]$DryRunOnly,
    [switch]$NoAgent
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 300 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 60) -TimeoutSec 300 } }

try {
    Write-Section "Chaos engineering Demo - Safe Chaos Automation"
    Start-PF "chaos-planner-service" "8019:8019"
    Start-PF "chaos-executor-service" "8020:8020"

    Write-Section "Safety Policy"
    HttpJson GET "http://localhost:8020/safety/policy" | ConvertTo-Json -Depth 20

    Write-Section "Create Safe Plan"
    $plan = HttpJson POST "http://localhost:8019/plans" @{ objective = "Validate $TargetService resilience to a bounded pod kill"; target_service = $TargetService; target_namespace = "cascade-targets"; experiment_kind = "pod_kill"; duration_seconds = 5; dry_run = $true }
    $plan | Select-Object plan_id, status, risk_level, safety_score, blast_radius_score | Format-List

    Write-Section "Safety Rejection Example"
    try {
        HttpJson POST "http://localhost:8019/plans" @{ objective = "Unsafe system namespace test"; target_service = $TargetService; target_namespace = "kube-system"; experiment_kind = "pod_kill"; duration_seconds = 5; dry_run = $true } | ConvertTo-Json -Depth 20
    } catch {
        Write-Host "Rejected as expected: $($_.Exception.Message)"
    }

    Write-Section "Dry-run Execution"
    $dry = HttpJson POST "http://localhost:8020/runs" @{ plan_id = $plan.plan_id; approved = $false; dry_run = $true; observation_window_seconds = 5; trigger_agent_investigation = $false }
    $dry | ConvertTo-Json -Depth 20

    if (-not $DryRunOnly) {
        Write-Section "Real Bounded Pod Kill"
        $run = HttpJson POST "http://localhost:8020/runs" @{ plan_id = $plan.plan_id; approved = $true; dry_run = $false; observation_window_seconds = $ObservationWindowSeconds; trigger_agent_investigation = (-not $NoAgent) }
        $run | Select-Object run_id, plan_id, status, cleanup_status | Format-List

        Write-Section "Run Detail"
        $detail = HttpJson GET "http://localhost:8020/runs/$($run.run_id)"
        $detail | ConvertTo-Json -Depth 30

        Write-Section "Resilience Score"
        $detail.score | ConvertTo-Json -Depth 20
    } else {
        Write-Host "DryRunOnly requested; real chaos execution skipped."
    }
} finally {
    Stop-PF
}
