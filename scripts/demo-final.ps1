param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [string]$TargetService = "catalogue",
    [int]$Port = 18300,
    [switch]$RunAcceptAll,
    [switch]$SkipTargetValidation,
    [switch]$NoPortForward
)

$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputRoot = Join-Path $Root "run-output\final-demo"
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$OutputDir = Join-Path $OutputRoot $Timestamp
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$Passed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "============================================================"
}
function Add-Pass { param([string]$Message) $script:Passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Warn { param([string]$Message) $script:Warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Add-Fail { param([string]$Message) $script:Failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Invoke-Kubectl {
    param([string[]]$Arguments)
    $output = & kubectl @Arguments 2>&1
    [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE }
}
function Get-KubectlJson {
    param([string[]]$Arguments)
    $result = Invoke-Kubectl $Arguments
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.Text)) { return $null }
    try { return $result.Text | ConvertFrom-Json } catch { return $null }
}
function Test-Rollout {
    param([string]$Deployment)
    $result = Invoke-Kubectl @("-n", $Namespace, "rollout", "status", "deployment/$Deployment", "--timeout=5s")
    if ($result.ExitCode -eq 0) { Add-Pass "deployment/$Deployment is rolled out"; return }
    Add-Fail "deployment/$Deployment is not rolled out"
}
function Test-ServiceEndpoints {
    param([string]$Service)
    $svc = Get-KubectlJson @("-n", $Namespace, "get", "service", $Service, "-o", "json")
    if ($null -eq $svc) { Add-Fail "svc/$Service is missing"; return }
    $slices = Get-KubectlJson @("-n", $Namespace, "get", "endpointslice", "-l", "kubernetes.io/service-name=$Service", "-o", "json")
    if ($null -eq $slices) { Add-Fail "svc/$Service has no EndpointSlice"; return }
    foreach ($slice in @($slices.items)) {
        foreach ($endpoint in @($slice.endpoints)) {
            if (@($endpoint.addresses).Count -gt 0 -and (($endpoint.conditions.ready -eq $true) -or ($null -eq $endpoint.conditions.ready))) {
                Add-Pass "svc/$Service has ready endpoints"
                return
            }
        }
    }
    Add-Fail "svc/$Service has no ready endpoints"
}
function Test-JsonCount {
    param([object]$Payload, [string]$Property, [string]$PassMessage, [string]$WarnMessage)
    if ($null -ne $Payload -and $null -ne $Payload.$Property -and [int]$Payload.$Property -gt 0) { Add-Pass $PassMessage; return }
    Add-Warn $WarnMessage
}
function Get-HttpJson {
    param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 6)
    for ($i = 1; $i -le $Retries; $i++) {
        try {
            if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 60 }
            return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 120
        } catch {
            if ($i -eq $Retries) { return $null }
            Start-Sleep -Seconds 2
        }
    }
    return $null
}
function Get-HttpText {
    param([string]$Url)
    try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30 } catch { return $null }
}
function Test-PortOpen {
    param([int]$LocalPort)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.BeginConnect("127.0.0.1", $LocalPort, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne(300)) { return $false }
        $client.EndConnect($connect)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}
