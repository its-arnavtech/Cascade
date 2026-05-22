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
    Write-Section "Accept Cascade Autopilot"
    kubectl -n $Namespace rollout status deployment/autopilot-service --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "autopilot-service rollout is not healthy" }

    $port = Get-FreePort
    Start-PortForward "autopilot-service" $port 8024
    $health = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/health" -TimeoutSec 20
    if ($health.service -ne "autopilot-service") { throw "Unexpected Autopilot health payload" }
    $mode = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/mode" -TimeoutSec 20
    if (-not $mode.safe_by_default) { throw "Autopilot mode does not report safe_by_default" }
    $runs = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/runs?limit=5" -TimeoutSec 20
    if ($null -eq $runs.count) { throw "Autopilot runs endpoint did not return a count" }
    $body = @{
        trigger_type = "manual"
        service = "catalogue"
        namespace = "cascade-targets"
        objective = "Acceptance dry-run Autopilot workflow"
        mode = "dry_run"
        preferred_action_type = "investigate_only"
    } | ConvertTo-Json
    $created = Invoke-RestMethod -Method POST -Uri "http://localhost:$port/runs" -Body $body -ContentType "application/json" -TimeoutSec 120
    if (-not $created.run.run_id) { throw "Autopilot run response did not include a run_id" }
    if ($created.run.mode -ne "dry_run") { throw "Autopilot run did not use dry_run mode" }
    if ($created.run.dry_run_execution_id -eq "") { throw "Autopilot dry-run did not produce a dry_run_execution_id" }
    if ($created.run.execution_id -ne "") { throw "Autopilot dry-run unexpectedly executed a real action" }
    if ($created.run.status -notin @("fixed", "degraded", "unchanged", "failed", "rolled_back")) { throw "Autopilot run did not reach a terminal state" }
    $detail = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/runs/$($created.run.run_id)" -TimeoutSec 20
    if ($detail.steps.Count -lt 6) { throw "Autopilot run detail did not include expected state steps" }
    $evidence = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/runs/$($created.run.run_id)/evidence" -TimeoutSec 20
    if ($null -eq $evidence.evidence -or $null -eq $evidence.recommendation -or $null -eq $evidence.action -or $null -eq $evidence.verification) {
        throw "Autopilot evidence endpoint did not include evidence/recommendation/action/verification"
    }
    Write-Host "PASS: autopilot-service health, mode, runs, dry-run workflow, detail, and evidence endpoints"
    Write-Host "CASCADE AUTOPILOT ACCEPTANCE: PASS"
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    exit 1
} finally {
    Stop-PortForwards
}
