param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$SkipTelemetryDeploy
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Checked {
    param([string]$Description, [scriptblock]$Command)
    Write-Host ""
    Write-Host "---- $Description ----"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}
function Assert-NativeSuccess {
    param([string]$Description)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

Write-Section "Deploy Cascade Storage and memory"
Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" {
    $clusters = @(kind get clusters)
    if ($clusters -notcontains $ClusterName) { throw "kind cluster '$ClusterName' does not exist." }
}
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info | Out-Null }
Invoke-Checked "Ensure namespace" { kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null }

if (-not $SkipTelemetryDeploy) {
    Write-Section "Ensure Telemetry pipeline Baseline"
    & .\scripts\deploy-telemetry.ps1 -ClusterName $ClusterName -Namespace $Namespace
}

$images = @(
    @{ Name = "cascade-telemetry-archiver:dev"; Dockerfile = "services/telemetry-archiver/Dockerfile" },
    @{ Name = "cascade-memory-indexer:dev"; Dockerfile = "services/memory-indexer/Dockerfile" },
    @{ Name = "cascade-retrieval-service:dev"; Dockerfile = "services/retrieval-service/Dockerfile" }
)

Write-Section "Build Storage and memory Images"
foreach ($image in $images) {
    Invoke-Checked "Build $($image.Name)" { docker build -f $image.Dockerfile -t $image.Name . }
}

Write-Section "Load Storage and memory Images Into kind"
foreach ($image in $images) {
    Invoke-Checked "kind load $($image.Name)" { kind load docker-image $image.Name --name $ClusterName }
}

Write-Section "Deploy ClickHouse"
kubectl apply -f infra/kubernetes/clickhouse/deployment.yaml
Assert-NativeSuccess "Apply ClickHouse deployment"
kubectl apply -f infra/kubernetes/clickhouse/service.yaml
Assert-NativeSuccess "Apply ClickHouse service"
kubectl -n $Namespace rollout status deployment/clickhouse --timeout=240s
Assert-NativeSuccess "Wait for ClickHouse rollout"
kubectl -n $Namespace delete job clickhouse-schema-init --ignore-not-found=true | Out-Null
Write-Host "Cleared any stale ClickHouse schema job"
kubectl apply -f infra/kubernetes/clickhouse/schema-job.yaml
Assert-NativeSuccess "Apply ClickHouse schema job"
kubectl -n $Namespace wait --for=condition=complete job/clickhouse-schema-init --timeout=180s
Assert-NativeSuccess "Wait for ClickHouse schema job"

Write-Section "Deploy Qdrant"
kubectl apply -f infra/kubernetes/qdrant/deployment.yaml
Assert-NativeSuccess "Apply Qdrant deployment"
kubectl apply -f infra/kubernetes/qdrant/service.yaml
Assert-NativeSuccess "Apply Qdrant service"
kubectl -n $Namespace rollout status deployment/qdrant --timeout=240s
Assert-NativeSuccess "Wait for Qdrant rollout"
kubectl -n $Namespace delete job qdrant-collection-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/qdrant/collection-job.yaml
Assert-NativeSuccess "Apply Qdrant collection job"
kubectl -n $Namespace wait --for=condition=complete job/qdrant-collection-init --timeout=180s
Assert-NativeSuccess "Wait for Qdrant collection job"

Write-Section "Deploy Storage and memory Services"
foreach ($path in @(
    "infra/kubernetes/telemetry-archiver/",
    "infra/kubernetes/memory-indexer/",
    "infra/kubernetes/retrieval-service/"
)) {
    kubectl apply -f $path
    Assert-NativeSuccess "Apply $path"
}

Write-Section "Wait For Storage and memory Rollouts"
foreach ($deployment in @("telemetry-archiver", "memory-indexer", "retrieval-service")) {
    kubectl -n $Namespace rollout status "deployment/$deployment" --timeout=180s
    Assert-NativeSuccess "Wait for $deployment rollout"
}

Write-Section "Storage and memory Deploy Complete"
Write-Host ".\scripts\accept-storage-memory.ps1"
