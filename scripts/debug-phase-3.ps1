param(
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Continue"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) try { if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 8 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20) -TimeoutSec 8 } } catch { $_.Exception.Message } }
function CH { param([string]$Query) $pod = kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath='{.items[0].metadata.name}' 2>$null; if ($pod) { kubectl -n $Namespace exec $pod -- clickhouse-client --query $Query } }

try {
    Write-Section "Namespaces"; kubectl get namespaces
    Write-Section "Pods"; kubectl -n $Namespace get pods -o wide
    Write-Section "Deployments"; kubectl -n $Namespace get deployments
    Write-Section "Services"; kubectl -n $Namespace get services
    Write-Section "Endpoints"; kubectl -n $Namespace get endpoints
    Write-Section "Recent Events"; kubectl -n $Namespace get events --sort-by=.lastTimestamp

    foreach ($svc in @("clickhouse", "qdrant", "telemetry-archiver", "memory-indexer", "retrieval-service", "redpanda")) {
        Write-Section "$svc logs"
        kubectl -n $Namespace logs "deployment/$svc" --tail=120
    }

    Write-Section "Redpanda Topics"
    $rpPod = kubectl -n $Namespace get pod -l app=redpanda -o jsonpath='{.items[0].metadata.name}'
    if ($rpPod) { kubectl -n $Namespace exec $rpPod -- rpk -X brokers=localhost:9092 topic list }

    Write-Section "ClickHouse Tables"
    CH "SHOW TABLES FROM cascade"
    Write-Section "ClickHouse Counts"
    foreach ($table in @("telemetry_events", "experiment_events", "incidents", "incident_reports", "topology_snapshots")) { Write-Host "$table=$(CH "SELECT count() FROM cascade.$table")" }

    Write-Section "Qdrant Collection"
    Start-PF "qdrant" "6333:6333"
    try {
        HttpJson GET "http://localhost:6333/collections/cascade_incident_memory" | ConvertTo-Json -Depth 20
        HttpJson POST "http://localhost:6333/collections/cascade_incident_memory/points/count" @{ exact = $true } | ConvertTo-Json -Depth 20
    } finally { Stop-PF }

    Write-Section "Retrieval Service Health"
    Start-PF "retrieval-service" "8012:8012"
    try {
        HttpJson GET "http://localhost:8012/health" | ConvertTo-Json -Depth 20
        HttpJson GET "http://localhost:8012/ready" | ConvertTo-Json -Depth 20
        HttpJson GET "http://localhost:8012/debug/counts" | ConvertTo-Json -Depth 20
    } finally { Stop-PF }
} finally {
    Stop-PF
}
