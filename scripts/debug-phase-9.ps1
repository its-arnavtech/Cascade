param(
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Continue"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }

Write-Section "Phase 9 Command Center Resources"
kubectl -n $Namespace get deploy,svc,endpoints,pods | Select-String command-center

Write-Section "Command Center API Deployment"
kubectl -n $Namespace describe deployment command-center-api

Write-Section "Command Center Deployment"
kubectl -n $Namespace describe deployment command-center

Write-Section "Recent Events"
kubectl -n $Namespace get events --sort-by=.lastTimestamp | Select-Object -Last 60

Write-Section "Command Center API Logs"
kubectl -n $Namespace logs deployment/command-center-api --tail=160

Write-Section "Command Center Logs"
kubectl -n $Namespace logs deployment/command-center --tail=120

Write-Section "In-cluster API And UI Samples"
kubectl -n $Namespace run phase9-debug-curl --rm -i --restart=Never --image=curlimages/curl:8.10.1 --image-pull-policy=IfNotPresent --command -- sh -c "set -e; echo command-center-api/health; curl -fsS http://command-center-api:8031/health; echo; echo command-center-api/ready; curl -fsS http://command-center-api:8031/ready; echo; echo command-center root; curl -fsS http://command-center:8030/ | head -c 200; echo; echo proxied retrieval counts; curl -fsS http://command-center:8030/api/retrieval/debug/counts; echo"

Write-Section "Local Access"
Write-Host "kubectl port-forward -n $Namespace svc/command-center 18300:8030"
Write-Host "Open http://localhost:18300"
