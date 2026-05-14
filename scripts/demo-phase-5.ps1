param([string]$Namespace = "cascade-system")

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 180 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 180 } }

try {
    Write-Section "Phase 5 Demo Health"
    kubectl -n $Namespace get deployments retrieval-service feature-extractor-service anomaly-detector-service knowledge-ingestion-service knowledge-retrieval-service

    Write-Section "Phase 4 Anomaly System"
    Start-PF "retrieval-service" "8012:8012"
    try {
        HttpJson GET "http://localhost:8012/anomalies/recent?limit=3" | ConvertTo-Json -Depth 20
    } finally { Stop-PF }

    Write-Section "Knowledge Ingestion"
    Start-PF "knowledge-ingestion-service" "8015:8015"
    try {
        HttpJson POST "http://localhost:8015/ingest/all" | ConvertTo-Json -Depth 20
        HttpJson GET "http://localhost:8015/stats" | ConvertTo-Json -Depth 10
        HttpJson GET "http://localhost:8015/runs/recent?limit=3" | ConvertTo-Json -Depth 20
    } finally { Stop-PF }

    Write-Section "Knowledge Search And Context"
    Start-PF "knowledge-retrieval-service" "8016:8016"
    try {
        foreach ($query in @(
            "pod restart unhealthy service anomaly",
            "how do I investigate recommendationservice restart anomaly",
            "what does Cascade know about service latency",
            "which stored incidents mention root cause or affected services"
        )) {
            Write-Host ""; Write-Host "Query: $query"
            HttpJson POST "http://localhost:8016/knowledge/search" @{ query = $query; limit = 3; filters = @{} } | ConvertTo-Json -Depth 20
        }
        HttpJson POST "http://localhost:8016/knowledge/context" @{ query = "how do I investigate recommendationservice restart anomaly"; limit = 8; filters = @{} } | ConvertTo-Json -Depth 20
    } finally { Stop-PF }

    Write-Section "Retrieval-Service Integration"
    Start-PF "retrieval-service" "8012:8012"
    try {
        HttpJson GET "http://localhost:8012/knowledge/stats" | ConvertTo-Json -Depth 10
        HttpJson POST "http://localhost:8012/knowledge/search" @{ query = "pod restart unhealthy service anomaly"; limit = 3; filters = @{} } | ConvertTo-Json -Depth 20
        HttpJson GET "http://localhost:8012/debug/counts" | ConvertTo-Json -Depth 10
    } finally { Stop-PF }
} finally {
    Stop-PF
}
