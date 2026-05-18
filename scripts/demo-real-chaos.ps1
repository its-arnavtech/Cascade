param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [ValidateSet("catalogue", "carts", "orders", "payment", "shipping", "queue-master", "user")]
    [string]$TargetService = "catalogue",
    [int]$DurationSeconds = 15,
    [string]$ExpectedContext = "kind-cascade",
    [switch]$ConfirmLocalKind,
    [switch]$AllowContextOverride
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$LiveFlagsEnabled = $false
$ExecutorPortForwardStarted = $false
. "$PSScriptRoot\lib\kafka-topics.ps1"

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

function Print-SafetyPolicy {
    if (-not $script:ExecutorPortForwardStarted) { return }
    Write-Host ""
    Write-Host "---- Current chaos safety policy ----"
    try {
        $policy = Invoke-RestMethod -Method GET -Uri "http://localhost:8020/safety/policy" -TimeoutSec 20
        $policy | ConvertTo-Json -Depth 40
    } catch {
        Write-Host "Could not fetch chaos safety policy: $($_.Exception.Message)"
    }
}

function Print-FailureDiagnostics {
    Print-SafetyPolicy
    Invoke-DiagnosticCommand "Target pods" { kubectl -n $TargetNamespace get pods -l "app=$TargetService" -o wide }
    Invoke-DiagnosticCommand "Recent target namespace events" { kubectl -n $TargetNamespace get events --sort-by=.lastTimestamp }
    Invoke-DiagnosticCommand "Chaos executor status" { kubectl -n $Namespace get deploy,pods -l "app=chaos-executor-service" -o wide }
    Invoke-DiagnosticCommand "Chaos executor rollout" { kubectl -n $Namespace rollout status deployment/chaos-executor-service --timeout=15s }
    Invoke-DiagnosticCommand "Chaos Mesh controller pods" { kubectl -n chaos-mesh get pods -o wide }
    Invoke-DiagnosticCommand "Cascade-managed Chaos Mesh resources" { kubectl -n $TargetNamespace get podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found=true -o wide }
}

function Disable-LiveChaosFlags {
    if (-not $script:LiveFlagsEnabled) { return }
    Write-Host ""
    Write-Host "---- Disable live chaos flags on executor ----"
    try {
        kubectl -n $Namespace set env deployment/chaos-executor-service ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_CHAOS=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-
        kubectl -n $Namespace rollout status deployment/chaos-executor-service --timeout=180s
    } catch {
        Write-Host "Failed to disable live chaos flags automatically: $($_.Exception.Message)"
        Write-Host "Run manually:"
        Write-Host "kubectl -n $Namespace set env deployment/chaos-executor-service ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_CHAOS=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-"
    }
}

try {
    if (-not $ConfirmLocalKind) { throw "Refusing real chaos without -ConfirmLocalKind." }
    if ($DurationSeconds -lt 10 -or $DurationSeconds -gt 30) { throw "DurationSeconds must be between 10 and 30." }
    if ($TargetNamespace -ne "cascade-targets") { throw "Refusing target namespace '$TargetNamespace'. Real chaos demo is scoped to cascade-targets." }
    $context = (& kubectl config current-context 2>&1).Trim()
    if ($context -ne $ExpectedContext -and -not $AllowContextOverride) { throw "Refusing context '$context'. Expected '$ExpectedContext'." }

    Invoke-Checked "Verify Sock Shop target pods" { kubectl -n $TargetNamespace get pods -l "app=$TargetService" }
    Invoke-Checked "Verify Chaos Mesh" { & "$PSScriptRoot\verify-chaos-mesh.ps1" -ExpectedContext $ExpectedContext -TargetNamespace $TargetNamespace }
    $topics = Ensure-CascadeRedpandaTopics -Namespace $Namespace -Topics @("chaos.experiments", "experiments.events")
    if (-not $topics.Success) { throw "Required Redpanda topics missing: $($topics.Missing -join ', ')" }

    Invoke-Checked "Enable live chaos flags on executor" {
        kubectl -n $Namespace set env deployment/chaos-executor-service `
            ENABLE_DANGEROUS_ACTIONS=true ENABLE_REAL_CHAOS=true CASCADE_LIVE_DEMO_MODE=true `
            CASCADE_ACTIVE_CLUSTER_CONTEXT=$ExpectedContext CASCADE_ALLOWED_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_TARGET_NAMESPACE=$TargetNamespace CASCADE_REQUIRE_APPROVAL=true CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }
    $LiveFlagsEnabled = $true
    Invoke-Checked "Wait for chaos executor rollout" { kubectl -n $Namespace rollout status deployment/chaos-executor-service --timeout=180s }

    Start-PF "chaos-planner-service" "8019:8019"
    Start-PF "chaos-executor-service" "8020:8020"
    $ExecutorPortForwardStarted = $true
    Start-PF "approval-service" "8022:8022"

    $plan = HttpJson POST "http://localhost:8019/plans" @{
        objective = "Local demo bounded pod kill for $TargetService"
        target_service = $TargetService
        target_namespace = $TargetNamespace
        experiment_kind = "pod_kill"
        duration_seconds = $DurationSeconds
        dry_run = $true
    }
    $planId = $plan.plan_id
    if (-not $planId) { throw "Plan response did not include plan_id." }
    Write-Host "Created chaos plan $planId"

    $dry = HttpJson POST "http://localhost:8020/runs" @{
        plan_id = $planId
        dry_run = $true
        approved = $false
        observation_window_seconds = 5
        trigger_agent_investigation = $false
    }
    if ($dry.status -ne "dry_run") { throw "Chaos dry-run did not pass. Status: $($dry.status)" }
    Write-Host "Dry-run passed for plan $planId"

    $approval = HttpJson POST "http://localhost:8022/approvals" @{
        plan_id = $planId
        decision = "approved"
        approver = "local-demo-user"
        approver_role = "developer"
        reason = "Approved local demo real chaos after dry-run"
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

    $run = HttpJson POST "http://localhost:8020/runs" @{
        plan_id = $planId
        approval_id = $approvalId
        dry_run = $false
        approved = $true
        observation_window_seconds = 10
        trigger_agent_investigation = $false
    }
    $run | ConvertTo-Json -Depth 40

    if ($run.run_id) {
        Write-Host ""
        Write-Host "---- Run detail ----"
        HttpJson GET "http://localhost:8020/runs/$($run.run_id)" | ConvertTo-Json -Depth 40
    }

    Invoke-Checked "Cleanup managed Chaos Mesh resources" { kubectl -n $TargetNamespace delete podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found=true }
    Invoke-Checked "Verify target deployment recovers" { kubectl -n $TargetNamespace rollout status "deployment/$TargetService" --timeout=180s }

    Write-Host ""
    Write-Host "Cleanup commands:"
    Write-Host "kubectl -n $TargetNamespace delete podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found=true"
    Write-Host "kubectl -n $Namespace set env deployment/chaos-executor-service ENABLE_DANGEROUS_ACTIONS=false ENABLE_REAL_CHAOS=false CASCADE_LIVE_DEMO_MODE=false CASCADE_ACTIVE_CLUSTER_CONTEXT-"
} catch {
    if ($LiveFlagsEnabled) {
        Print-FailureDiagnostics
    }
    throw
} finally {
    try {
        Invoke-DiagnosticCommand "Best-effort cleanup of managed Chaos Mesh resources" { kubectl -n $TargetNamespace delete podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found=true }
    } finally {
        Stop-PF
        Disable-LiveChaosFlags
    }
}
