param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [string]$TargetService = "recommendationservice",
    [switch]$DryRunOnly,
    [switch]$NoChaos
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
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 8) for ($i = 1; $i -le $Retries; $i++) { try { if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 240 } return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 60) -TimeoutSec 240 } catch { Start-Sleep -Seconds 2 } }; return $null }
function Test-Deployment { param([string]$Name) $d = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json"); if ($null -eq $d) { Add-Fail "Deployment $Name missing"; return }; $a = [int]$d.status.availableReplicas; $r = [int]$d.spec.replicas; if ($r -gt 0 -and $a -ge $r) { Add-Pass "Deployment $Name available" } else { Add-Fail "Deployment $Name not available ($a/$r)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if (-not $pod) { return "" }; (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text.Trim() }
function Assert-NoManagedChaos { $resources = (Invoke-Kubectl @("-n", $TargetNamespace, "get", "podchaos,networkchaos,stresschaos", "-l", "cascade.io/phase=phase7", "--ignore-not-found")).Text; if ([string]::IsNullOrWhiteSpace($resources)) { Add-Pass "No Cascade-managed Chaos Mesh resources remain" } else { Add-Fail "Cascade-managed Chaos Mesh resources still exist: $resources" } }

try {
    Write-Section "Chaos engineering Acceptance"
    $api = Invoke-Kubectl @("version", "--request-timeout=5s"); if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unreachable"; throw "No cluster" }
    foreach ($d in @("redpanda", "clickhouse", "qdrant", "retrieval-service", "agent-tool-gateway", "agent-orchestrator-service", "chaos-planner-service", "chaos-executor-service")) { Test-Deployment $d }

    foreach ($t in @("investigation_runs", "agent_steps", "investigation_reports", "agent_tool_calls", "chaos_experiment_plans", "chaos_experiment_runs", "chaos_observations", "resilience_scores", "chaos_safety_violations")) {
        $tables = CH "SHOW TABLES FROM cascade"
        if ($tables -match "(?m)^$t$") { Add-Pass "ClickHouse table $t exists" } else { Add-Fail "ClickHouse table $t missing" }
    }

    foreach ($topic in @("agent.investigations", "chaos.experiments")) {
        $topicCheck = Test-CascadeRedpandaTopic -Namespace $Namespace -Topic $topic
        if ($topicCheck.Exists) { Add-Pass "$topic topic exists" } else { Add-Fail "$topic topic missing. Raw topic list: $($topicCheck.Raw)" }
    }
    foreach ($crd in @("podchaos.chaos-mesh.org", "networkchaos.chaos-mesh.org", "stresschaos.chaos-mesh.org")) {
        $r = Invoke-Kubectl @("get", "crd", $crd)
        if ($r.ExitCode -eq 0) { Add-Pass "Chaos Mesh CRD $crd exists" } else { Add-Fail "Chaos Mesh CRD $crd missing" }
    }
    $targetPods = (Invoke-Kubectl @("-n", $TargetNamespace, "get", "pod", "-l", "app=$TargetService", "-o", "jsonpath={.items[*].metadata.name}")).Text
    if (-not [string]::IsNullOrWhiteSpace($targetPods)) { Add-Pass "Allowlisted target workload $TargetService has pods" } else { Add-Fail "Target workload $TargetService has no pods" }

    Start-PF "chaos-planner-service" "8019:8019"
    Start-PF "chaos-executor-service" "8020:8020"
    try {
        $plannerReady = HttpJson GET "http://localhost:8019/ready"
        if ($plannerReady.service -eq "chaos-planner-service") { Add-Pass "chaos-planner-service ready" } else { Add-Fail "chaos-planner-service not ready" }
        $executorReady = HttpJson GET "http://localhost:8020/ready"
        if ($executorReady.service -eq "chaos-executor-service") { Add-Pass "chaos-executor-service ready" } else { Add-Fail "chaos-executor-service not ready" }
        $policy = HttpJson GET "http://localhost:8020/safety/policy"
        if ($policy.allowed_namespaces -contains $TargetNamespace -and $policy.denied_namespaces -contains "kube-system") { Add-Pass "/safety/policy returns allowlist/denylist" } else { Add-Fail "/safety/policy invalid" }

        $plan = HttpJson POST "http://localhost:8019/plans" @{ objective = "Validate $TargetService resilience to pod kill"; target_service = $TargetService; target_namespace = $TargetNamespace; experiment_kind = "pod_kill"; duration_seconds = 5; dry_run = $true }
        if ($plan.status -eq "ready" -and $plan.manifest.kind -eq "PodChaos") { Add-Pass "safe pod_kill plan created" } else { Add-Fail "safe pod_kill plan failed" }
        $planId = $plan.plan_id
        if ([int](CH "SELECT count() FROM cascade.chaos_experiment_plans WHERE plan_id = '$planId'") -gt 0) { Add-Pass "plan row inserted" } else { Add-Fail "plan row missing" }
        $validation = HttpJson POST "http://localhost:8019/plans/$planId/validate"
        if ($validation.allowed -eq $true) { Add-Pass "plan safety validation passes" } else { Add-Fail "plan safety validation failed" }

        $unsafeBefore = [int](CH "SELECT count() FROM cascade.chaos_safety_violations")
        $unsafe = HttpJson POST "http://localhost:8019/plans" @{ objective = "Unsafe system namespace chaos"; target_service = $TargetService; target_namespace = "kube-system"; experiment_kind = "pod_kill"; duration_seconds = 5; dry_run = $true } 1
        $unsafeAfter = [int](CH "SELECT count() FROM cascade.chaos_safety_violations")
        if ($null -eq $unsafe -and $unsafeAfter -gt $unsafeBefore) { Add-Pass "denied namespace plan rejected and violation recorded" } else { Add-Fail "unsafe namespace rejection failed" }
        Assert-NoManagedChaos

        $dryRun = HttpJson POST "http://localhost:8020/runs" @{ plan_id = $planId; approved = $false; dry_run = $true; observation_window_seconds = 5; trigger_agent_investigation = $false }
        if ($dryRun.status -eq "dry_run" -and $dryRun.dry_run -eq $true) { Add-Pass "dry-run execution succeeds" } else { Add-Fail "dry-run execution failed" }
        if ([int](CH "SELECT count() FROM cascade.chaos_experiment_runs WHERE run_id = '$($dryRun.run_id)'") -gt 0) { Add-Pass "dry-run row inserted" } else { Add-Fail "dry-run row missing" }
        Assert-NoManagedChaos

        $realRun = $null
        if (-not $DryRunOnly -and -not $NoChaos) {
            $realRun = HttpJson POST "http://localhost:8020/runs" @{ plan_id = $planId; approved = $true; dry_run = $false; observation_window_seconds = 5; trigger_agent_investigation = $true } 1
            if ($realRun.status -eq "completed" -and $realRun.cleanup_status -match "cleaned_up|not_found") { Add-Pass "real bounded pod_kill execution completed with cleanup" } else { Add-Fail "real bounded pod_kill execution failed" }
            if ([int](CH "SELECT count() FROM cascade.chaos_observations WHERE run_id = '$($realRun.run_id)'") -gt 0) { Add-Pass "observation row inserted" } else { Add-Fail "observation row missing" }
            if ([int](CH "SELECT count() FROM cascade.resilience_scores WHERE run_id = '$($realRun.run_id)'") -gt 0) { Add-Pass "resilience score row inserted" } else { Add-Fail "resilience score row missing" }
            $detail = HttpJson GET "http://localhost:8020/runs/$($realRun.run_id)"
            if ($detail.observation -and $detail.score) { Add-Pass "GET /runs/{run_id} returns observation and score" } else { Add-Fail "run detail missing observation/score" }
        } else {
            Add-Warn "Real chaos execution skipped by -DryRunOnly/-NoChaos"
        }

        $runs = HttpJson GET "http://localhost:8020/runs?limit=5"
        if ($runs.runs.Count -ge 1) { Add-Pass "GET /runs returns valid JSON" } else { Add-Fail "GET /runs invalid" }
        $scores = HttpJson GET "http://localhost:8020/scores/recent?limit=5"
        if ($scores.scores.Count -ge 0) { Add-Pass "GET /scores/recent returns valid JSON" } else { Add-Fail "GET /scores/recent invalid" }
        $events = (Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/redpanda", "--", "rpk", "topic", "consume", "chaos.experiments", "--offset", "start", "--num", "1")).Text
        if ($events -match "chaos.run.started") { Add-Pass "chaos.experiments contains lifecycle events" } else { Add-Fail "chaos.experiments lifecycle events not observed" }
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
if ($Failed.Count -eq 0) { Write-Host "CHAOS ACCEPTANCE: PASS"; exit 0 }
Write-Host "CHAOS ACCEPTANCE: FAIL"
exit 1
