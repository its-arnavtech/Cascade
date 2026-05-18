param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [ValidateSet("catalogue", "carts", "orders", "payment", "shipping", "queue-master", "user")]
    [string]$TargetService = "catalogue",
    [string]$ExpectedContext = "kind-cascade",
    [switch]$ConfirmLocalKind,
    [switch]$AllowContextOverride
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$LiveFlagsEnabled = $false
$ExecutorPortForwardStarted = $false

function Invoke-Checked {
    param([string]$Description, [scriptblock]$Command)
    Write-Host ""
    Write-Host "---- $Description ----"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" }
}

function Invoke-DiagnosticCommand {
    param([string]$Description, [scriptblock]$Command)
    Write-Host ""
    Write-Host "---- $Description ----"
    try {
        & $Command
    } catch {
        Write-Host "Diagnostic failed: $($_.Exception.Message)"
    }
}

function Start-PF {
    param([string]$Service, [string]$Map)
    $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru
    $script:PortForwards.Add($p) | Out-Null
    Start-Sleep -Seconds 2
}

function Stop-PF {
    foreach ($p in $script:PortForwards) {
        if ($null -ne $p -and -not $p.HasExited) {
            Stop-Process -Id $p.Id -Force
        }
    }
    $script:PortForwards.Clear()
}

function Get-ErrorResponseBody {
    param([object]$ErrorRecord)
    $response = $ErrorRecord.Exception.Response
    if ($null -eq $response) { return "" }
    try {
        if ($response.Content) {
            return $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        }
    } catch {
    }
    try {
        $stream = $response.GetResponseStream()
        if ($null -eq $stream) { return "" }
        $reader = New-Object System.IO.StreamReader($stream)
        return $reader.ReadToEnd()
    } catch {
        return ""
    }
}

function HttpJson {
    param([string]$Method, [string]$Url, [object]$Body = $null)
    $params = @{
        Method = $Method
        Uri = $Url
        TimeoutSec = 240
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = ($Body | ConvertTo-Json -Depth 80)
    }
    try {
        return Invoke-RestMethod @params
    } catch {
        $statusCode = ""
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        $bodyText = Get-ErrorResponseBody $_
        Write-Host ""
        Write-Host "HTTP request failed: $Method $Url"
        if ($statusCode) { Write-Host "HTTP status: $statusCode" }
        if ($bodyText) {
            Write-Host "Response body:"
            Write-Host $bodyText
        }
        throw
    }
}

function Get-PlanPostChecks {
    param([object]$Plan)
    if ($Plan.post_checks) { return @($Plan.post_checks) }
    if ($Plan.plan -and $Plan.plan.post_checks) { return @($Plan.plan.post_checks) }
    if ($Plan.plan -and $Plan.plan.plan -and $Plan.plan.plan.post_checks) { return @($Plan.plan.plan.post_checks) }
    return @()
}

function Print-SafetyPolicy {
    if (-not $script:ExecutorPortForwardStarted) { return }
    Write-Host ""
    Write-Host "---- Current remediation safety policy ----"
    try {
        $policy = Invoke-RestMethod -Method GET -Uri "http://localhost:8023/safety/policy" -TimeoutSec 20
        $policy | ConvertTo-Json -Depth 40
    } catch {
        Write-Host "Could not fetch remediation safety policy: $($_.Exception.Message)"
    }
}

function Print-FailureDiagnostics {
    Print-SafetyPolicy
    Invoke-DiagnosticCommand "Target deployment" { kubectl -n $TargetNamespace get deployment $TargetService -o wide }
    Invoke-DiagnosticCommand "Target pods" { kubectl -n $TargetNamespace get pods -l "app=$TargetService" -o wide }
    Invoke-DiagnosticCommand "Target rollout status" { kubectl -n $TargetNamespace rollout status "deployment/$TargetService" --timeout=15s }
    Invoke-DiagnosticCommand "Recent target namespace events" { kubectl -n $TargetNamespace get events --sort-by=.lastTimestamp }
    Invoke-DiagnosticCommand "Remediation executor status" { kubectl -n $Namespace get deploy,pods -l "app=remediation-executor-service" -o wide }
}

