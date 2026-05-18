param(
    [string]$ClusterContext = "kind-cascade",
    [string]$Namespace = "chaos-mesh",
    [switch]$ConfirmLocalKind,
    [switch]$AllowContextOverride
)

$ErrorActionPreference = "Stop"

function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }

$context = (& kubectl config current-context 2>&1).Trim()
if (-not $ConfirmLocalKind) {
    throw "Refusing to install Chaos Mesh without -ConfirmLocalKind."
}
if ($context -ne $ClusterContext -and -not $AllowContextOverride) {
    throw "Refusing to install Chaos Mesh on context '$context'. Expected '$ClusterContext'. Use -AllowContextOverride only for an intentional local demo override."
}
if (-not (Get-Command helm -ErrorAction SilentlyContinue)) {
    throw "Helm is required for this install path. Install Helm, then rerun this script."
}

Invoke-Checked "Add Chaos Mesh Helm repo" { helm repo add chaos-mesh https://charts.chaos-mesh.org }
Invoke-Checked "Update Helm repos" { helm repo update }
Invoke-Checked "Create namespace $Namespace" { kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f - }
Invoke-Checked "Install or upgrade Chaos Mesh" {
    helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh `
        --namespace $Namespace `
        --set chaosDaemon.runtime=containerd `
        --set chaosDaemon.socketPath=/run/containerd/containerd.sock `
        --set dashboard.create=false
}
Invoke-Checked "Wait for Chaos Mesh controller" { kubectl -n $Namespace rollout status deployment/chaos-controller-manager --timeout=180s }

& "$PSScriptRoot\verify-chaos-mesh.ps1" -ExpectedContext $ClusterContext
if ($LASTEXITCODE -ne 0) { throw "Chaos Mesh verification failed" }
