param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; Assert-NativeSuccess $Description }

Write-Section "Deploy Cascade Scheduler"
Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" { $clusters = @(kind get clusters); if ($clusters -notcontains $ClusterName) { throw "kind cluster '$ClusterName' does not exist." } }
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info | Out-Null }

if (-not $SkipDependencies) {
    Write-Section "Ensure Autopilot And Chaos Baseline"
    & .\scripts\deploy-autopilot.ps1 -ClusterName $ClusterName -Namespace $Namespace
    Assert-NativeSuccess "Deploy Autopilot baseline"
}

Write-Section "Build Scheduler Image"
Invoke-Checked "Build cascade-scheduler-service:dev" { docker build -f services/scheduler-service/Dockerfile -t cascade-scheduler-service:dev . }

Write-Section "Load Scheduler Image Into kind"
Invoke-Checked "kind load cascade-scheduler-service:dev" { kind load docker-image cascade-scheduler-service:dev --name $ClusterName }

Write-Section "Apply Scheduler Schema"
kubectl -n $Namespace delete job clickhouse-schema-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/clickhouse/schema-job.yaml
Assert-NativeSuccess "Apply ClickHouse schema job"
kubectl -n $Namespace wait --for=condition=complete job/clickhouse-schema-init --timeout=180s
Assert-NativeSuccess "Wait for ClickHouse schema job"

Write-Section "Deploy Scheduler Service"
kubectl apply -f infra/kubernetes/scheduler-service/
Assert-NativeSuccess "Apply scheduler-service manifests"
kubectl -n $Namespace rollout restart deployment/scheduler-service
Assert-NativeSuccess "Restart scheduler-service"
kubectl -n $Namespace rollout status deployment/scheduler-service --timeout=240s
Assert-NativeSuccess "Wait for scheduler-service rollout"

Write-Section "Scheduler Deploy Complete"
Write-Host ".\scripts\accept-scheduler.ps1"
