param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$CreateKindIfMissing
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
    param(
        [string]$Description,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "---- $Description ----"
    & $Command
}

function Test-CommandExists {
    param([string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Section "Cascade Reset To Stable Phase 2.1"
Write-Host "Cluster: $ClusterName"
Write-Host "Namespace: $Namespace"
Write-Host "CreateKindIfMissing: $CreateKindIfMissing"

Write-Section "1. Tooling"
if (-not (Test-CommandExists "docker")) {
    throw "docker is not installed or not on PATH."
}
if (-not (Test-CommandExists "kind")) {
    throw "kind is not installed or not on PATH."
}
if (-not (Test-CommandExists "kubectl")) {
    throw "kubectl is not installed or not on PATH."
}

Invoke-Checked "Verify Docker is running" {
    docker info | Out-Null
    Write-Host "Docker is running."
}

Invoke-Checked "Verify kind cluster" {
    $clusters = @(kind get clusters)
    if ($clusters -notcontains $ClusterName) {
        if ($CreateKindIfMissing) {
            Write-Host "kind cluster '$ClusterName' missing. Creating it now."
            kind create cluster --name $ClusterName
        }
        else {
            throw "kind cluster '$ClusterName' is missing. Rerun with -CreateKindIfMissing or create it manually."
        }
    }
    else {
        Write-Host "kind cluster '$ClusterName' exists."
    }
}

Invoke-Checked "Switch kubectl context" {
    kubectl config use-context "kind-$ClusterName"
}

Invoke-Checked "Verify Kubernetes API" {
    kubectl cluster-info
}

Write-Section "2. Remove Active Phase 2.2 Kubernetes Resources"
Invoke-Checked "Keep namespace present" {
    kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f -
}

Invoke-Checked "Delete Kafka resources from $Namespace" {
    kubectl -n $Namespace delete deployment kafka --ignore-not-found=true
    kubectl -n $Namespace delete service kafka --ignore-not-found=true
    kubectl -n $Namespace delete job kafka-topics-init --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=kafka --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=kafka-topics-init --ignore-not-found=true
    kubectl -n $Namespace delete deployment redpanda --ignore-not-found=true
    kubectl -n $Namespace delete service redpanda --ignore-not-found=true
    kubectl -n $Namespace delete job redpanda-topics-init --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=redpanda --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=redpanda-topics-init --ignore-not-found=true
}

Invoke-Checked "Delete stream-enricher resources from $Namespace" {
    kubectl -n $Namespace delete deployment stream-enricher --ignore-not-found=true
    kubectl -n $Namespace delete service stream-enricher --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=stream-enricher --ignore-not-found=true
}

Write-Section "3. Rebuild Observation Service Image"
Invoke-Checked "Build cascade-observation-service:dev" {
    docker build -f services/observation-service/Dockerfile -t cascade-observation-service:dev .
}

Invoke-Checked "Load image into kind" {
    kind load docker-image cascade-observation-service:dev --name $ClusterName
}

Write-Section "4. Redeploy Observation Service Only"
Invoke-Checked "Apply observation-service manifests" {
    kubectl apply -f infra/kubernetes/observation-service/
}

Invoke-Checked "Patch imagePullPolicy to Never" {
    kubectl -n $Namespace patch deployment observation-service --type='json' -p='[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Never"}]'
}

Invoke-Checked "Disable Kafka publisher for Phase 2.1 baseline" {
    kubectl -n $Namespace set env deployment/observation-service TELEMETRY_PUBLISH_ENABLED=false
}

Invoke-Checked "Wait for observation-service rollout" {
    kubectl -n $Namespace rollout status deployment/observation-service --timeout=180s
}

Write-Section "5. Current Phase 2.1 State"
kubectl -n $Namespace get pods -o wide
kubectl -n $Namespace get deployments
kubectl -n $Namespace get svc

Write-Section "6. Test Instructions"
Write-Host "Run the Phase 2.1 acceptance test:"
Write-Host "  .\scripts\accept-phase-2-1.ps1"
Write-Host ""
Write-Host "Manual port-forward checks:"
Write-Host "  kubectl -n $Namespace port-forward svc/observation-service 8000:8000"
Write-Host "  curl http://localhost:8000/health"
Write-Host "  curl `"http://localhost:8000/metrics/raw?query=up`""
Write-Host "  curl http://localhost:8000/snapshot"
Write-Host ""
Write-Host "Reset complete. Kafka and stream-enricher source files remain in the repo, but their Kubernetes resources have been removed."
