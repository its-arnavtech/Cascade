param([string]$Namespace = "cascade-system")

$ErrorActionPreference = "Continue"
$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
. "$PSScriptRoot\lib\kafka-topics.ps1"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Add-Pass { param([string]$Message) $script:Passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Fail { param([string]$Message) $script:Failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Add-Warn { param([string]$Message) $script:Warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Get-KubectlJson { param([string[]]$Arguments) $r = Invoke-Kubectl $Arguments; if ($r.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($r.Text)) { return $null }; try { $r.Text | ConvertFrom-Json } catch { return $null } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 8) for ($i = 1; $i -le $Retries; $i++) { try { if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 180 } return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 40) -TimeoutSec 180 } catch { Start-Sleep -Seconds 2 } }; return $null }
function Test-Deployment { param([string]$Name) $d = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json"); if ($null -eq $d) { Add-Fail "Deployment $Name missing"; return }; $a = [int]$d.status.availableReplicas; $r = [int]$d.spec.replicas; if ($r -gt 0 -and $a -ge $r) { Add-Pass "Deployment $Name available" } else { Add-Fail "Deployment $Name not available ($a/$r)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if (-not $pod) { return "" }; (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text.Trim() }

try {
    Write-Section "Agent investigations Acceptance"
    $api = Invoke-Kubectl @("version", "--request-timeout=5s"); if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unreachable"; throw "No cluster" }
    foreach ($d in @("redpanda", "clickhouse", "qdrant", "retrieval-service", "knowledge-ingestion-service", "knowledge-retrieval-service", "feature-extractor-service", "anomaly-detector-service", "agent-tool-gateway", "agent-orchestrator-service")) { Test-Deployment $d }

    foreach ($t in @("knowledge_documents", "knowledge_chunks", "knowledge_ingestion_runs", "knowledge_queries", "investigation_runs", "agent_steps", "investigation_reports", "agent_tool_calls")) {
        $tables = CH "SHOW TABLES FROM cascade"
        if ($tables -match "(?m)^$t$") { Add-Pass "ClickHouse table $t exists" } else { Add-Fail "ClickHouse table $t missing" }
    }
    try { [void][int](CH "SELECT count() FROM cascade.anomaly_events"); Add-Pass "anomaly_events is queryable" } catch { Add-Fail "anomaly_events is not queryable" }
    if ([int](CH "SELECT count() FROM cascade.knowledge_chunks") -gt 0) { Add-Pass "knowledge_chunks has rows" } else { Add-Fail "knowledge_chunks empty" }

    $topicCheck = Test-CascadeRedpandaTopic -Namespace $Namespace -Topic "agent.investigations"
    if ($topicCheck.Exists) { Add-Pass "agent.investigations topic exists" } else { Add-Fail "agent.investigations topic missing. Raw topic list: $($topicCheck.Raw)" }

    Start-PF "agent-tool-gateway" "8017:8017"
    Start-PF "agent-orchestrator-service" "8018:8018"
    try {
        $gatewayReady = HttpJson GET "http://localhost:8017/ready"
        if ($gatewayReady.service -eq "agent-tool-gateway") { Add-Pass "agent-tool-gateway ready" } else { Add-Fail "agent-tool-gateway not ready" }
        $orchReady = HttpJson GET "http://localhost:8018/ready"
        if ($orchReady.service -eq "agent-orchestrator-service") { Add-Pass "agent-orchestrator-service ready" } else { Add-Fail "agent-orchestrator-service not ready" }

        $tools = HttpJson GET "http://localhost:8017/tools"
        foreach ($tool in @("get_recent_anomalies", "get_recent_events", "search_knowledge", "get_service_impact", "search_similar_incidents")) {
            if (($tools.tools | Where-Object { $_.name -eq $tool })) { Add-Pass "/tools includes $tool" } else { Add-Fail "/tools missing $tool" }
        }
        $status = HttpJson GET "http://localhost:8018/agents/status"
        if ($status.deterministic_planner_available -eq $true -and $status.configured_mode -eq "deterministic") { Add-Pass "/agents/status reports deterministic mode" } else { Add-Fail "/agents/status invalid" }

        $toolChecks = @(
            @{ Name = "get_recent_anomalies"; Body = @{ limit = 3 } },
            @{ Name = "get_recent_events"; Body = @{ limit = 3 } },
            @{ Name = "search_knowledge"; Body = @{ query = "pod restart unhealthy service anomaly"; limit = 3; filters = @{} } },
            @{ Name = "get_service_impact"; Body = @{ root_service = "catalogue" } },
            @{ Name = "search_similar_incidents"; Body = @{ query = "restart anomaly"; limit = 3; service = "catalogue" } }
        )
        foreach ($check in $toolChecks) {
            $result = HttpJson POST "http://localhost:8017/tools/$($check.Name)" $check.Body
            if ($result.tool_name -eq $check.Name -and $result.status -eq "ok") { Add-Pass "tool $($check.Name) returns normalized response" } else { Add-Fail "tool $($check.Name) failed" }
        }

        $investigation = HttpJson POST "http://localhost:8018/investigations" @{
            trigger_type = "service"
            service = "catalogue"
            namespace = "cascade-targets"
            objective = "Investigate catalogue restart anomaly using stored Cascade evidence"
            mode = "deterministic"
            max_steps = 12
        } 1
        if ($investigation.status -eq "completed" -and $investigation.investigation_id -and $investigation.report_id) { Add-Pass "investigation completes successfully" } else { Add-Fail "investigation did not complete" }
        $investigationId = $investigation.investigation_id
        $detail = HttpJson GET "http://localhost:8018/investigations/$investigationId"
        $report = HttpJson GET "http://localhost:8018/investigations/$investigationId/report"
        if ($detail.steps.Count -gt 0) { Add-Pass "GET /investigations/{id} returns steps" } else { Add-Fail "investigation detail missing steps" }
        if ($report.evidence_json -or $report.evidence.Count -gt 0) { Add-Pass "report contains evidence refs" } else { Add-Fail "report missing evidence" }
        if ($report.confidence -ge 0) { Add-Pass "report contains confidence" } else { Add-Fail "report missing confidence" }
        $reportJson = $report | ConvertTo-Json -Depth 80
        if ($reportJson -match "SUGGESTION ONLY" -and $reportJson -notmatch "executed") { Add-Pass "suggested remediation is text-only" } else { Add-Fail "suggested remediation boundary unclear" }

        if ([int](CH "SELECT count() FROM cascade.investigation_runs WHERE investigation_id = '$investigationId'") -gt 0) { Add-Pass "investigation_runs row inserted" } else { Add-Fail "investigation_runs row missing" }
        if ([int](CH "SELECT count() FROM cascade.agent_steps WHERE investigation_id = '$investigationId'") -gt 0) { Add-Pass "agent_steps rows inserted" } else { Add-Fail "agent_steps rows missing" }
        if ([int](CH "SELECT count() FROM cascade.agent_tool_calls WHERE investigation_id = '$investigationId'") -gt 0) { Add-Pass "agent_tool_calls rows inserted" } else { Add-Fail "agent_tool_calls rows missing" }
        if ([int](CH "SELECT count() FROM cascade.investigation_reports WHERE investigation_id = '$investigationId'") -gt 0) { Add-Pass "investigation_reports row inserted" } else { Add-Fail "investigation_reports row missing" }
        $recent = HttpJson GET "http://localhost:8018/investigations?limit=5"
        if ($recent.investigations.Count -ge 1) { Add-Pass "GET /investigations returns valid JSON" } else { Add-Fail "GET /investigations invalid" }

        $events = (Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/redpanda", "--", "rpk", "topic", "consume", "agent.investigations", "--offset", "start", "--num", "12")).Text
        if ($events -match "investigation.started" -and $events -match "investigation.completed") { Add-Pass "agent.investigations contains lifecycle events" } else { Add-Fail "agent.investigations lifecycle events not observed" }
    } finally { Stop-PF }
} catch {
    Add-Warn "Acceptance stopped early: $($_.Exception.Message)"
} finally {
    Stop-PF
}

Write-Section "Final Result"
Write-Host "Passed:"; if ($Passed.Count -eq 0) { Write-Host "  - none" } else { foreach ($p in $Passed) { Write-Host "  - $p" } }
Write-Host ""; Write-Host "Warnings:"; if ($Warnings.Count -eq 0) { Write-Host "  - none" } else { foreach ($w in $Warnings) { Write-Host "  - $w" } }
Write-Host ""; Write-Host "Failed:"; if ($Failed.Count -eq 0) { Write-Host "  - none" } else { foreach ($f in $Failed) { Write-Host "  - $f" } }
Write-Host ""
if ($Failed.Count -eq 0) { Write-Host "AGENTS ACCEPTANCE: PASS"; exit 0 }
Write-Host "AGENTS ACCEPTANCE: FAIL"
exit 1