function Assert-ReadyTargetPod {
    param([string]$Description)
    Write-Host ""
    Write-Host "---- $Description ----"
    $podsJson = kubectl -n $TargetNamespace get pods -l "app=$TargetService" -o json
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" }
    $pods = $podsJson | ConvertFrom-Json
    $readyPods = @(
        $pods.items | Where-Object {
            $ready = @($_.status.conditions | Where-Object { $_.type -eq "Ready" -and $_.status -eq "True" })
            -not $_.metadata.deletionTimestamp -and $_.status.phase -eq "Running" -and $ready.Count -gt 0
        }
    )
    if ($readyPods.Count -lt 1) { throw "No current Ready pod found for app=$TargetService in $TargetNamespace." }
    $readyPods | ForEach-Object { Write-Host "$($_.metadata.name) is Ready" }
}

function Disable-LiveRemediationFlags {
    if (-not $script:LiveFlagsEnabled) { return }
    Write-Host ""
    Write-Host "---- Disable live remediation flags on executor ----"
    try {
        kubectl -n $Namespace set env deployment/remediation-executor-service EXECUTION_ENABLED=false ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_REMEDIATION=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-
        kubectl -n $Namespace rollout status deployment/remediation-executor-service --timeout=180s
    } catch {
        Write-Host "Failed to disable live remediation flags automatically: $($_.Exception.Message)"
        Write-Host "Run manually:"
        Write-Host "kubectl -n $Namespace set env deployment/remediation-executor-service EXECUTION_ENABLED=false ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_REMEDIATION=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-"
    }
}

function Verify-LiveRemediationFlagsDisabled {
    if (-not $script:LiveFlagsEnabled) { return }
    Write-Host ""
    Write-Host "---- Verify live remediation flags are disabled ----"
    try {
        $envJson = kubectl -n $Namespace get deployment remediation-executor-service -o jsonpath='{.spec.template.spec.containers[0].env}'
        $envRows = $envJson | ConvertFrom-Json
        $values = @{}
        foreach ($row in $envRows) { $values[$row.name] = $row.value }
        foreach ($name in @("EXECUTION_ENABLED", "ENABLE_DANGEROUS_ACTIONS", "ENABLE_REAL_REMEDIATION", "CASCADE_LIVE_DEMO_MODE")) {
            if ($values[$name] -ne "false") { throw "$name is '$($values[$name])', expected false" }
        }
        Write-Host "Live remediation flags are false."
    } catch {
        Write-Host "Could not verify live remediation flags: $($_.Exception.Message)"
    }
}

