param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$SkipRemediationDeploy
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; Assert-NativeSuccess $Description }

Write-Section "Deploy Cascade Autopilot"
Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" { $clusters = @(kind get clusters); if ($clusters -notcontains $ClusterName) { throw "kind cluster '$ClusterName' does not exist." } }
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info | Out-Null }

if (-not $SkipRemediationDeploy) {
    Write-Section "Ensure Remediation Baseline"
    & .\scripts\deploy-remediation.ps1 -ClusterName $ClusterName -Namespace $Namespace
    Assert-NativeSuccess "Deploy Remediation baseline"
}

Write-Section "Build Autopilot Image"
Invoke-Checked "Build cascade-autopilot-service:dev" { docker build -f services/autopilot-service/Dockerfile -t cascade-autopilot-service:dev . }

Write-Section "Load Autopilot Image Into kind"
Invoke-Checked "kind load cascade-autopilot-service:dev" { kind load docker-image cascade-autopilot-service:dev --name $ClusterName }

Write-Section "Apply Autopilot Schema And Topics"
kubectl -n $Namespace delete job clickhouse-schema-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/clickhouse/schema-job.yaml
Assert-NativeSuccess "Apply ClickHouse schema job"
kubectl -n $Namespace wait --for=condition=complete job/clickhouse-schema-init --timeout=180s
Assert-NativeSuccess "Wait for ClickHouse schema job"

kubectl -n $Namespace delete job redpanda-topics-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/redpanda/topics-job.yaml
Assert-NativeSuccess "Apply Redpanda topics job"
kubectl -n $Namespace wait --for=condition=complete job/redpanda-topics-init --timeout=180s
Assert-NativeSuccess "Wait for Redpanda topics job"

Write-Section "Deploy Autopilot Service"
kubectl apply -f infra/kubernetes/autopilot-service/
Assert-NativeSuccess "Apply autopilot-service manifests"
kubectl -n $Namespace rollout restart deployment/autopilot-service
Assert-NativeSuccess "Restart autopilot-service"
kubectl -n $Namespace rollout status deployment/autopilot-service --timeout=240s
Assert-NativeSuccess "Wait for autopilot-service rollout"

Write-Section "Autopilot Deploy Complete"
Write-Host ".\scripts\accept-autopilot.ps1"
