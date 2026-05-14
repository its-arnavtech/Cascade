param([string]$Namespace = "cascade-system")

$ErrorActionPreference = "Continue"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) try { if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 30 | ConvertTo-Json -Depth 20 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20) -TimeoutSec 30 | ConvertTo-Json -Depth 20 } } catch { "ERROR: $($_.Exception.Message)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if ($pod) { (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text } }

try {
    Write-Section "Namespace Status"
    kubectl -n $Namespace get pods,deployments,svc,endpoints -o wide

    Write-Section "Recent Events"
    kubectl -n $Namespace get events --sort-by=.lastTimestamp | Select-Object -Last 40

    Write-Section "Redpanda Topics"
    kubectl -n $Namespace exec deployment/redpanda -- rpk topic list

    Write-Section "Phase 6 ClickHouse Counts"
    foreach ($table in @("investigation_runs", "agent_steps", "investigation_reports", "agent_tool_calls")) {
        Write-Host "$table = $(CH "SELECT count() FROM cascade.$table")"
    }

    Write-Section "Recent Investigation Runs"
    CH "SELECT investigation_id, status, mode, service, confidence, created_at FROM cascade.investigation_runs ORDER BY created_at DESC LIMIT 5 FORMAT PrettyCompact"

    Write-Section "Recent Agent Steps"
    CH "SELECT investigation_id, node_name, status, tool_name, created_at FROM cascade.agent_steps ORDER BY created_at DESC LIMIT 10 FORMAT PrettyCompact"

    Write-Section "Recent Tool Calls"
    CH "SELECT investigation_id, tool_name, status, latency_ms, called_at FROM cascade.agent_tool_calls ORDER BY called_at DESC LIMIT 10 FORMAT PrettyCompact"

    Write-Section "Service Logs"
    kubectl -n $Namespace logs deployment/agent-tool-gateway --tail=120
    kubectl -n $Namespace logs deployment/agent-orchestrator-service --tail=160

    Start-PF "agent-tool-gateway" "8017:8017"
    Start-PF "agent-orchestrator-service" "8018:8018"
    Write-Section "Health And Ready"
    HttpJson GET "http://localhost:8017/health"
    HttpJson GET "http://localhost:8017/ready"
    HttpJson GET "http://localhost:8018/health"
    HttpJson GET "http://localhost:8018/ready"

    Write-Section "Tools And Agent Status"
    HttpJson GET "http://localhost:8017/tools"
    HttpJson GET "http://localhost:8018/agents/status"

    Write-Section "Recent Investigations"
    HttpJson GET "http://localhost:8018/investigations?limit=3"
} finally {
    Stop-PF
}
