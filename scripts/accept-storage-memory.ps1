param(
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Continue"
$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
. "$PSScriptRoot\lib\kafka-topics.ps1"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Add-Pass { param([string]$Message) $script:Passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Fail { param([string]$Message) $script:Failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Add-Warn { param([string]$Message) $script:Warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Get-KubectlJson { param([string[]]$Arguments) $r = Invoke-Kubectl $Arguments; if ($r.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($r.Text)) { return $null }; try { $r.Text | ConvertFrom-Json } catch { return $null } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 10) for ($i = 1; $i -le $Retries; $i++) { try { if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 10 } return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 10 } catch { Start-Sleep -Seconds 2 } }; return $null }
function Test-Deployment { param([string]$Name) $d = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json"); if ($null -eq $d) { Add-Fail "Deployment $Name missing"; return }; $a = [int]$d.status.availableReplicas; $r = [int]$d.spec.replicas; if ($r -gt 0 -and $a -ge $r) { Add-Pass "Deployment $Name available" } else { Add-Fail "Deployment $Name not available ($a/$r)" } }
function Test-Endpoint { param([string]$Name) $ip = (Invoke-Kubectl @("-n", $Namespace, "get", "endpoints", $Name, "-o", "jsonpath={.subsets[0].addresses[0].ip}")).Text.Trim(); if ($ip) { Add-Pass "$Name service has endpoints" } else { Add-Fail "$Name service has no endpoints" } }
function Invoke-ClickHouse { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if (-not $pod) { return "" }; (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text.Trim() }

try {
    Write-Section "Storage and memory Acceptance"
    $api = Invoke-Kubectl @("version", "--request-timeout=5s"); if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unreachable"; throw "No cluster" }

    foreach ($d in @("redpanda", "stream-enricher", "experiment-tracker-service", "topology-service", "causal-reconstruction-service", "incident-timeline-service")) { Test-Deployment $d }
    foreach ($t in @("telemetry.raw", "telemetry.enriched", "experiments.events")) {
        $topicCheck = Test-CascadeRedpandaTopic -Namespace $Namespace -Topic $t
        if ($topicCheck.Exists) { Add-Pass "Topic $t exists" } else { Add-Fail "Topic $t missing. Raw topic list: $($topicCheck.Raw)" }
    }

    foreach ($d in @("clickhouse", "qdrant", "telemetry-archiver", "memory-indexer", "retrieval-service")) { Test-Deployment $d }
    foreach ($svc in @("clickhouse", "qdrant", "telemetry-archiver", "memory-indexer", "retrieval-service")) { Test-Endpoint $svc }

    $dbs = Invoke-ClickHouse "SHOW DATABASES"
    if ($dbs -match "(?m)^cascade$") { Add-Pass "ClickHouse database cascade exists" } else { Add-Fail "ClickHouse database cascade missing" }
    $tables = Invoke-ClickHouse "SHOW TABLES FROM cascade"
    foreach ($t in @("telemetry_events", "experiment_events", "incidents", "incident_reports", "topology_snapshots")) { if ($tables -match "(?m)^$t$") { Add-Pass "ClickHouse table $t exists" } else { Add-Fail "ClickHouse table $t missing" } }

    Start-PF "qdrant" "6333:6333"
    try {
        $collection = HttpJson GET "http://localhost:6333/collections/cascade_incident_memory" $null 5
        if ($collection.result.config.params.vectors.size -eq 128) { Add-Pass "Qdrant collection cascade_incident_memory exists with 128 dimensions" } else { Add-Fail "Qdrant collection missing or wrong vector size" }
    } finally { Stop-PF }

    Start-PF "experiment-tracker-service" "8002:8002"
    try {
        $experiment = HttpJson POST "http://localhost:8002/experiments" @{ experiment_type = "storage-memory-acceptance"; target_service = "carts"; namespace = "cascade-targets"; duration_seconds = 30; chaos_mesh_resource = "storage-memory-acceptance" } 10
        if ($experiment.experiment_id) { Add-Pass "Created acceptance experiment" } else { Add-Fail "Could not create acceptance experiment" }
    } finally { Stop-PF }

    Write-Host "Waiting for Redpanda archival and memory indexing..."
    Start-Sleep -Seconds 35

    $telemetryCount = [int](Invoke-ClickHouse "SELECT count() FROM cascade.telemetry_events")
    if ($telemetryCount -gt 0) { Add-Pass "ClickHouse telemetry_events has rows ($telemetryCount)" } else { Add-Fail "ClickHouse telemetry_events has no rows" }
    $experimentCount = [int](Invoke-ClickHouse "SELECT count() FROM cascade.experiment_events")
    if ($experimentCount -gt 0) { Add-Pass "ClickHouse experiment_events has rows ($experimentCount)" } else { Add-Fail "ClickHouse experiment_events has no rows" }

    Start-PF "causal-reconstruction-service" "8005:8005"
    try { $incident = HttpJson POST "http://localhost:8005/reconstruct" @{ experiment_id = $experiment.experiment_id; lookback_seconds = 60; window_seconds = 300 } 10 } finally { Stop-PF }
    Start-PF "topology-service" "8004:8004"
    try {
        $impact = HttpJson POST "http://localhost:8004/topology/impact" @{ root_service = "carts" } 10
        $topology = HttpJson GET "http://localhost:8004/topology" $null 10
    } finally { Stop-PF }
    Start-PF "incident-timeline-service" "8006:8006"
    try { $report = HttpJson POST "http://localhost:8006/report" @{ experiment = $experiment; incident = $incident; topology_impact = $impact } 10 } finally { Stop-PF }

    Start-PF "retrieval-service" "8012:8012"
    try {
        $health = HttpJson GET "http://localhost:8012/health" $null 10
        if ($health.service -eq "retrieval-service") { Add-Pass "retrieval-service /health returns JSON" } else { Add-Fail "retrieval-service /health failed" }
        $ready = HttpJson GET "http://localhost:8012/ready" $null 10
        if ($ready.status -eq "ok") { Add-Pass "retrieval-service /ready returns ok" } else { Add-Fail "retrieval-service /ready failed" }
        $ingestedIncident = HttpJson POST "http://localhost:8012/incidents" @{ incident = $incident } 10
        $ingestedReport = HttpJson POST "http://localhost:8012/reports" @{ incident = $incident; report = $report } 10
        $snapshot = HttpJson POST "http://localhost:8012/topology/snapshots" $topology 10
        if ($ingestedIncident.incident_id -and $ingestedReport.report_id -and $snapshot.snapshot_id) { Add-Pass "Incident, report, and topology archival APIs stored data" } else { Add-Fail "Incident/report/topology archival API failed" }
        $recentEvents = HttpJson GET "http://localhost:8012/events/recent?limit=5" $null 10
        if ($recentEvents.count -ge 1) { Add-Pass "/events/recent returns stored telemetry" } else { Add-Fail "/events/recent returned no telemetry" }
        $recentExperiments = HttpJson GET "http://localhost:8012/experiments/recent?limit=5" $null 10
        if ($recentExperiments.count -ge 1) { Add-Pass "/experiments/recent returns stored experiments" } else { Add-Fail "/experiments/recent returned no experiments" }
        $recentIncidents = HttpJson GET "http://localhost:8012/incidents/recent?limit=5" $null 10
        if ($recentIncidents.count -ge 1) { Add-Pass "/incidents/recent returns stored incidents" } else { Add-Fail "/incidents/recent returned no incidents" }
        $memory = HttpJson POST "http://localhost:8012/memory/search" @{ query = "unhealthy pod restart latency service failure experiment root cause"; limit = 5 } 10
        if ($memory.count -ge 1) { Add-Pass "/memory/search returns similar memories" } else { Add-Fail "/memory/search returned no memories" }
        $detail = HttpJson GET "http://localhost:8012/incidents/$($ingestedIncident.incident_id)" $null 10
        if ($detail.incident.incident_id) { Add-Pass "/incidents/{incident_id} returns incident detail" } else { Add-Fail "/incidents/{incident_id} failed" }
        $latestTopology = HttpJson GET "http://localhost:8012/topology/snapshot/latest" $null 10
        if ($latestTopology.snapshot.snapshot_id) { Add-Pass "/topology/snapshot/latest returns snapshot" } else { Add-Fail "/topology/snapshot/latest failed" }
    } finally { Stop-PF }

    Start-PF "qdrant" "6333:6333"
    try {
        $count = HttpJson POST "http://localhost:6333/collections/cascade_incident_memory/points/count" @{ exact = $true } 10
        if ($count.result.count -gt 0) { Add-Pass "Qdrant has indexed points ($($count.result.count))" } else { Add-Fail "Qdrant has no indexed points" }
    } finally { Stop-PF }
} catch {
    Add-Warn "Acceptance stopped early: $($_.Exception.Message)"
} finally {
    Stop-PF
}

Write-Section "Final Result"
Write-Host "Passed:"; if ($Passed.Count -eq 0) { Write-Host "  - none" } else { foreach ($p in $Passed) { Write-Host "  - $p" } }
Write-Host ""; Write-Host "Warnings:"; if ($Warnings.Count -eq 0) { Write-Host "  - none" } else { foreach ($w in $Warnings) { Write-Host "  - $w" } }
Write-Host ""; Write-Host "Failed:"; if ($Failed.Count -eq 0) { Write-Host "  - none" } else { foreach ($f in $Failed) { Write-Host "  - $f" } }
Write-Host ""
if ($Failed.Count -eq 0) { Write-Host "STORAGE AND MEMORY ACCEPTANCE: PASS"; exit 0 }
Write-Host "STORAGE AND MEMORY ACCEPTANCE: FAIL"
exit 1
