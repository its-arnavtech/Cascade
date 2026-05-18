param(
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 12 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 12 } }
function CH { param([string]$Query) $pod = kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath='{.items[0].metadata.name}'; kubectl -n $Namespace exec $pod -- clickhouse-client --query $Query }

try {
    Write-Section "Storage and memory Demo Health"
    foreach ($d in @("redpanda", "clickhouse", "qdrant", "telemetry-archiver", "memory-indexer", "retrieval-service")) {
        kubectl -n $Namespace get deployment $d
    }

    Start-PF "retrieval-service" "8012:8012"
    try {
        HttpJson GET "http://localhost:8012/health" | ConvertTo-Json -Depth 10
    } finally { Stop-PF }

    Write-Section "Create Storage and memory Demo Experiment"
    Start-PF "experiment-tracker-service" "8002:8002"
    try { $experiment = HttpJson POST "http://localhost:8002/experiments" @{ experiment_type = "storage-memory-demo"; target_service = "carts"; namespace = "cascade-targets"; duration_seconds = 30; chaos_mesh_resource = "storage-memory-demo" } } finally { Stop-PF }
    $experiment | ConvertTo-Json -Depth 10

    Write-Section "Wait For Archival"
    Start-Sleep -Seconds 35

    Write-Section "Build And Persist Incident Report"
    Start-PF "causal-reconstruction-service" "8005:8005"
    try { $incident = HttpJson POST "http://localhost:8005/reconstruct" @{ experiment_id = $experiment.experiment_id; lookback_seconds = 60; window_seconds = 300 } } finally { Stop-PF }
    Start-PF "topology-service" "8004:8004"
    try {
        $impact = HttpJson POST "http://localhost:8004/topology/impact" @{ root_service = "carts" }
        $topology = HttpJson GET "http://localhost:8004/topology"
    } finally { Stop-PF }
    Start-PF "incident-timeline-service" "8006:8006"
    try { $report = HttpJson POST "http://localhost:8006/report" @{ experiment = $experiment; incident = $incident; topology_impact = $impact } } finally { Stop-PF }

    Start-PF "retrieval-service" "8012:8012"
    try {
        HttpJson POST "http://localhost:8012/incidents" @{ incident = $incident } | Out-Null
        HttpJson POST "http://localhost:8012/reports" @{ incident = $incident; report = $report } | Out-Null
        HttpJson POST "http://localhost:8012/topology/snapshots" $topology | Out-Null

        Write-Section "ClickHouse Row Counts"
        HttpJson GET "http://localhost:8012/debug/counts" | ConvertTo-Json -Depth 10

        Write-Section "Recent Telemetry"
        HttpJson GET "http://localhost:8012/events/recent?limit=1" | ConvertTo-Json -Depth 20

        Write-Section "Recent Experiments"
        HttpJson GET "http://localhost:8012/experiments/recent?limit=1" | ConvertTo-Json -Depth 20

        Write-Section "Recent Incidents"
        HttpJson GET "http://localhost:8012/incidents/recent?limit=1" | ConvertTo-Json -Depth 20

        Write-Section "Similar Incident Memory"
        HttpJson POST "http://localhost:8012/memory/search" @{ query = "unhealthy pod restart latency service failure experiment root cause"; limit = 5 } | ConvertTo-Json -Depth 20
    } finally { Stop-PF }

    Write-Section "Incident Report"
    Write-Host $report.markdown
} finally {
    Stop-PF
}
