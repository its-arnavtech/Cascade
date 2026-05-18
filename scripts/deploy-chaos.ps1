param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$SkipAgentsDeploy
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; Assert-NativeSuccess $Description }

Write-Section "Deploy Cascade Chaos engineering"
Invoke-Checked "Verify Docker" { docker info | Out-Null }
Invoke-Checked "Verify kind cluster" {
    $clusters = @(kind get clusters)
    if ($clusters -notcontains $ClusterName) { throw "kind cluster '$ClusterName' does not exist." }
}
Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
Invoke-Checked "Verify Kubernetes API" { kubectl cluster-info | Out-Null }
Invoke-Checked "Verify Chaos Mesh CRDs" { kubectl get crd podchaos.chaos-mesh.org | Out-Null }

if (-not $SkipAgentsDeploy) {
    Write-Section "Ensure Agent investigations Baseline"
    & .\scripts\deploy-agents.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipKnowledgeRagDeploy
    Assert-NativeSuccess "Deploy Agent investigations baseline"
}

$images = @(
    @{ Name = "cascade-chaos-planner-service:dev"; Dockerfile = "services/chaos-planner-service/Dockerfile" },
    @{ Name = "cascade-chaos-executor-service:dev"; Dockerfile = "services/chaos-executor-service/Dockerfile" },
    @{ Name = "cascade-agent-tool-gateway:dev"; Dockerfile = "services/agent-tool-gateway/Dockerfile" }
)

Write-Section "Build Chaos engineering Images"
foreach ($image in $images) {
    Invoke-Checked "Build $($image.Name)" { docker build -f $image.Dockerfile -t $image.Name . }
}

Write-Section "Load Chaos engineering Images Into kind"
foreach ($image in $images) {
    Invoke-Checked "kind load $($image.Name)" { kind load docker-image $image.Name --name $ClusterName }
}

Write-Section "Apply Chaos engineering Schema And Topics"
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

Write-Section "Deploy Chaos engineering Services"
foreach ($path in @(
    "infra/kubernetes/chaos-executor-service/rbac.yaml",
    "infra/kubernetes/chaos-planner-service/",
    "infra/kubernetes/chaos-executor-service/",
    "infra/kubernetes/agent-tool-gateway/"
)) {
    kubectl apply -f $path
    Assert-NativeSuccess "Apply $path"
}

foreach ($deployment in @("chaos-planner-service", "chaos-executor-service", "agent-tool-gateway")) {
    kubectl -n $Namespace rollout restart "deployment/$deployment"
    Assert-NativeSuccess "Restart $deployment"
}

Write-Section "Wait For Rollouts"
foreach ($deployment in @("chaos-planner-service", "chaos-executor-service", "agent-tool-gateway")) {
    kubectl -n $Namespace rollout status "deployment/$deployment" --timeout=300s
    Assert-NativeSuccess "Wait for $deployment rollout"
}

Write-Section "Chaos engineering Deploy Complete"
Write-Host ".\scripts\accept-chaos.ps1"
