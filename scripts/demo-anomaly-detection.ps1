param([string]$Namespace = "cascade-system", [switch]$Synthetic)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 15 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 15 } }

try {
    Write-Section "Anomaly detection Demo Health"
    kubectl -n $Namespace get deployments clickhouse qdrant retrieval-service feature-extractor-service anomaly-detector-service

    Start-PF "retrieval-service" "8012:8012"
    try { HttpJson GET "http://localhost:8012/debug/counts" | ConvertTo-Json -Depth 10 } finally { Stop-PF }

    Write-Section "Feature Extraction"
    Start-PF "feature-extractor-service" "8013:8013"
    try {
        $extract = HttpJson POST "http://localhost:8013/extract" @{ lookback_minutes = 120; window_seconds = 300 }
        $extract | ConvertTo-Json -Depth 10
        if ($Synthetic) {
            Write-Host "Inserting clearly labeled synthetic Anomaly detection demo anomaly window."
            HttpJson POST "http://localhost:8013/features/synthetic" | ConvertTo-Json -Depth 10
        }
        HttpJson GET "http://localhost:8013/features/recent?limit=3" | ConvertTo-Json -Depth 20
    } finally { Stop-PF }

    Write-Section "Anomaly Detection"
    Start-PF "anomaly-detector-service" "8014:8014"
    try {
        HttpJson GET "http://localhost:8014/models/status" | ConvertTo-Json -Depth 20
        $detectBody = @{ lookback_minutes = 240; publish = $true }
        if ($Synthetic) {
            $detectBody["service"] = "anomaly-synthetic-service"
        }
        HttpJson POST "http://localhost:8014/detect" $detectBody | ConvertTo-Json -Depth 20
        HttpJson GET "http://localhost:8014/anomalies/recent?limit=3" | ConvertTo-Json -Depth 20
    } finally { Stop-PF }

    Write-Section "Retrieval APIs"
    Start-PF "retrieval-service" "8012:8012"
    try {
        HttpJson GET "http://localhost:8012/features/recent?limit=2" | ConvertTo-Json -Depth 20
        HttpJson GET "http://localhost:8012/anomalies/recent?limit=2" | ConvertTo-Json -Depth 20
        HttpJson GET "http://localhost:8012/debug/counts" | ConvertTo-Json -Depth 10
    } finally { Stop-PF }
} finally {
    Stop-PF
}
