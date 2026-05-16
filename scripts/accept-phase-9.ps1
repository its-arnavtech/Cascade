param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [string]$TargetService = "recommendationservice",
    [switch]$SkipFrontendBuild
)

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
function Get-FreePort { $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); $l.Start(); try { return $l.LocalEndpoint.Port } finally { $l.Stop() } }
function Test-Deployment {
    param([string]$Name)
    $d = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json")
    if ($null -eq $d) { Add-Fail "Deployment $Name missing"; return $false }
    $a = [int]$d.status.availableReplicas
    $r = [int]$d.spec.replicas
    if ($r -gt 0 -and $a -ge $r) { Add-Pass "Deployment $Name available"; return $true }
    Add-Fail "Deployment $Name not available ($a/$r)"
    return $false
}
function Test-Endpoints {
    param([string]$Name)
    $slices = Get-KubectlJson @("-n", $Namespace, "get", "endpointslice", "-l", "kubernetes.io/service-name=$Name", "-o", "json")
    if ($null -ne $slices) {
        foreach ($slice in @($slices.items)) {
            foreach ($endpoint in @($slice.endpoints)) {
                if (@($endpoint.addresses).Count -ge 1 -and (($endpoint.conditions.ready -eq $true) -or ($null -eq $endpoint.conditions.ready))) {
                    Add-Pass "Service $Name has endpoints"
                    return $true
                }
            }
        }
    }
    Add-Fail "Service $Name has no endpoints"
    return $false
}
function Start-PF {
    param([string]$Service, [int]$RemotePort)
    $localPort = Get-FreePort
    $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", "$localPort`:$RemotePort") -WindowStyle Hidden -PassThru
    $script:PortForwards.Add($p) | Out-Null
    Start-Sleep -Seconds 3
    if ($p.HasExited) { Add-Fail "port-forward for svc/$Service exited early"; return $null }
    return [pscustomobject]@{ Process = $p; Port = $localPort; BaseUrl = "http://localhost:$localPort" }
}
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson {
    param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 8)
    for ($i = 1; $i -le $Retries; $i++) {
        try {
            if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 90 }
            return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 120
        } catch { Start-Sleep -Seconds 2 }
    }
    return $null
}
function HttpStatus {
    param([string]$Method, [string]$Url, [object]$Body = $null)
    try {
        if ($null -eq $Body) {
            Invoke-WebRequest -Method $Method -Uri $Url -UseBasicParsing -TimeoutSec 30 | Out-Null
        } else {
            Invoke-WebRequest -Method $Method -Uri $Url -UseBasicParsing -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 30 | Out-Null
        }
        return 200
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}
function HttpText { param([string]$Url) try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30 } catch { return $null } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if (-not $pod) { return "" }; (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text.Trim() }
function Write-Phase9Debug {
    Write-Section "Phase 9 Debug Output"
    kubectl -n $Namespace get deploy,svc,endpoints,pods | Select-String command-center
    kubectl -n $Namespace describe deployment command-center-api
    kubectl -n $Namespace describe deployment command-center
    kubectl -n $Namespace logs deployment/command-center-api --tail=100
    kubectl -n $Namespace logs deployment/command-center --tail=100
}

try {
    Write-Section "Phase 9 Acceptance"
    $api = Invoke-Kubectl @("version", "--request-timeout=5s")
    if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unreachable"; throw "No cluster" }

    Write-Section "A. Phase 8 Baseline"
    foreach ($d in @("redpanda", "clickhouse", "qdrant", "retrieval-service", "knowledge-retrieval-service", "agent-tool-gateway", "agent-orchestrator-service", "chaos-planner-service", "chaos-executor-service", "remediation-recommender-service", "approval-service", "remediation-executor-service")) { Test-Deployment $d | Out-Null }
    $tables = CH "SHOW TABLES FROM cascade"
    foreach ($t in @("telemetry_events", "experiment_events", "anomaly_events", "investigation_runs", "chaos_experiment_runs", "remediation_plans", "remediation_approvals", "remediation_executions")) {
        if ($tables -match "(?m)^$t$") { Add-Pass "ClickHouse table $t exists" } else { Add-Fail "ClickHouse table $t missing" }
    }
    foreach ($topic in @("telemetry.raw", "telemetry.enriched", "experiments.events", "anomalies.detected", "agent.investigations", "chaos.experiments", "remediation.actions")) {
        $topicCheck = Test-CascadeRedpandaTopic -Namespace $Namespace -Topic $topic
        if ($topicCheck.Exists) { Add-Pass "$topic topic exists" } else { Add-Fail "$topic topic missing. Raw topic list: $($topicCheck.Raw)" }
    }

    Write-Section "B. UI Resources"
    foreach ($d in @("command-center-api", "command-center")) { Test-Deployment $d | Out-Null; Test-Endpoints $d | Out-Null }

    Write-Section "C. Command Center API"
    $apiPf = Start-PF "command-center-api" 8031
    if ($null -ne $apiPf) {
        $health = HttpJson GET "$($apiPf.BaseUrl)/health"
        if ($health.status -eq "ok") { Add-Pass "command-center-api /health works" } else { Add-Fail "command-center-api /health failed" }
        $ready = HttpJson GET "$($apiPf.BaseUrl)/ready"
        if ($ready.service -eq "command-center-api") { Add-Pass "command-center-api /ready works" } else { Add-Fail "command-center-api /ready failed" }
    }
    Stop-PF

    Write-Section "D. Static UI And API Proxy"
    $uiPf = Start-PF "command-center" 8030
    if ($null -eq $uiPf) { throw "Unable to port-forward command-center" }
    $base = $uiPf.BaseUrl
    $html = HttpText "$base/"
    if ($null -ne $html -and $html.Content -match '<div id="root"') { Add-Pass "GET / returns command center HTML" } else { Add-Fail "GET / did not return expected HTML" }
    $assetPath = if ($null -ne $html) { [regex]::Match([string]$html.Content, 'src="([^"]+\.js)"').Groups[1].Value } else { "" }
    if ($assetPath) {
        $asset = HttpText "$base$assetPath"
        if ($null -ne $asset -and $asset.StatusCode -eq 200) { Add-Pass "built JS asset loads" } else { Add-Fail "built JS asset missing" }
    } else { Add-Fail "index bundle path not found" }

    foreach ($check in @(
        @("/api/retrieval/health", "retrieval health"),
        @("/api/retrieval/debug/counts", "retrieval debug counts"),
        @("/api/knowledge/knowledge/stats", "knowledge stats"),
        @("/api/agent/agents/status", "agent status"),
        @("/api/chaos/planner/health", "chaos planner health"),
        @("/api/chaos/executor/safety/policy", "chaos executor safety policy"),
        @("/api/remediation/recommender/health", "remediation recommender health"),
        @("/api/remediation/executor/safety/policy", "remediation executor safety policy")
    )) {
        $result = HttpJson GET "$base$($check[0])"
        if ($null -ne $result) { Add-Pass "$($check[1]) works through proxy" } else { Add-Fail "$($check[1]) failed through proxy" }
    }

    Write-Section "E. Safe Action Integration"
    $investigation = HttpJson POST "$base/api/agent/investigations" @{
        trigger_type = "manual"
        service = $TargetService
        namespace = $TargetNamespace
        objective = "Phase 9 acceptance deterministic investigation"
        mode = "deterministic"
        max_steps = 8
    }
    if ($investigation.investigation_id -and $investigation.status -eq "completed") { Add-Pass "create investigation through UI API succeeds" } else { Add-Fail "create investigation through UI API failed" }

    $remPlan = HttpJson POST "$base/api/remediation/recommender/plans" @{
        trigger_type = "investigation"
        trigger_id = $investigation.investigation_id
        service = $TargetService
        namespace = $TargetNamespace
        objective = "Phase 9 acceptance remediation plan"
        preferred_action_type = "investigate_only"
    }
    if ($remPlan.plan_id) { Add-Pass "create remediation plan through proxy succeeds" } else { Add-Fail "create remediation plan failed" }
    $approval = HttpJson POST "$base/api/remediation/approval/approvals" @{
        plan_id = $remPlan.plan_id
        decision = "approved"
        approver = "phase9-acceptance"
        approver_role = "developer"
        reason = "Dry-run validation acceptance"
        expires_minutes = 60
    }
    if ($approval.approval.approval_id) { Add-Pass "approval record through proxy succeeds" } else { Add-Fail "approval record failed" }
    $dryRem = HttpJson POST "$base/api/remediation/executor/executions/dry-run" @{
        plan_id = $remPlan.plan_id
        approval_id = $approval.approval.approval_id
    }
    if ($dryRem.execution.dry_run -eq $true -and $dryRem.execution.executed -eq $false) { Add-Pass "dry-run remediation validation succeeds without execution" } else { Add-Fail "dry-run remediation validation failed" }
    $realRemStatus = HttpStatus POST "$base/api/remediation/executor/executions" @{ plan_id = $remPlan.plan_id; approval_id = $approval.approval.approval_id }
    if ($realRemStatus -eq 403) { Add-Pass "real remediation execution blocked by command center proxy" } else { Add-Fail "real remediation execution was not blocked (HTTP $realRemStatus)" }

    $chaosPlan = HttpJson POST "$base/api/chaos/planner/plans" @{
        objective = "Phase 9 acceptance chaos dry-run plan"
        target_service = $TargetService
        target_namespace = $TargetNamespace
        experiment_kind = "pod_kill"
        duration_seconds = 30
        dry_run = $true
    }
    if ($chaosPlan.plan_id) { Add-Pass "create chaos dry-run plan through proxy succeeds" } else { Add-Fail "create chaos dry-run plan failed" }
    $chaosRun = HttpJson POST "$base/api/chaos/executor/runs" @{
        plan_id = $chaosPlan.plan_id
        approved = $false
        dry_run = $true
        observation_window_seconds = 10
        trigger_agent_investigation = $false
    }
    if ($chaosRun.dry_run -eq $true -and $chaosRun.status -eq "dry_run") { Add-Pass "chaos dry-run execution succeeds without real execution" } else { Add-Fail "chaos dry-run execution failed" }
    $realChaosStatus = HttpStatus POST "$base/api/chaos/executor/runs" @{ plan_id = $chaosPlan.plan_id; approved = $true; dry_run = $false; observation_window_seconds = 5 }
    if ($realChaosStatus -eq 403) { Add-Pass "real chaos execution blocked by command center proxy" } else { Add-Fail "real chaos execution was not blocked (HTTP $realChaosStatus)" }

    Write-Section "F. Frontend Build"
    if (-not $SkipFrontendBuild) {
        Push-Location web\command-center
        npm run build
        if ($LASTEXITCODE -eq 0) { Add-Pass "npm run build passes" } else { Add-Fail "npm run build failed" }
        Pop-Location
    } else {
        Add-Warn "Skipped frontend build by flag"
    }
} catch {
    Add-Warn "Acceptance stopped early: $($_.Exception.Message)"
} finally {
    Stop-PF
}

if ($Failed.Count -gt 0) {
    try { Write-Phase9Debug } catch { Add-Warn "Failed to collect debug output: $($_.Exception.Message)" }
}

Write-Section "Final Result"
Write-Host "Passed:"; if ($Passed.Count -eq 0) { Write-Host "  - none" } else { foreach ($p in $Passed) { Write-Host "  - $p" } }
Write-Host ""; Write-Host "Warnings:"; if ($Warnings.Count -eq 0) { Write-Host "  - none" } else { foreach ($w in $Warnings) { Write-Host "  - $w" } }
Write-Host ""; Write-Host "Failed:"; if ($Failed.Count -eq 0) { Write-Host "  - none" } else { foreach ($f in $Failed) { Write-Host "  - $f" } }
Write-Host ""
if ($Failed.Count -eq 0) { Write-Host "PHASE 9 ACCEPTANCE: PASS"; exit 0 }
Write-Host "PHASE 9 ACCEPTANCE: FAIL"
exit 1
