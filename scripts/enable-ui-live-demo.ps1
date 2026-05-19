param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [string]$ExpectedContext = "kind-cascade",
    [switch]$ConfirmLocalKind
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

function Assert-LocalKind {
    if (-not $ConfirmLocalKind) {
        throw "Pass -ConfirmLocalKind to confirm this is a local kind live-demo setup."
    }
    $context = kubectl config current-context
    if ($LASTEXITCODE -ne 0) { throw "Could not read kubectl context" }
    if ($context.Trim() -ne $ExpectedContext) {
        throw "Refusing to enable UI live demo on context '$context'. Expected '$ExpectedContext'."
    }
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
    Assert-LocalKind
    Invoke-Checked "Verify cascade system namespace" { kubectl get namespace $Namespace }
    Invoke-Checked "Verify target namespace" { kubectl get namespace $TargetNamespace }

    Write-Host ""
    Write-Host "---- Check Chaos Mesh CRDs ----"
    kubectl get crd podchaos.chaos-mesh.org
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Chaos Mesh PodChaos CRD was not found. Install Chaos Mesh before running real chaos demos."
        Write-Host "Suggested: powershell -ExecutionPolicy Bypass -File .\scripts\install-chaos-mesh.ps1"
    }

    Invoke-Checked "Enable chaos executor live-demo flags" {
        kubectl -n $Namespace set env deployment/chaos-executor-service `
            ENABLE_DANGEROUS_ACTIONS=true `
            ENABLE_REAL_CHAOS=true `
            CASCADE_LIVE_DEMO_MODE=true `
            CASCADE_ACTIVE_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_TARGET_NAMESPACE=$TargetNamespace `
            CASCADE_REQUIRE_APPROVAL=true `
            CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }

    Invoke-Checked "Enable remediation executor live-demo flags" {
        kubectl -n $Namespace set env deployment/remediation-executor-service `
            EXECUTION_ENABLED=true `
            ENABLE_DANGEROUS_ACTIONS=true `
            ENABLE_REAL_REMEDIATION=true `
            CASCADE_LIVE_DEMO_MODE=true `
            CASCADE_ACTIVE_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_CLUSTER_CONTEXT=$ExpectedContext `
            CASCADE_ALLOWED_TARGET_NAMESPACE=$TargetNamespace `
            CASCADE_REQUIRE_APPROVAL=true `
            CASCADE_REQUIRE_DRY_RUN_FIRST=true
    }

    Invoke-Checked "Enable Command Center proxy live-demo gate" {
        kubectl -n $Namespace set env deployment/command-center-api ENABLE_DANGEROUS_ACTIONS=true
    }

    Invoke-Checked "Wait for chaos executor rollout" { kubectl -n $Namespace rollout status deployment/chaos-executor-service --timeout=180s }
    Invoke-Checked "Wait for remediation executor rollout" { kubectl -n $Namespace rollout status deployment/remediation-executor-service --timeout=180s }
    Invoke-Checked "Wait for command center API rollout" { kubectl -n $Namespace rollout status deployment/command-center-api --timeout=180s }

    Print-LiveDemoStatus
    Write-Host ""
    Write-Host "UI live-demo mode is enabled for local kind target namespace '$TargetNamespace'."
} finally {
    Stop-StatusPortForward
}
