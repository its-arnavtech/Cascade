param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({
        if (-not (Test-Path -LiteralPath $_ -PathType Leaf)) { throw "Target config not found: $_" }
        $true
    })]
    [string]$TargetConfig,

    [ValidatePattern('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')]
    [string]$CascadeNamespace = "cascade-system",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Read-ConfigNamespace {
    param([string]$Path)
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^namespace:\s*(?<value>[a-z0-9]([-a-z0-9]*[a-z0-9])?)\s*$') { return $Matches.value }
    }
    throw "Target config must contain namespace: <kubernetes-namespace>"
}

$resolvedConfig = (Resolve-Path -LiteralPath $TargetConfig).Path
$targetNamespace = Read-ConfigNamespace $resolvedConfig
$targetFileName = Split-Path -Leaf $resolvedConfig
$configMapName = "cascade-target-config"
$mountedPath = "/etc/cascade/target/$targetFileName"
$deployments = @(
    "topology-service",
    "chaos-planner-service",
    "chaos-executor-service",
    "remediation-recommender-service",
    "remediation-executor-service"
)

Write-Section "Configure Cascade Target Workload"
Write-Host "Target config: $resolvedConfig"
Write-Host "Target namespace: $targetNamespace"
Write-Host "Cascade namespace: $CascadeNamespace"
if ($DryRun) { Write-Host "Dry run only; no cluster objects will be changed." }

Invoke-Checked "Verify kubectl can reach Kubernetes" { kubectl version --request-timeout=5s | Out-Null }
Invoke-Checked "Verify Cascade namespace exists" { kubectl get namespace $CascadeNamespace | Out-Null }

if ($DryRun) {
    Write-Host ""
    Write-Host "Would create/update ConfigMap $configMapName from $resolvedConfig"
    foreach ($deployment in $deployments) {
        Write-Host "Would set CASCADE_TARGET_CONFIG=$mountedPath and mount ConfigMap on deployment/$deployment"
    }
    Write-Host "Would set TARGET_NAMESPACE=$targetNamespace on deployment/observation-service"
    exit 0
}

Invoke-Checked "Create target config ConfigMap" {
    kubectl -n $CascadeNamespace create configmap $configMapName --from-file=$targetFileName=$resolvedConfig --dry-run=client -o yaml | kubectl apply -f -
}

foreach ($deployment in $deployments) {
    Invoke-Checked "Set CASCADE_TARGET_CONFIG on $deployment" {
        kubectl -n $CascadeNamespace set env deployment/$deployment CASCADE_TARGET_CONFIG=$mountedPath
    }
    Invoke-Checked "Mount target config on $deployment" {
        kubectl -n $CascadeNamespace set volume deployment/$deployment --add --overwrite --name=target-config --type=configmap --configmap-name=$configMapName --mount-path=/etc/cascade/target --read-only=true
    }
}

foreach ($deployment in @("chaos-executor-service", "remediation-executor-service")) {
    Invoke-Checked "Set live-demo namespace gate on $deployment" {
        kubectl -n $CascadeNamespace set env deployment/$deployment CASCADE_ALLOWED_TARGET_NAMESPACE=$targetNamespace
    }
}

Invoke-Checked "Set observation target namespace" {
    kubectl -n $CascadeNamespace set env deployment/observation-service TARGET_NAMESPACE=$targetNamespace
}

Write-Section "Restart Updated Deployments"
foreach ($deployment in @($deployments + "observation-service")) {
    Invoke-Checked "Restart $deployment" { kubectl -n $CascadeNamespace rollout restart deployment/$deployment }
    Invoke-Checked "Wait for $deployment" { kubectl -n $CascadeNamespace rollout status deployment/$deployment --timeout=180s }
}

Write-Section "Target Configured"
Write-Host ".\scripts\validate-target.ps1 -Namespace $targetNamespace -TargetConfig $TargetConfig -Strict"
Write-Host ".\scripts\ensure-redpanda-topics.ps1"
Write-Host ".\scripts\accept-telemetry.ps1"
