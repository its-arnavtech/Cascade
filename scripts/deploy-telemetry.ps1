param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Stop"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "============================================================"
}

function Invoke-Checked {
    param([string]$Description, [scriptblock]$Command)
    Write-Host ""
    Write-Host "---- $Description ----"
    & $Command
}
function Assert-NativeSuccess {
    param([string]$Description)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}
function Clear-RedpandaRollout {
    Write-Host "Clearing stale Redpanda ReplicaSets and pods before applying the single-broker deployment."
    kubectl -n $Namespace scale deployment/redpanda --replicas=0 --timeout=30s 2>$null
    $LASTEXITCODE = 0
    kubectl -n $Namespace delete pod -l app=redpanda --grace-period=0 --force --ignore-not-found=true
    kubectl -n $Namespace delete rs -l app=redpanda --ignore-not-found=true
}


Write-Section "Deploy Cascade Telemetry pipeline"

Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" {
    $clusters = @(kind get clusters)
    if ($clusters -notcontains $ClusterName) {
        throw "kind cluster '$ClusterName' does not exist."
    }
}
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info }
Invoke-Checked "Ensure namespace" { kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f - }

$images = @(
    @{ Name = "cascade-observation-service:dev"; Dockerfile = "services/observation-service/Dockerfile" },
    @{ Name = "cascade-stream-enricher:dev"; Dockerfile = "services/stream-enricher/Dockerfile" },
    @{ Name = "cascade-experiment-tracker-service:dev"; Dockerfile = "services/experiment-tracker-service/Dockerfile" },
    @{ Name = "cascade-causal-reconstruction-service:dev"; Dockerfile = "services/causal-reconstruction-service/Dockerfile" },
    @{ Name = "cascade-topology-service:dev"; Dockerfile = "services/topology-service/Dockerfile" },
    @{ Name = "cascade-incident-timeline-service:dev"; Dockerfile = "services/incident-timeline-service/Dockerfile" }
)

Write-Section "Build Images"
foreach ($image in $images) {
    Invoke-Checked "Build $($image.Name)" {
        docker build -f $image.Dockerfile -t $image.Name .
    }
}

Write-Section "Load Images Into kind"
foreach ($image in $images) {
    Invoke-Checked "kind load $($image.Name)" {
        kind load docker-image $image.Name --name $ClusterName
    }
}

Write-Section "Deploy Redpanda"
try { Clear-RedpandaRollout } catch { Write-Host "WARN: Redpanda pre-scale skipped (fresh cluster)" }
kubectl apply -f infra/kubernetes/redpanda/pvc.yaml
Assert-NativeSuccess "Apply Redpanda PVC"
kubectl apply -f infra/kubernetes/redpanda/deployment.yaml
Assert-NativeSuccess "Apply Redpanda deployment"
kubectl apply -f infra/kubernetes/redpanda/service.yaml
Assert-NativeSuccess "Apply Redpanda service"
kubectl -n $Namespace rollout status deployment/redpanda --timeout=240s
Assert-NativeSuccess "Wait for Redpanda rollout"

Write-Section "Create Topics"
kubectl -n $Namespace delete job redpanda-topics-init --ignore-not-found=true
kubectl apply -f infra/kubernetes/redpanda/topics-job.yaml
Assert-NativeSuccess "Apply Redpanda topics job"
kubectl -n $Namespace wait --for=condition=complete job/redpanda-topics-init --timeout=180s
Assert-NativeSuccess "Wait for Redpanda topics job"

Write-Section "Deploy Services"
foreach ($path in @(
    "infra/kubernetes/observation-service/",
    "infra/kubernetes/stream-enricher/",
    "infra/kubernetes/experiment-tracker-service/",
    "infra/kubernetes/topology-service/",
    "infra/kubernetes/causal-reconstruction-service/",
    "infra/kubernetes/incident-timeline-service/"
)) {
    kubectl apply -f $path
}

Write-Section "Wait For Rollouts"
foreach ($deployment in @(
    "observation-service",
    "stream-enricher",
    "experiment-tracker-service",
    "topology-service",
    "causal-reconstruction-service",
    "incident-timeline-service"
)) {
    kubectl -n $Namespace rollout status "deployment/$deployment" --timeout=180s
}

Write-Section "Next Step"
Write-Host ".\scripts\accept-telemetry.ps1"
