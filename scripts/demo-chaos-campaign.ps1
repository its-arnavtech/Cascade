param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [string[]]$Services = @("catalogue", "carts"),
    [int]$Port = 18119
)

$ErrorActionPreference = "Stop"
$PortForward = $null

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }

try {
    Write-Section "Chaos Campaign Dry-Run Demo"
    kubectl -n $Namespace rollout status deployment/chaos-planner-service --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "chaos-planner-service rollout is not healthy" }
    kubectl -n $Namespace rollout status deployment/chaos-executor-service --timeout=120s
    if ($LASTEXITCODE -ne 0) { throw "chaos-executor-service rollout is not healthy" }

    $PortForward = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/chaos-planner-service", "$Port`:8019") -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 3
    if ($PortForward.HasExited) { throw "port-forward for chaos-planner-service exited early" }

    $templates = @()
    foreach ($service in $Services) {
        $templates += @{
            name = "dry-run pod kill $service"
            experiment_kind = "pod_kill"
            target_service = $service
            duration_seconds = 10
            dry_run = $true
        }
    }
    $campaignBody = @{
        name = "Local dry-run chaos campaign"
        target_namespace = $TargetNamespace
        allowed_services = $Services
        experiment_templates = $templates
        schedule = @{ trigger = "manual" }
        max_experiments_per_run = [Math]::Min(3, $Services.Count)
        blast_radius_limit = 0.5
        cooldown_seconds = 0
        dry_run = $true
        local_demo_execution_enabled = $false
    } | ConvertTo-Json -Depth 8

    $campaignResponse = Invoke-RestMethod -Method POST -Uri "http://localhost:$Port/campaigns" -Body $campaignBody -ContentType "application/json" -TimeoutSec 30
    $campaignId = $campaignResponse.campaign.campaign_id
    if (-not $campaignId) { throw "Campaign create response did not include campaign_id" }
    Write-Host "Created campaign $campaignId"

    $runBody = @{ dry_run = $true; requested_by = "demo-chaos-campaign"; observation_window_seconds = 10; trigger_agent_investigation = $false } | ConvertTo-Json
    $runResponse = Invoke-RestMethod -Method POST -Uri "http://localhost:$Port/campaigns/$campaignId/start" -Body $runBody -ContentType "application/json" -TimeoutSec 180
    $runResponse | ConvertTo-Json -Depth 8
    if ($runResponse.run.status -notin @("completed", "completed_with_blocks")) { throw "Unexpected campaign run status $($runResponse.run.status)" }

    Write-Host "CHAOS CAMPAIGN DEMO: PASS"
} finally {
    if ($null -ne $PortForward -and -not $PortForward.HasExited) {
        Stop-Process -Id $PortForward.Id -Force
    }
}
