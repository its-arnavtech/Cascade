param([string]$Namespace = "cascade-system")

$ErrorActionPreference = "Continue"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url) try { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 8 } catch { $_.Exception.Message } }
function CH { param([string]$Query) $pod = kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath='{.items[0].metadata.name}' 2>$null; if ($pod) { kubectl -n $Namespace exec $pod -- clickhouse-client --query $Query } }

try {
    Write-Section "Namespaces"; kubectl get namespaces
    Write-Section "Pods"; kubectl -n $Namespace get pods -o wide
    Write-Section "Deployments"; kubectl -n $Namespace get deployments
    Write-Section "Services"; kubectl -n $Namespace get services
    Write-Section "Endpoints"; kubectl -n $Namespace get endpoints
    Write-Section "Recent Events"; kubectl -n $Namespace get events --sort-by=.lastTimestamp
    Write-Section "Redpanda Topics"
    $rpPod = kubectl -n $Namespace get pod -l app=redpanda -o jsonpath='{.items[0].metadata.name}'
    if ($rpPod) { kubectl -n $Namespace exec $rpPod -- rpk -X brokers=localhost:9092 topic list }
    Write-Section "ClickHouse Phase 4 Counts"
    foreach ($table in @("telemetry_feature_windows", "anomaly_events", "model_runs")) { Write-Host "$table=$(CH "SELECT count() FROM cascade.$table")" }
    Write-Section "Recent Feature Windows"; CH "SELECT service, namespace, workload, window_start, event_count, unhealthy_rate, restart_rate FROM cascade.telemetry_feature_windows ORDER BY window_end DESC LIMIT 10"
    Write-Section "Recent Anomalies"; CH "SELECT service, severity, risk_score, explanation FROM cascade.anomaly_events ORDER BY detected_at DESC LIMIT 10"
    Write-Section "Model Runs"; CH "SELECT started_at, windows_scored, anomalies_detected, status FROM cascade.model_runs ORDER BY started_at DESC LIMIT 10"
    foreach ($svc in @("feature-extractor-service", "anomaly-detector-service", "retrieval-service")) {
        Write-Section "$svc logs"; kubectl -n $Namespace logs "deployment/$svc" --tail=120
    }
    Start-PF "feature-extractor-service" "8013:8013"
    try { Write-Section "Feature Extractor Health"; HttpJson GET "http://localhost:8013/health" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8013/ready" | ConvertTo-Json -Depth 10 } finally { Stop-PF }
    Start-PF "anomaly-detector-service" "8014:8014"
    try { Write-Section "Anomaly Detector Health"; HttpJson GET "http://localhost:8014/health" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8014/ready" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8014/models/status" | ConvertTo-Json -Depth 20 } finally { Stop-PF }
    Start-PF "retrieval-service" "8012:8012"
    try { Write-Section "Retrieval Health"; HttpJson GET "http://localhost:8012/health" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8012/ready" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8012/debug/counts" | ConvertTo-Json -Depth 10 } finally { Stop-PF }
} finally {
    Stop-PF
}