function Start-CommandCenterPortForward {
    if ($NoPortForward) {
        if (Test-PortOpen $Port) { Add-Pass "Command Center already reachable on localhost:$Port"; return }
        Add-Fail "NoPortForward was set but localhost:$Port is not reachable"
        return
    }
    if (Test-PortOpen $Port) {
        Add-Warn "localhost:$Port is already in use; reusing it for Command Center checks"
        return
    }
    $out = Join-Path $OutputDir "command-center-port-forward.out.log"
    $err = Join-Path $OutputDir "command-center-port-forward.err.log"
    $process = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/command-center", "$Port`:8030") -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    $script:PortForwards.Add($process) | Out-Null
    Start-Sleep -Seconds 3
    if ($process.HasExited) { Add-Fail "Command Center port-forward exited early; see $err"; return }
    if (Test-PortOpen $Port) { Add-Pass "Command Center port-forward started on localhost:$Port" } else { Add-Fail "Command Center port-forward did not open localhost:$Port" }
}
function Stop-PortForwards {
    foreach ($process in $script:PortForwards) {
        if ($null -ne $process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    }
}
function Test-Api {
    param([string]$Path, [string]$Label)
    $payload = Get-HttpJson GET "$BaseUrl$Path"
    if ($null -ne $payload) { Add-Pass "$Label reachable"; return $payload }
    Add-Fail "$Label not reachable at $Path"
    return $null
}

Set-Location $Root

try {
    Write-Section "Cascade Final Demo Verification"
    Write-Host "Output folder: $OutputDir"
    Write-Host "Safety: this script only runs read-only checks and dry-run chaos/remediation/Autopilot actions."
    Write-Host "It does not enable live chaos, live remediation, or production execution modes."

    Write-Section "1. Local Prerequisites"
    foreach ($tool in @("kubectl", "python", "npm")) {
        $command = Get-Command $tool -ErrorAction SilentlyContinue
        if ($null -ne $command) { Add-Pass "$tool is available" } else { Add-Fail "$tool is not available on PATH" }
    }
    $kubectl = Invoke-Kubectl @("version", "--request-timeout=5s")
    if ($kubectl.ExitCode -eq 0) { Add-Pass "Kubernetes API is reachable" } else { Add-Fail "Kubernetes API is not reachable" }
    $context = (Invoke-Kubectl @("config", "current-context")).Text.Trim()
    if ($context) {
        if ($context -match "kind") { Add-Pass "kubectl context is kind-like: $context" } else { Add-Warn "kubectl context is '$context'; final demo is safest on local kind" }
    } else {
        Add-Fail "kubectl context is unavailable"
    }

    Write-Section "2. Platform Manifests And Services"
    $ns = Get-KubectlJson @("get", "namespace", $Namespace, "-o", "json")
    if ($null -ne $ns) { Add-Pass "namespace/$Namespace exists" } else { Add-Fail "namespace/$Namespace is missing; run .\scripts\deploy.ps1" }
    $requiredDeployments = @(
        "command-center-api",
        "command-center",
        "topology-service",
        "observation-service",
        "retrieval-service",
        "feature-extractor-service",
        "anomaly-detector-service",
        "telemetry-archiver",
        "stream-enricher",
        "knowledge-retrieval-service",
        "agent-tool-gateway",
        "agent-orchestrator-service",
        "chaos-planner-service",
        "chaos-executor-service",
        "remediation-recommender-service",
        "approval-service",
        "remediation-executor-service",
        "autopilot-service",
        "scheduler-service",
        "experiment-tracker-service",
        "clickhouse",
        "redpanda",
        "qdrant"
    )
    foreach ($deployment in $requiredDeployments) { Test-Rollout $deployment }
    foreach ($service in $requiredDeployments) { Test-ServiceEndpoints $service }

    Write-Section "3. Target Workload"
    $targetNs = Get-KubectlJson @("get", "namespace", $TargetNamespace, "-o", "json")
    if ($null -ne $targetNs) { Add-Pass "namespace/$TargetNamespace exists" } else { Add-Fail "namespace/$TargetNamespace is missing; run .\scripts\deploy-targets.ps1 or deploy your target" }
    $label = ""
    if ($null -ne $targetNs.metadata.labels) { $label = $targetNs.metadata.labels."cascade.io/monitored" }
    if ($label -eq "true") { Add-Pass "namespace/$TargetNamespace has cascade.io/monitored=true" } else { Add-Warn "namespace/$TargetNamespace is not labeled cascade.io/monitored=true" }
    $targetSvc = Get-KubectlJson @("-n", $TargetNamespace, "get", "service", $TargetService, "-o", "json")
    if ($null -ne $targetSvc) { Add-Pass "target service $TargetNamespace/$TargetService exists" } else { Add-Fail "target service $TargetNamespace/$TargetService is missing" }
    if (-not $SkipTargetValidation -and (Test-Path ".\scripts\validate-target.ps1")) {
        & powershell -ExecutionPolicy Bypass -File ".\scripts\validate-target.ps1" -Namespace $TargetNamespace -ExpectedServices $TargetService -ShowLabels
        if ($LASTEXITCODE -eq 0) { Add-Pass "validate-target.ps1 completed for $TargetNamespace" } else { Add-Warn "validate-target.ps1 reported target readiness issues" }
    }

    Write-Section "4. Optional Broad Acceptance"
    if ($RunAcceptAll) {
        & powershell -ExecutionPolicy Bypass -File ".\scripts\accept-all.ps1"
        if ($LASTEXITCODE -eq 0) { Add-Pass "accept-all.ps1 passed" } else { Add-Fail "accept-all.ps1 failed" }
    } else {
        Add-Warn "Skipped accept-all.ps1; run with -RunAcceptAll for the full local acceptance suite"
    }

    Write-Section "5. Command Center Access"
    Start-CommandCenterPortForward
    $BaseUrl = "http://localhost:$Port"
    $html = Get-HttpText "$BaseUrl/"
    if ($null -ne $html -and $html.Content -match '<div id="root"') { Add-Pass "Command Center frontend is reachable" } else { Add-Fail "Command Center frontend did not return the expected app shell" }
    $liveDemo = Test-Api "/api/live-demo/status" "live-demo status"
    if ($null -ne $liveDemo) {
        if ($liveDemo.real_chaos_enabled -or $liveDemo.real_remediation_enabled) { Add-Fail "live execution appears enabled; final demo must stay dry-run by default" } else { Add-Pass "live chaos/remediation are not enabled" }
    }
    Test-Api "/api/retrieval/health" "retrieval health" | Out-Null
    Test-Api "/api/retrieval/debug/counts" "retrieval counts" | Out-Null
    Test-Api "/api/contracts" "contract registry" | Out-Null
    Test-Api "/api/scheduler/scheduler/status" "scheduler status" | Out-Null

    Write-Section "6. Telemetry, Topology, RCA"
    $counts = Get-HttpJson GET "$BaseUrl/api/retrieval/debug/counts"
    if ($null -ne $counts) {
        foreach ($name in @("telemetry_events", "anomaly_events", "rca_reports", "topology_snapshots")) {
            if ($null -ne $counts.$name -and [int]$counts.$name -gt 0) { Add-Pass "$name has stored records" } else { Add-Warn "$name has no stored records yet" }
        }
    }
    $topologyRefresh = Get-HttpJson POST "$BaseUrl/api/topology/topology/refresh" @{}
    if ($null -ne $topologyRefresh) { Add-Pass "topology refresh completed through Command Center API" } else { Add-Warn "topology refresh was unavailable through Command Center API" }
    $graph = Get-HttpJson GET "$BaseUrl/api/topology/topology/graph"
    if ($null -ne $graph -and @($graph.nodes).Count -gt 0) { Add-Pass "topology graph returns nodes" } else { Add-Warn "topology graph returned no nodes" }
    $rca = Get-HttpJson POST "$BaseUrl/api/causality/rca/analyze" @{ service = $TargetService; namespace = $TargetNamespace; lookback_minutes = 30 }
    if ($null -eq $rca) { $rca = Get-HttpJson POST "$BaseUrl/api/causality/causality/analyze" @{ service = $TargetService; namespace = $TargetNamespace; lookback_minutes = 30 } }
    if ($null -ne $rca) { Add-Pass "RCA/causality analysis endpoint responds" } else { Add-Warn "RCA/causality analysis endpoint did not return a report" }

    Write-Section "7. Safe Dry-Run Actions"
    $campaign = Get-HttpJson POST "$BaseUrl/api/chaos/planner/campaigns" @{
        name = "Final demo dry-run campaign"
        target_namespace = $TargetNamespace
        allowed_services = @($TargetService)
        experiment_templates = @(@{
            name = "dry-run pod kill $TargetService"
            experiment_kind = "pod_kill"
            target_service = $TargetService
            duration_seconds = 10
            dry_run = $true
        })
        schedule = @{ trigger = "manual" }
        max_experiments_per_run = 1
        blast_radius_limit = 0.5
        cooldown_seconds = 0
        dry_run = $true
        local_demo_execution_enabled = $false
    }
    $campaignId = ""
    if ($null -ne $campaign -and $campaign.campaign.campaign_id) {
        $campaignId = $campaign.campaign.campaign_id
        Add-Pass "dry-run chaos campaign created"
        $campaignRun = Get-HttpJson POST "$BaseUrl/api/chaos/planner/campaigns/$campaignId/start" @{ dry_run = $true; requested_by = "demo-final"; observation_window_seconds = 10; trigger_agent_investigation = $false }
        if ($null -ne $campaignRun -and $campaignRun.run.dry_run -eq $true) { Add-Pass "dry-run chaos campaign run completed without live execution" } else { Add-Warn "dry-run chaos campaign run did not return expected dry_run=true" }
    } else {
        Add-Warn "dry-run chaos campaign could not be created"
    }

    $auto = Get-HttpJson POST "$BaseUrl/api/autopilot/runs" @{
        trigger_type = "manual"
        service = $TargetService
        namespace = $TargetNamespace
        objective = "Final demo dry-run Autopilot workflow"
        mode = "dry_run"
        preferred_action_type = "investigate_only"
    }
    if ($null -ne $auto -and $auto.run.run_id) { Add-Pass "Autopilot dry-run completed with run $($auto.run.run_id)" } else { Add-Warn "Autopilot dry-run did not return a run id" }

    $plan = Get-HttpJson POST "$BaseUrl/api/remediation/recommender/plans" @{
        trigger_type = "manual"
        trigger_id = "demo-final"
        service = $TargetService
        namespace = $TargetNamespace
        objective = "Final demo remediation dry-run"
        preferred_action_type = "investigate_only"
    }
    if ($null -ne $plan -and $plan.plan_id) {
        Add-Pass "remediation plan created"
        $approval = Get-HttpJson POST "$BaseUrl/api/remediation/approval/approvals" @{
            plan_id = $plan.plan_id
            decision = "approved"
            approver = "demo-final"
            approver_role = "developer"
            reason = "Dry-run final demo validation"
            expires_minutes = 60
        }
        if ($null -ne $approval -and $approval.approval.approval_id) { Add-Pass "plan-bound approval record created" } else { Add-Warn "approval record was not created" }
        $approvalId = if ($null -ne $approval) { $approval.approval.approval_id } else { "" }
        $execution = Get-HttpJson POST "$BaseUrl/api/remediation/executor/executions/dry-run" @{ plan_id = $plan.plan_id; approval_id = $approvalId }
        if ($null -ne $execution -and $execution.execution.dry_run -eq $true -and $execution.execution.executed -eq $false) {
            Add-Pass "remediation dry-run completed without mutation"
        } else {
            Add-Warn "remediation dry-run did not return expected non-mutating execution"
        }
    } else {
        Add-Warn "remediation plan could not be created"
    }

    Write-Section "8. History And Evidence Records"
    Start-Sleep -Seconds 2
    $plans = Get-HttpJson GET "$BaseUrl/api/remediation/recommender/plans?limit=10"
    Test-JsonCount $plans "count" "remediation plans are queryable" "no remediation plans found after dry-run creation"
    $executions = Get-HttpJson GET "$BaseUrl/api/remediation/executor/executions?limit=10"
    Test-JsonCount $executions "count" "remediation executions are queryable" "no remediation executions found after dry-run execution"
    $campaigns = Get-HttpJson GET "$BaseUrl/api/chaos/planner/campaigns?limit=10"
    Test-JsonCount $campaigns "count" "chaos campaigns are queryable" "no chaos campaigns found after dry-run creation"
    $campaignRuns = Get-HttpJson GET "$BaseUrl/api/chaos/planner/campaign-runs?limit=10"
    Test-JsonCount $campaignRuns "count" "chaos campaign runs are queryable" "no chaos campaign runs found after dry-run start"
    $autopilotRuns = Get-HttpJson GET "$BaseUrl/api/autopilot/runs?limit=10"
    Test-JsonCount $autopilotRuns "count" "Autopilot runs are queryable" "no Autopilot runs found after dry-run run"
    $audit = Get-HttpJson GET "$BaseUrl/api/retrieval/audit/events?limit=10"
    Test-JsonCount $audit "count" "audit timeline has recent events" "audit timeline has no recent events"
    $schedulerHistory = Get-HttpJson GET "$BaseUrl/api/scheduler/scheduler/history?limit=10"
    if ($null -ne $schedulerHistory) { Add-Pass "scheduler history endpoint responds" } else { Add-Warn "scheduler history endpoint did not respond" }
    $verifications = Get-HttpJson GET "$BaseUrl/api/remediation/executor/verifications?limit=10"
    Test-JsonCount $verifications "count" "verification records exist" "no verification records found; dry-run-only demos may not create post-remediation verification"
    $rollbacks = Get-HttpJson GET "$BaseUrl/api/remediation/executor/rollback-plans?limit=10"
    Test-JsonCount $rollbacks "count" "rollback plan records exist" "no rollback plan records found; dry-run-only demos may not create executable rollback records"

    Write-Section "9. Command Center Pages"
    $pages = @(
        "/overview",
        "/topology",
        "/causality",
        "/chaos",
        "/autopilot",
        "/remediation",
        "/scheduler",
        "/audit",
        "/system",
        "/about"
    )
    foreach ($page in $pages) {
        $response = Get-HttpText "$BaseUrl$page"
        if ($null -ne $response -and $response.StatusCode -eq 200) { Add-Pass "page $page returns HTTP 200" } else { Add-Fail "page $page is not reachable" }
    }

    Write-Section "10. Presenter URLs And Expected Notes"
    Write-Host "Command Center: $BaseUrl"
    Write-Host "Overview:       $BaseUrl/overview"
    Write-Host "Topology:       $BaseUrl/topology"
    Write-Host "Causality/RCA:  $BaseUrl/causality"
    Write-Host "Chaos:          $BaseUrl/chaos"
    Write-Host "Autopilot:      $BaseUrl/autopilot"
    Write-Host "Remediation:    $BaseUrl/remediation"
    Write-Host "Scheduler:      $BaseUrl/scheduler"
    Write-Host "Audit:          $BaseUrl/audit"
    Write-Host "System/API:     $BaseUrl/system"
    Write-Host ""
    Write-Host "Expected warnings can include Prometheus raw query fallback, insufficient RED/RCA data on fresh clusters,"
    Write-Host "and no live verification or rollback records when only dry-run workflows have been executed."
    Write-Host "Use .\scripts\demo-command-center.ps1 -Stage All for the presenter stage flow."
} finally {
    Stop-PortForwards
}

Write-Section "Final PASS/WARN/FAIL Summary"
Write-Host "Passed:"
if ($Passed.Count -eq 0) { Write-Host "  - none" } else { foreach ($item in $Passed) { Write-Host "  - $item" } }
Write-Host ""
Write-Host "Warnings:"
if ($Warnings.Count -eq 0) { Write-Host "  - none" } else { foreach ($item in $Warnings) { Write-Host "  - $item" } }
Write-Host ""
Write-Host "Failed:"
if ($Failed.Count -eq 0) { Write-Host "  - none" } else { foreach ($item in $Failed) { Write-Host "  - $item" } }
Write-Host ""
Write-Host "Artifacts: $OutputDir"

if ($Failed.Count -eq 0) {
    Write-Host "CASCADE FINAL DEMO: PASS"
    exit 0
}
Write-Host "CASCADE FINAL DEMO: FAIL"
exit 1
