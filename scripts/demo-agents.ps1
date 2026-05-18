param([string]$Namespace = "cascade-system")

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 180 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 40) -TimeoutSec 180 } }

try {
    Write-Section "Agent investigations Demo - Agentic Investigation"
    Start-PF "agent-tool-gateway" "8017:8017"
    Start-PF "agent-orchestrator-service" "8018:8018"

    Write-Section "Agent Runtime Status"
    HttpJson GET "http://localhost:8018/agents/status" | ConvertTo-Json -Depth 20

    Write-Section "Tool Registry"
    $tools = HttpJson GET "http://localhost:8017/tools"
    $tools.tools | Select-Object name, target_service, read_only | Format-Table -AutoSize

    Write-Section "Start Deterministic Investigation"
    $result = HttpJson POST "http://localhost:8018/investigations" @{
        trigger_type = "service"
        service = "catalogue"
        namespace = "cascade-targets"
        objective = "Investigate catalogue restart anomaly using stored telemetry, anomalies, topology, memory, and knowledge"
        mode = "deterministic"
        max_steps = 12
    }
    $result | ConvertTo-Json -Depth 20

    Write-Section "Investigation Trace"
    $detail = HttpJson GET "http://localhost:8018/investigations/$($result.investigation_id)"
    $detail.steps | Select-Object node_name, agent_role, status, tool_name, tool_latency_ms | Format-Table -AutoSize

    Write-Section "Tool Calls"
    $detail.tool_calls | Select-Object tool_name, status, latency_ms, response_summary | Format-Table -AutoSize

    Write-Section "Final Investigation Report"
    $report = HttpJson GET "http://localhost:8018/investigations/$($result.investigation_id)/report"
    Write-Host $report.markdown_report
} finally {
    Stop-PF
}