try {
    if (-not $ConfirmLocalKind) { throw "Refusing real remediation without -ConfirmLocalKind." }
    if ($TargetNamespace -ne "cascade-targets") { throw "Refusing target namespace '$TargetNamespace'. Real remediation demo is scoped to cascade-targets." }
    $context = (& kubectl config current-context 2>&1).Trim()
    if ($context -ne $ExpectedContext -and -not $AllowContextOverride) { throw "Refusing context '$context'. Expected '$ExpectedContext'." }

    Invoke-Checked "Verify target namespace" { kubectl get namespace $TargetNamespace }
    Invoke-Checked "Verify target deployment" { kubectl -n $TargetNamespace get deployment $TargetService }
    Assert-ReadyTargetPod "Verify target pod readiness"

    Invoke-Checked "Enable live remediation flags on executor" {
        kubectl -n $Namespace set env deployment/remediation-executor-service `
            EXECUTION_ENABLED=true ENABLE_DANGEROUS_ACTIONS=true ENABLE_REAL_REMEDIATION=true CASCADE_LIVE_DEMO_MODE=true `
            CASCADE_ACTIVE_CLUSTER_CONTEXT=$ExpectedContext CASCADE_ALLOWED_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_TARGET_NAMESPACE=$TargetNamespace CASCADE_REQUIRE_APPROVAL=true CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }
    $LiveFlagsEnabled = $true
    Invoke-Checked "Wait for remediation executor rollout" { kubectl -n $Namespace rollout status deployment/remediation-executor-service --timeout=180s }

    Start-PF "remediation-recommender-service" "8021:8021"
    Start-PF "approval-service" "8022:8022"
    Start-PF "remediation-executor-service" "8023:8023"
    $ExecutorPortForwardStarted = $true

    $policy = HttpJson GET "http://localhost:8023/safety/policy"
    if ($policy.protected.services -contains $TargetService) { throw "Refusing protected service '$TargetService'." }
    if ($policy.allowed_services -notcontains $TargetService) { throw "Refusing non-allowlisted service '$TargetService'." }

    $planResponse = HttpJson POST "http://localhost:8021/plans" @{
        trigger_type = "manual"
        service = $TargetService
        namespace = $TargetNamespace
        objective = "Local demo restart for $TargetService after dry-run validation"
        preferred_action_type = "restart_deployment"
    }
    $planId = $planResponse.plan_id
    $plan = $planResponse.plan
    if (-not $planId) { throw "Plan response did not include plan_id." }
    if ($plan.action_type -ne "restart_deployment") { throw "Plan action_type was '$($plan.action_type)', expected restart_deployment." }
    if (-not $plan.rollback_steps -or @($plan.rollback_steps).Count -lt 1) { throw "Plan is missing rollback steps." }
    $postChecks = Get-PlanPostChecks $plan
    if ($postChecks.Count -lt 1) { throw "Plan is missing post-checks." }
    Write-Host "Created remediation plan $planId with $(@($plan.rollback_steps).Count) rollback step(s) and $($postChecks.Count) post-check(s)."

    $dry = HttpJson POST "http://localhost:8023/executions/dry-run" @{
        plan_id = $planId
        dry_run = $true
    }
    if ($dry.execution.validation_status -notin @("passed", "degraded")) { throw "Remediation dry-run did not pass. Status: $($dry.execution.validation_status)" }
    Write-Host "Dry-run passed for plan $planId"

    $approval = HttpJson POST "http://localhost:8022/approvals" @{
        plan_id = $planId
        decision = "approved"
        approver = "local-demo-user"
        approver_role = "developer"
        reason = "Approved local demo remediation after dry-run"
        expires_minutes = 30
    }
    $approvalId = $approval.approval.approval_id
    if (-not $approvalId) { throw "Approval response did not include approval.approval_id." }
    if ($approval.approval.decision -ne "approved") { throw "Approval decision was '$($approval.approval.decision)', expected approved." }

    $approvalStatus = HttpJson GET "http://localhost:8022/plans/$planId/approval-status"
    if ($approvalStatus.PSObject.Properties.Name -contains "approval_current" -and -not $approvalStatus.approval_current) {
        throw "Approval $approvalId is not current."
    }
    Write-Host "Created current approval $approvalId"

    $execution = HttpJson POST "http://localhost:8023/executions" @{
        plan_id = $planId
        approval_id = $approvalId
        dry_run = $false
    }
    $execution | ConvertTo-Json -Depth 40

    Invoke-Checked "Verify deployment recovers" { kubectl -n $TargetNamespace rollout status "deployment/$TargetService" --timeout=180s }
    Assert-ReadyTargetPod "Verify pod readiness after remediation"
    Invoke-Checked "Verify namespace remains target namespace" { kubectl get namespace $TargetNamespace }

    Write-Host ""
    Write-Host "Rollback/post-check commands:"
    Write-Host "kubectl -n $TargetNamespace rollout status deployment/$TargetService --timeout=180s"
    Write-Host "kubectl -n $TargetNamespace get pods -l app=$TargetService -o wide"
    Write-Host "kubectl -n $TargetNamespace rollout history deployment/$TargetService"
    Write-Host "kubectl -n $TargetNamespace rollout undo deployment/$TargetService"
    Write-Host "kubectl -n $Namespace set env deployment/remediation-executor-service EXECUTION_ENABLED=false ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_REMEDIATION=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-"
} catch {
    if ($LiveFlagsEnabled) {
        Print-FailureDiagnostics
    }
    throw
} finally {
    try {
        Stop-PF
    } finally {
        Disable-LiveRemediationFlags
        Verify-LiveRemediationFlagsDisabled
    }
}
