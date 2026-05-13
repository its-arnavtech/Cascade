param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$SkipPhase3Deploy
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; Assert-NativeSuccess $Description }

Write-Section "Deploy Cascade Phase 4"
Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" {
    $clusters = @(kind get clusters)
    if ($clusters -notcontains $ClusterName) { throw "kind cluster '$ClusterName' does not exist." }
}
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info | Out-Null }

if (-not $SkipPhase3Deploy) {
    Write-Section "Ensure Phase 3 Baseline"
    & .\scripts\deploy-phase-3.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipPhase2Deploy
    Assert-NativeSuccess "Deploy Phase 3 baseline"
}

$images = @(
    @{ Name = "cascade-feature-extractor-service:dev"; Dockerfile = "services/feature-extractor-service/Dockerfile" },
    @{ Name = "cascade-anomaly-detector-service:dev"; Dockerfile = "services/anomaly-detector-service/Dockerfile" },
    @{ Name = "cascade-retrieval-service:dev"; Dockerfile = "services/retrieval-service/Dockerfile" }
)

Write-Section "Build Phase 4 Images"
foreach ($image in $images) {
    Invoke-Checked "Build $($image.Name)" { docker build -f $image.Dockerfile -t $image.Name . }
}

Write-Section "Load Phase 4 Images Into kind"
foreach ($image in $images) {
    Invoke-Checked "kind load $($image.Name)" { kind load docker-image $image.Name --name $ClusterName }
}

Write-Section "Apply Phase 4 Schema"
kubectl -n $Namespace delete job clickhouse-schema-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/clickhouse/schema-job.yaml
Assert-NativeSuccess "Apply ClickHouse schema job"
kubectl -n $Namespace wait --for=condition=complete job/clickhouse-schema-init --timeout=180s
Assert-NativeSuccess "Wait for ClickHouse schema job"

Write-Section "Ensure Redpanda Topics"
kubectl -n $Namespace delete job redpanda-topics-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/redpanda/topics-job.yaml
Assert-NativeSuccess "Apply Redpanda topics job"
kubectl -n $Namespace wait --for=condition=complete job/redpanda-topics-init --timeout=180s
Assert-NativeSuccess "Wait for Redpanda topics job"

Write-Section "Deploy Phase 4 Services"
foreach ($path in @(
    "infra/kubernetes/feature-extractor-service/",
    "infra/kubernetes/anomaly-detector-service/",
    "infra/kubernetes/retrieval-service/"
)) {
    kubectl apply -f $path
    Assert-NativeSuccess "Apply $path"
}

foreach ($deployment in @("feature-extractor-service", "anomaly-detector-service", "retrieval-service")) {
    kubectl -n $Namespace rollout restart "deployment/$deployment"
    Assert-NativeSuccess "Restart $deployment for freshly loaded kind image"
}

Write-Section "Wait For Rollouts"
foreach ($deployment in @("feature-extractor-service", "anomaly-detector-service", "retrieval-service")) {
    kubectl -n $Namespace rollout status "deployment/$deployment" --timeout=240s
    Assert-NativeSuccess "Wait for $deployment rollout"
}

Write-Section "Phase 4 Deploy Complete"
Write-Host ".\scripts\accept-phase-4.ps1"
