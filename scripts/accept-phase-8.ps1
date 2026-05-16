param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [string]$TargetService = "recommendationservice"
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
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 8) for ($i = 1; $i -le $Retries; $i++) { try { if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 240 } return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 240 } catch { Start-Sleep -Seconds 2 } }; return $null }
function Test-Deployment { param([string]$Name) $d = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json"); if ($null -eq $d) { Add-Fail "Deployment $Name missing"; return }; $a = [int]$d.status.availableReplicas; $r = [int]$d.spec.replicas; if ($r -gt 0 -and $a -ge $r) { Add-Pass "Deployment $Name available" } else { Add-Fail "Deployment $Name not available ($a/$r)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if (-not $pod) { return "" }; (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text.Trim() }

try {
    Write-Section "Phase 8 Acceptance"
    $api = Invoke-Kubectl @("version", "--request-timeout=5s"); if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unreachable"; throw "No cluster" }
    foreach ($d in @("redpanda", "clickhouse", "qdrant", "retrieval-service", "agent-tool-gateway", "agent-orchestrator-service", "chaos-planner-service", "chaos-executor-service", "remediation-recommender-service", "approval-service", "remediation-executor-service")) { Test-Deployment $d }

    $tables = CH "SHOW TABLES FROM cascade"
    foreach ($t in @("chaos_experiment_plans", "chaos_experiment_runs", "remediation_plans", "remediation_approvals", "remediation_executions", "remediation_safety_violations", "remediation_policy_audit")) {
        if ($tables -match "(?m)^$t$") { Add-Pass "ClickHouse table $t exists" } else { Add-Fail "ClickHouse table $t missing" }
    }
    foreach ($topic in @("chaos.experiments", "remediation.actions")) {
        $topicCheck = Test-CascadeRedpandaTopic -Namespace $Namespace -Topic $topic
        if ($topicCheck.Exists) { Add-Pass "$topic topic exists" } else { Add-Fail "$topic topic missing. Raw topic list: $($topicCheck.Raw)" }
    }

    Start-PF "remediation-recommender-service" "8021:8021"
    Start-PF "approval-service" "8022:8022"
    Start-PF "remediation-executor-service" "8023:8023"
    Start-PF "agent-tool-gateway" "8017:8017"
    try {
        foreach ($svc in @(@("8021", "remediation-recommender-service"), @("8022", "approval-service"), @("8023", "remediation-executor-service"))) {
            $ready = HttpJson GET "http://localhost:$($svc[0])/ready"
            if ($ready.service -eq $svc[1]) { Add-Pass "$($svc[1]) ready" } else { Add-Fail "$($svc[1]) not ready" }
        }
        $policy = HttpJson GET "http://localhost:8023/safety/policy"
        if ($policy.execution_enabled -eq $false -and $policy.denied_namespaces -contains "kube-system") { Add-Pass "remediation safety policy returned and execution disabled" } else { Add-Fail "remediation safety policy invalid" }

        $plan = HttpJson POST "http://localhost:8021/plans" @{ trigger_type = "manual"; trigger_id = ""; service = $TargetService; namespace = $TargetNamespace; objective = "Recommend next steps for $TargetService restart anomaly"; preferred_action_type = "investigate_only" }
        $planId = $plan.plan_id
        if ($planId -and $plan.plan.rollback_steps.Count -ge 1 -and $plan.plan.evidence_refs.Count -ge 1) { Add-Pass "investigate_only remediation plan generated with evidence and rollback" } else { Add-Fail "plan generation missing required content" }
        if ([int](CH "SELECT count() FROM cascade.remediation_plans WHERE plan_id = '$planId'") -gt 0) { Add-Pass "plan row inserted" } else { Add-Fail "plan row missing" }

        $unsafeBefore = [int](CH "SELECT count() FROM cascade.remediation_safety_violations")
        $unsafe = HttpJson POST "http://localhost:8021/plans" @{ trigger_type = "manual"; service = $TargetService; namespace = "kube-system"; objective = "Unsafe system remediation"; preferred_action_type = "restart_deployment" } 1
        $unsafeAfter = [int](CH "SELECT count() FROM cascade.remediation_safety_violations")
        if ($null -eq $unsafe -and $unsafeAfter -gt $unsafeBefore) { Add-Pass "unsafe remediation rejected and violation recorded" } else { Add-Fail "unsafe remediation rejection failed" }

        $approval = HttpJson POST "http://localhost:8022/approvals" @{ plan_id = $planId; decision = "approved"; approver = "local-user"; approver_role = "developer"; reason = "Reviewed and approved dry-run validation only"; expires_minutes = 60 }
        $approvalId = $approval.approval.approval_id
        if ($approvalId) { Add-Pass "approval recorded" } else { Add-Fail "approval failed" }
        $rejectPlan = HttpJson POST "http://localhost:8021/plans" @{ trigger_type = "manual"; service = $TargetService; namespace = $TargetNamespace; objective = "Rejected sample"; preferred_action_type = "investigate_only" }
        $rejection = HttpJson POST "http://localhost:8022/approvals" @{ plan_id = $rejectPlan.plan_id; decision = "rejected"; approver = "local-user"; approver_role = "developer"; reason = "Acceptance rejection path"; expires_minutes = 60 }
        if ($rejection.approval.decision -eq "rejected") { Add-Pass "rejection recorded" } else { Add-Fail "rejection failed" }

        $dry = HttpJson POST "http://localhost:8023/executions/dry-run" @{ plan_id = $planId; approval_id = $approvalId }
        if ($dry.execution.dry_run -eq $true -and $dry.execution.executed -eq $false) { Add-Pass "dry-run execution recorded without mutation" } else { Add-Fail "dry-run execution failed" }

        $real = HttpJson POST "http://localhost:8023/executions" @{ plan_id = $planId; approval_id = $approvalId; dry_run = $false } 1
        if ($null -eq $real) { Add-Pass "real execution rejected while EXECUTION_ENABLED=false" } else { Add-Fail "real execution unexpectedly allowed" }

        $tools = HttpJson GET "http://localhost:8017/tools"
        $names = @($tools.tools | ForEach-Object { $_.name })
        if ($names -contains "get_recent_remediation_plans" -and $names -contains "get_remediation_safety_policy" -and $names -notcontains "approve_remediation" -and $names -notcontains "execute_remediation") { Add-Pass "agent gateway exposes only read-only remediation tools" } else { Add-Fail "agent gateway remediation tools invalid" }
        $toolResult = HttpJson POST "http://localhost:8017/tools/get_recent_remediation_plans" @{ limit = 3 }
        if ($toolResult.status -eq "ok") { Add-Pass "agent gateway remediation plan tool works" } else { Add-Fail "agent gateway remediation plan tool failed" }

        if ((HttpJson GET "http://localhost:8021/plans?limit=5").plans.Count -ge 1) { Add-Pass "GET /plans returns valid JSON" } else { Add-Fail "GET /plans invalid" }
        if ((HttpJson GET "http://localhost:8022/approvals?limit=5").approvals.Count -ge 1) { Add-Pass "GET /approvals returns valid JSON" } else { Add-Fail "GET /approvals invalid" }
        if ((HttpJson GET "http://localhost:8023/executions?limit=5").executions.Count -ge 1) { Add-Pass "GET /executions returns valid JSON" } else { Add-Fail "GET /executions invalid" }
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
if ($Failed.Count -eq 0) { Write-Host "PHASE 8 ACCEPTANCE: PASS"; exit 0 }
Write-Host "PHASE 8 ACCEPTANCE: FAIL"
exit 1
