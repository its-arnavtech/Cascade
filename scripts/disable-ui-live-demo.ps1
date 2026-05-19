param(
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Stop"
$StatusPortForward = $null

function Invoke-Checked {
    param([string]$Description, [scriptblock]$Command)
    Write-Host ""
    Write-Host "---- $Description ----"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" }
}

function Start-StatusPortForward {
    $script:StatusPortForward = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/command-center", "18300:8030") -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 3
}

function Stop-StatusPortForward {
    if ($null -ne $script:StatusPortForward -and -not $script:StatusPortForward.HasExited) {
        Stop-Process -Id $script:StatusPortForward.Id -Force
    }
}

function Print-LiveDemoStatus {
    Write-Host ""
    Write-Host "---- Command Center live-demo status ----"
    Write-Host "Endpoint: http://localhost:18300/api/live-demo/status"
    Start-StatusPortForward
    try {
        Invoke-RestMethod -Method GET -Uri "http://localhost:18300/api/live-demo/status" -TimeoutSec 20 | ConvertTo-Json -Depth 40
    } finally {
        Stop-StatusPortForward
    }
}

try {
    Invoke-Checked "Disable chaos executor live-demo flags" {
        kubectl -n $Namespace set env deployment/chaos-executor-service `
            ENABLE_DANGEROUS_ACTIONS=false `
            ENABLE_REAL_CHAOS=false `
            CASCADE_LIVE_DEMO_MODE=false `
            CASCADE_ACTIVE_CLUSTER_CONTEXT- `
            CASCADE_ALLOWED_CLUSTER_CONTEXT- `
            CASCADE_ALLOWED_TARGET_NAMESPACE- `
            CASCADE_REQUIRE_APPROVAL=true `
            CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }

    Invoke-Checked "Disable remediation executor live-demo flags" {
        kubectl -n $Namespace set env deployment/remediation-executor-service `
            EXECUTION_ENABLED=false `
            ENABLE_DANGEROUS_ACTIONS=false `
            ENABLE_REAL_REMEDIATION=false `
            CASCADE_LIVE_DEMO_MODE=false `
            CASCADE_ACTIVE_CLUSTER_CONTEXT- `
            CASCADE_ALLOWED_CLUSTER_CONTEXT- `
            CASCADE_ALLOWED_TARGET_NAMESPACE- `
            CASCADE_REQUIRE_APPROVAL=true `
            CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }

    Invoke-Checked "Disable Command Center proxy live-demo gate" {
        kubectl -n $Namespace set env deployment/command-center-api ENABLE_DANGEROUS_ACTIONS=false
    }

    Invoke-Checked "Wait for chaos executor rollout" { kubectl -n $Namespace rollout status deployment/chaos-executor-service --timeout=180s }
    Invoke-Checked "Wait for remediation executor rollout" { kubectl -n $Namespace rollout status deployment/remediation-executor-service --timeout=180s }
    Invoke-Checked "Wait for command center API rollout" { kubectl -n $Namespace rollout status deployment/command-center-api --timeout=180s }

    Print-LiveDemoStatus
    Write-Host ""
    Write-Host "UI live-demo mode is disabled. Command Center has returned to dry-run mode."
} finally {
    Stop-StatusPortForward
}
