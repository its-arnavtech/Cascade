param(
    [string]$Namespace = "cascade-system",
    [string]$ServiceName = "observation-service",
    [int]$LocalPort = 8000
)

$ErrorActionPreference = "Stop"

Write-Host "Port-forwarding service/$ServiceName in namespace $Namespace to localhost:$LocalPort"
Write-Host "Press Ctrl+C to stop the port-forward."
Write-Host ""
Write-Host "In another terminal, run:"
Write-Host "  curl http://localhost:$LocalPort/health"
Write-Host "  curl http://localhost:$LocalPort/snapshot"
Write-Host "  curl `"http://localhost:$LocalPort/metrics/raw?query=up`""
Write-Host ""

kubectl -n $Namespace port-forward "svc/$ServiceName" "$LocalPort`:8000"
