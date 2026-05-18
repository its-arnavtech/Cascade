param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$SkipAnomalyDetectionDeploy
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; Assert-NativeSuccess $Description }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; Start-Sleep -Seconds 2; return $p }
function Stop-PF { param($Process) if ($null -ne $Process -and -not $Process.HasExited) { Stop-Process -Id $Process.Id -Force } }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 30 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 60 } }

Write-Section "Deploy Cascade Knowledge and RAG"
Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" {
    $clusters = @(kind get clusters)
    if ($clusters -notcontains $ClusterName) { throw "kind cluster '$ClusterName' does not exist." }
}
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info | Out-Null }

if (-not $SkipAnomalyDetectionDeploy) {
    Write-Section "Ensure Anomaly detection Baseline"
    & .\scripts\deploy-anomaly-detection.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipStorageMemoryDeploy
    Assert-NativeSuccess "Deploy Anomaly detection baseline"
}

$images = @(
    @{ Name = "cascade-knowledge-ingestion-service:dev"; Dockerfile = "services/knowledge-ingestion-service/Dockerfile" },
    @{ Name = "cascade-knowledge-retrieval-service:dev"; Dockerfile = "services/knowledge-retrieval-service/Dockerfile" },
    @{ Name = "cascade-retrieval-service:dev"; Dockerfile = "services/retrieval-service/Dockerfile" }
)

Write-Section "Build Knowledge and RAG Images"
foreach ($image in $images) {
    Invoke-Checked "Build $($image.Name)" { docker build -f $image.Dockerfile -t $image.Name . }
}

Write-Section "Load Knowledge and RAG Images Into kind"
foreach ($image in $images) {
    Invoke-Checked "kind load $($image.Name)" { kind load docker-image $image.Name --name $ClusterName }
}

Write-Section "Apply Knowledge and RAG Schema And Collections"
kubectl -n $Namespace delete job clickhouse-schema-init --ignore-not-found=true | Out-Null
Write-Host "Cleared any stale ClickHouse schema job"
kubectl apply -f infra/kubernetes/clickhouse/schema-job.yaml
Assert-NativeSuccess "Apply ClickHouse schema job"
kubectl -n $Namespace wait --for=condition=complete job/clickhouse-schema-init --timeout=180s
Assert-NativeSuccess "Wait for ClickHouse schema job"

kubectl -n $Namespace delete job qdrant-collection-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/qdrant/collection-job.yaml
Assert-NativeSuccess "Apply Qdrant collection job"
kubectl -n $Namespace wait --for=condition=complete job/qdrant-collection-init --timeout=180s
Assert-NativeSuccess "Wait for Qdrant collection job"

Write-Section "Deploy Knowledge and RAG Services"
foreach ($path in @(
    "infra/kubernetes/retrieval-service/",
    "infra/kubernetes/knowledge-ingestion-service/",
    "infra/kubernetes/knowledge-retrieval-service/"
)) {
    kubectl apply -f $path
    Assert-NativeSuccess "Apply $path"
}

foreach ($deployment in @("retrieval-service", "knowledge-ingestion-service", "knowledge-retrieval-service")) {
    kubectl -n $Namespace rollout restart "deployment/$deployment"
    Assert-NativeSuccess "Restart $deployment"
}

Write-Section "Wait For Rollouts"
foreach ($deployment in @("retrieval-service", "knowledge-ingestion-service", "knowledge-retrieval-service")) {
    kubectl -n $Namespace rollout status "deployment/$deployment" --timeout=240s
    Assert-NativeSuccess "Wait for $deployment rollout"
}

Write-Section "Initial Knowledge Ingestion"
$pf = Start-PF "knowledge-ingestion-service" "8015:8015"
try {
    $ready = HttpJson GET "http://localhost:8015/ready"
    $ingest = HttpJson POST "http://localhost:8015/ingest/all"
    $ingest | ConvertTo-Json -Depth 20
    if ($ingest.status -ne "ok" -and $ingest.status -ne "partial") { throw "Initial ingestion failed" }
} finally {
    Stop-PF $pf
}

Write-Section "Knowledge and RAG Deploy Complete"
Write-Host ".\scripts\accept-knowledge-rag.ps1"
