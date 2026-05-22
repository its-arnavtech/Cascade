param(
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}
function Start-PortForward {
    param([string]$Service, [int]$LocalPort, [int]$RemotePort)
    $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", "$LocalPort`:$RemotePort") -WindowStyle Hidden -PassThru
    $script:PortForwards.Add($p) | Out-Null
    Start-Sleep -Seconds 3
    if ($p.HasExited) { throw "port-forward for svc/$Service exited early" }
}
function Stop-PortForwards {
    foreach ($p in $script:PortForwards) {
        if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    }
    $script:PortForwards.Clear()
}

try {
    Write-Section "Accept Cascade Scheduler"
    kubectl -n $Namespace rollout status deployment/scheduler-service --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "scheduler-service rollout is not healthy" }

    $port = Get-FreePort
    Start-PortForward "scheduler-service" $port 8025
    $health = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/health" -TimeoutSec 20
    if ($health.service -ne "scheduler-service") { throw "Unexpected scheduler health payload" }
    if ($health.mode -ne "dry-run scheduler") { throw "Scheduler is not reporting dry-run scheduler mode" }
    $status = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/scheduler/status" -TimeoutSec 20
    if ($null -eq $status.items) { throw "Scheduler status did not include item count" }
    $body = @{
        item_type = "autopilot_run"
        target_id = "acceptance"
        name = "Acceptance Autopilot dry-run"
        schedule = @{ trigger = "interval"; interval_seconds = 60 }
        enabled = $true
        paused = $false
        mode = "dry_run_scheduler"
        payload = @{
            service = "catalogue"
            namespace = "cascade-targets"
            objective = "Scheduler acceptance dry-run"
            mode = "dry_run"
            preferred_action_type = "investigate_only"
        }
    } | ConvertTo-Json -Depth 20
    $created = Invoke-RestMethod -Method POST -Uri "http://localhost:$port/scheduler/items" -Body $body -ContentType "application/json" -TimeoutSec 20
    if (-not $created.item.item_id) { throw "Scheduler item creation did not return item_id" }
    $paused = Invoke-RestMethod -Method POST -Uri "http://localhost:$port/scheduler/items/$($created.item.item_id)/pause" -Body (@{ reason = "acceptance pause" } | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 20
    if (-not $paused.item.paused) { throw "Scheduler pause did not set paused state" }
    $resumed = Invoke-RestMethod -Method POST -Uri "http://localhost:$port/scheduler/items/$($created.item.item_id)/resume" -Body (@{ reason = "acceptance resume" } | ConvertTo-Json) -ContentType "application/json" -TimeoutSec 20
    if ($resumed.item.paused) { throw "Scheduler resume did not clear paused state" }
    $history = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/scheduler/history?limit=10" -TimeoutSec 20
    if ($null -eq $history.count) { throw "Scheduler history endpoint did not include a count" }
    Write-Host "PASS: scheduler-service health, status, item create, pause, resume, and history endpoints"
    Write-Host "CASCADE SCHEDULER ACCEPTANCE: PASS"
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
} finally {
    Stop-PortForwards
}
