param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$SkipChaosDeploy
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; Assert-NativeSuccess $Description }

Write-Section "Deploy Cascade Remediation"
Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" { $clusters = @(kind get clusters); if ($clusters -notcontains $ClusterName) { throw "kind cluster '$ClusterName' does not exist." } }
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info | Out-Null }

if (-not $SkipChaosDeploy) {
    Write-Section "Ensure Chaos engineering Baseline"
    & .\scripts\deploy-chaos.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipAgentsDeploy
    Assert-NativeSuccess "Deploy Chaos engineering baseline"
}

$images = @(
    @{ Name = "cascade-remediation-recommender-service:dev"; Dockerfile = "services/remediation-recommender-service/Dockerfile" },
    @{ Name = "cascade-approval-service:dev"; Dockerfile = "services/approval-service/Dockerfile" },
    @{ Name = "cascade-remediation-executor-service:dev"; Dockerfile = "services/remediation-executor-service/Dockerfile" },
    @{ Name = "cascade-agent-tool-gateway:dev"; Dockerfile = "services/agent-tool-gateway/Dockerfile" }
)

Write-Section "Build Remediation Images"
foreach ($image in $images) { Invoke-Checked "Build $($image.Name)" { docker build -f $image.Dockerfile -t $image.Name . } }

Write-Section "Load Remediation Images Into kind"
foreach ($image in $images) { Invoke-Checked "kind load $($image.Name)" { kind load docker-image $image.Name --name $ClusterName } }

Write-Section "Apply Remediation Schema And Topics"
kubectl -n $Namespace delete job clickhouse-schema-init --ignore-not-found=true | Out-Null
Write-Host "Cleared any stale ClickHouse schema job"
kubectl apply -f infra/kubernetes/clickhouse/schema-job.yaml
Assert-NativeSuccess "Apply ClickHouse schema job"
kubectl -n $Namespace wait --for=condition=complete job/clickhouse-schema-init --timeout=180s
Assert-NativeSuccess "Wait for ClickHouse schema job"

kubectl -n $Namespace delete job redpanda-topics-init --ignore-not-found=true | Out-Null
kubectl apply -f infra/kubernetes/redpanda/topics-job.yaml
Assert-NativeSuccess "Apply Redpanda topics job"
kubectl -n $Namespace wait --for=condition=complete job/redpanda-topics-init --timeout=180s
Assert-NativeSuccess "Wait for Redpanda topics job"

Write-Section "Deploy Remediation Services"
foreach ($path in @(
    "infra/kubernetes/remediation-executor-service/rbac.yaml",
    "infra/kubernetes/remediation-recommender-service/",
    "infra/kubernetes/approval-service/",
    "infra/kubernetes/remediation-executor-service/",
    "infra/kubernetes/agent-tool-gateway/"
)) {
    kubectl apply -f $path
    Assert-NativeSuccess "Apply $path"
}

foreach ($deployment in @("remediation-recommender-service", "approval-service", "remediation-executor-service", "agent-tool-gateway")) {
    kubectl -n $Namespace rollout restart "deployment/$deployment"
    Assert-NativeSuccess "Restart $deployment"
}

Write-Section "Wait For Rollouts"
foreach ($deployment in @("remediation-recommender-service", "approval-service", "remediation-executor-service", "agent-tool-gateway")) {
    kubectl -n $Namespace rollout status "deployment/$deployment" --timeout=300s
    Assert-NativeSuccess "Wait for $deployment rollout"
}

Write-Section "Remediation Deploy Complete"
Write-Host ".\scripts\accept-remediation.ps1"

