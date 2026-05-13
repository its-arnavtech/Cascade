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

Write-Section "Reset Phase 2.2 Redpanda Kubernetes Resources"
Write-Host "Cluster: $ClusterName"
Write-Host "Namespace: $Namespace"
Write-Host "This script deletes active broker and stream-enricher Kubernetes resources only."
Write-Host "It does not delete source files."

Write-Section "1. Tooling"
foreach ($command in @("docker", "kind", "kubectl")) {
    if (-not (Test-CommandExists $command)) {
        throw "$command is not installed or not on PATH."
    }
    Write-Host "$command found."
}

Invoke-Checked "Verify Docker is running" {
    docker info | Out-Null
    Write-Host "Docker is running."
}

Invoke-Checked "Verify kind cluster '$ClusterName' exists" {
    $clusters = @(kind get clusters)
    if ($clusters -notcontains $ClusterName) {
        throw "kind cluster '$ClusterName' does not exist. Recreate it before retrying Phase 2.2."
    }
    Write-Host "kind cluster '$ClusterName' exists."
}

Invoke-Checked "Switch kubectl context to kind-$ClusterName" {
    kubectl config use-context "kind-$ClusterName"
}

Invoke-Checked "Verify Kubernetes API is reachable" {
    kubectl cluster-info
}

Write-Section "2. Keep Namespace"
Invoke-Checked "Ensure namespace $Namespace exists" {
    kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f -
}

Write-Section "3. Delete Active Old Apache Kafka Resources"
Invoke-Checked "Delete kafka deployment/service/job and pods" {
    kubectl -n $Namespace delete deployment kafka --ignore-not-found=true
    kubectl -n $Namespace delete service kafka --ignore-not-found=true
    kubectl -n $Namespace delete job kafka-topics-init --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=kafka --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=kafka-topics-init --ignore-not-found=true
}

Write-Section "4. Delete Active Redpanda Retry Resources"
Invoke-Checked "Delete redpanda deployment/service/job and pods" {
    kubectl -n $Namespace delete deployment redpanda --ignore-not-found=true
    kubectl -n $Namespace delete service redpanda --ignore-not-found=true
    kubectl -n $Namespace delete job redpanda-topics-init --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=redpanda --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=redpanda-topics-init --ignore-not-found=true
}

Write-Section "5. Delete Old Stream Enricher Resources"
Invoke-Checked "Delete stream-enricher deployment/service and pods" {
    kubectl -n $Namespace delete deployment stream-enricher --ignore-not-found=true
    kubectl -n $Namespace delete service stream-enricher --ignore-not-found=true
    kubectl -n $Namespace delete pod -l app=stream-enricher --ignore-not-found=true
}

Write-Section "6. Preserve Observation Service"
Invoke-Checked "Show observation-service state" {
    kubectl -n $Namespace get deployment observation-service --ignore-not-found=true
    kubectl -n $Namespace get service observation-service --ignore-not-found=true
    kubectl -n $Namespace get pods -l app=observation-service -o wide
}

Write-Section "7. Result"
kubectl -n $Namespace get all
Write-Host ""
Write-Host "Reset complete. Rebuild and kind-load service images before applying Phase 2.2 manifests if the cluster was recreated."
