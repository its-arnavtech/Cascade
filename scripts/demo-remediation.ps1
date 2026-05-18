param(
    [string]$Namespace = "cascade-system",
    [string]$Service = "recommendationservice",
    [ValidateSet("manual", "anomaly", "investigation", "chaos")]
    [string]$TriggerType = "manual",
    [switch]$DryRunOnly = $true,
    [switch]$AllowExecution
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Svc, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Svc", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 240 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 80) -TimeoutSec 240 } }

try {
    Write-Section "Remediation Demo - Remediation + Human Approval"
    Start-PF "remediation-recommender-service" "8021:8021"
    Start-PF "approval-service" "8022:8022"
    Start-PF "remediation-executor-service" "8023:8023"
    Start-PF "agent-tool-gateway" "8017:8017"

    Write-Section "Safety Policy"
    $policy = HttpJson GET "http://localhost:8023/safety/policy"
    $policy | ConvertTo-Json -Depth 20

    Write-Section "Generate Evidence-backed Plan"
    $body = @{ trigger_type = $TriggerType; trigger_id = ""; service = $Service; namespace = "cascade-targets"; objective = "Recommend safe next steps for $Service reliability symptoms"; preferred_action_type = "investigate_only" }
    if ($TriggerType -eq "anomaly") {
        $plan = HttpJson POST "http://localhost:8021/plans/from-latest-anomaly" @{ service = $Service; preferred_action_type = "investigate_only" }
    } elseif ($TriggerType -eq "investigation") {
        $plan = HttpJson POST "http://localhost:8021/plans/from-latest-investigation" @{ service = $Service; preferred_action_type = "investigate_only" }
    } else {
        $plan = HttpJson POST "http://localhost:8021/plans" $body
    }
    $planId = $plan.plan_id
    $plan.plan | Select-Object plan_id, status, action_type, confidence, action_summary | Format-List

    Write-Section "Evidence Summary"
    $plan.plan.evidence_refs | ConvertTo-Json -Depth 20
    Write-Section "Remediation Steps"
    $plan.plan.remediation_steps
    Write-Section "Rollback Steps"
    $plan.plan.rollback_steps
    Write-Section "Safety Findings"
    $plan.plan.safety_findings

    Write-Section "Reject Unsafe Example"
    try {
        HttpJson POST "http://localhost:8021/plans" @{ trigger_type = "manual"; service = $Service; namespace = "kube-system"; objective = "Unsafe remediation"; preferred_action_type = "restart_deployment" } | ConvertTo-Json -Depth 20
    } catch {
        Write-Host "Rejected as expected: $($_.Exception.Message)"
    }

    Write-Section "Approve Safe Dry-run Plan"
    $approval = HttpJson POST "http://localhost:8022/approvals" @{ plan_id = $planId; decision = "approved"; approver = "local-user"; approver_role = "developer"; reason = "Approved dry-run validation only"; expires_minutes = 60 }
    $approval.approval | Select-Object approval_id, plan_id, decision, approver, expires_at | Format-List

    Write-Section "Dry-run Validation"
    $dry = HttpJson POST "http://localhost:8023/executions/dry-run" @{ plan_id = $planId; approval_id = $approval.approval.approval_id }
    $dry.execution | Select-Object execution_id, plan_id, action_type, dry_run, executed, validation_status, output_summary | Format-List

    Write-Section "Real Execution Disabled By Default"
    try {
        HttpJson POST "http://localhost:8023/executions" @{ plan_id = $planId; approval_id = $approval.approval.approval_id; dry_run = $false } | ConvertTo-Json -Depth 20
    } catch {
        Write-Host "Blocked as expected: $($_.Exception.Message)"
    }

    if ($AllowExecution -and -not $DryRunOnly) {
        Write-Host "AllowExecution requested, but the default manifest keeps EXECUTION_ENABLED=false. Set the deployment env explicitly before real execution."
    }

    Write-Section "Read-only Agent Gateway Tools"
    HttpJson GET "http://localhost:8017/tools" | Select-Object -ExpandProperty tools | Where-Object { $_.name -match "remediation" } | Format-Table name, read_only, target_service
    HttpJson POST "http://localhost:8017/tools/get_recent_remediation_plans" @{ limit = 3 } | ConvertTo-Json -Depth 20
} finally {
    Stop-PF
}

