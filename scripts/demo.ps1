param(
    [int]$Port = 18300,
    [string]$Namespace = "cascade-system",
    [switch]$NoBrowser,
    [switch]$SkipActionDemo
)

$ErrorActionPreference = "Stop"
$PortForward = $null

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 30 } return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 40) -TimeoutSec 60 }
function Test-ServiceEndpoint {
    param([string]$Service)
    $slices = kubectl -n $Namespace get endpointslice -l "kubernetes.io/service-name=$Service" -o json | ConvertFrom-Json
    foreach ($slice in @($slices.items)) {
        foreach ($endpoint in @($slice.endpoints)) {
            if (@($endpoint.addresses).Count -ge 1 -and (($endpoint.conditions.ready -eq $true) -or ($null -eq $endpoint.conditions.ready))) { return }
        }
    }
    throw "svc/$Service has no endpoints"
}
function Test-PortAvailable {
    param([int]$LocalPort)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect("127.0.0.1", $LocalPort, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(300, $false)) {
            $client.EndConnect($iar)
            return $false
        }
        return $true
    } catch {
        return $true
    } finally {
        $client.Close()
    }
}

try {
    Write-Section "Cascade Command Center UI Demo"
    kubectl -n $Namespace rollout status deployment/command-center --timeout=60s
    kubectl -n $Namespace rollout status deployment/command-center-api --timeout=60s
    Test-ServiceEndpoint "command-center"
    Test-ServiceEndpoint "command-center-api"
    if (-not (Test-PortAvailable $Port)) { throw "Local port $Port is already in use. Pass -Port with a free port." }

    Write-Host "Starting port-forward on http://localhost:$Port"
    $PortForward = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/command-center", "$Port`:8030") -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 3
    if ($PortForward.HasExited) { throw "port-forward exited early" }

    Write-Section "API Health"
    HttpJson GET "http://localhost:$Port/api/retrieval/health" | ConvertTo-Json -Depth 20
    HttpJson GET "http://localhost:$Port/api/retrieval/debug/counts" | ConvertTo-Json -Depth 20
    HttpJson GET "http://localhost:$Port/api/remediation/executor/safety/policy" | ConvertTo-Json -Depth 20

    if (-not $SkipActionDemo) {
        Write-Section "Safe Action Demo"
        $investigation = HttpJson POST "http://localhost:$Port/api/agent/investigations" @{
            trigger_type = "manual"
            service = "catalogue"
            namespace = "cascade-targets"
            objective = "Demo deterministic investigation from Command Center UI UI path"
            mode = "deterministic"
            max_steps = 8
        }
        $investigation | ConvertTo-Json -Depth 20
        $plan = HttpJson POST "http://localhost:$Port/api/remediation/recommender/plans" @{
            trigger_type = "investigation"
            trigger_id = $investigation.investigation_id
            service = "catalogue"
            namespace = "cascade-targets"
            objective = "Demo remediation plan for dry-run only"
            preferred_action_type = "investigate_only"
        }
        $approval = HttpJson POST "http://localhost:$Port/api/remediation/approval/approvals" @{
            plan_id = $plan.plan_id
            decision = "approved"
            approver = "demo-operator"
            approver_role = "developer"
            reason = "Approved for dry-run validation only"
            expires_minutes = 30
        }
        HttpJson POST "http://localhost:$Port/api/remediation/executor/executions/dry-run" @{
            plan_id = $plan.plan_id
            approval_id = $approval.approval.approval_id
        } | ConvertTo-Json -Depth 20
    }

    Write-Section "Open UI"
    Write-Host "Dashboard: http://localhost:$Port/"
    Write-Host "System: http://localhost:$Port/system"
    Write-Host "Telemetry: http://localhost:$Port/telemetry"
    Write-Host "Anomalies: http://localhost:$Port/anomalies"
    Write-Host "Investigations: http://localhost:$Port/investigations"
    Write-Host "Chaos: http://localhost:$Port/chaos"
    Write-Host "Remediation: http://localhost:$Port/remediation"
    if (-not $NoBrowser) {
        Start-Process "http://localhost:$Port"
    }
    Write-Host "Press Ctrl+C to stop this demo. The port-forward process id is $($PortForward.Id)."
} finally {
    if ($NoBrowser -and $null -ne $PortForward -and -not $PortForward.HasExited) {
        Stop-Process -Id $PortForward.Id -Force
    }
}
