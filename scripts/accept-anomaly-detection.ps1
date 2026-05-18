param([string]$Namespace = "cascade-system")

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
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 10) for ($i = 1; $i -le $Retries; $i++) { try { if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 12 } return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 12 } catch { Start-Sleep -Seconds 2 } }; return $null }
function Test-Deployment { param([string]$Name) $d = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json"); if ($null -eq $d) { Add-Fail "Deployment $Name missing"; return }; $a = [int]$d.status.availableReplicas; $r = [int]$d.spec.replicas; if ($r -gt 0 -and $a -ge $r) { Add-Pass "Deployment $Name available" } else { Add-Fail "Deployment $Name not available ($a/$r)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if (-not $pod) { return "" }; (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text.Trim() }

try {
    Write-Section "Anomaly detection Acceptance"
    $api = Invoke-Kubectl @("version", "--request-timeout=5s"); if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unreachable"; throw "No cluster" }
    foreach ($d in @("redpanda", "clickhouse", "qdrant", "retrieval-service", "feature-extractor-service", "anomaly-detector-service")) { Test-Deployment $d }
    foreach ($t in @("telemetry_events", "experiment_events", "incidents", "incident_reports", "topology_snapshots", "telemetry_feature_windows", "anomaly_events", "model_runs")) {
        $tables = CH "SHOW TABLES FROM cascade"
        if ($tables -match "(?m)^$t$") { Add-Pass "ClickHouse table $t exists" } else { Add-Fail "ClickHouse table $t missing" }
    }
    if ([int](CH "SELECT count() FROM cascade.telemetry_events") -gt 0) { Add-Pass "telemetry_events has rows" } else { Add-Fail "telemetry_events empty" }
    if ([int](CH "SELECT count() FROM cascade.experiment_events") -gt 0) { Add-Pass "experiment_events has rows" } else { Add-Fail "experiment_events empty" }
    $rpPod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=redpanda", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim()
    foreach ($topic in @("telemetry.raw", "telemetry.enriched", "experiments.events", "anomalies.detected")) {
        $topicCheck = Test-CascadeRedpandaTopic -Namespace $Namespace -Topic $topic
        if ($topicCheck.Exists) {
            Add-Pass "Topic $topic exists"
        } else {
            Add-Fail "Topic $topic missing. Raw topic list: $($topicCheck.Raw)"
        }
    }

    Start-PF "feature-extractor-service" "8013:8013"
    try {
        $ready = HttpJson GET "http://localhost:8013/ready"
        if ($ready.service -eq "feature-extractor-service") { Add-Pass "feature-extractor-service ready" } else { Add-Fail "feature-extractor-service not ready" }
        $extract = HttpJson POST "http://localhost:8013/extract" @{ lookback_minutes = 120; window_seconds = 300 }
        if ($extract.windows_created -ge 0) { Add-Pass "POST /extract succeeds" } else { Add-Fail "POST /extract failed" }
        $synthetic = HttpJson POST "http://localhost:8013/features/synthetic"
        if ($synthetic.window.window_id) { Add-Pass "Synthetic Anomaly detection feature window inserted and labeled" } else { Add-Fail "Synthetic feature insert failed" }
        $script:SyntheticService = if ($synthetic.window.service) { $synthetic.window.service } else { "phase4-synthetic-service" }
        $features = HttpJson GET "http://localhost:8013/features/recent?limit=5"
        if ($features.count -ge 1) { Add-Pass "feature-extractor /features/recent returns JSON" } else { Add-Fail "No recent feature windows" }
    } finally { Stop-PF }
    if ([int](CH "SELECT count() FROM cascade.telemetry_feature_windows") -gt 0) { Add-Pass "telemetry_feature_windows has rows" } else { Add-Fail "telemetry_feature_windows empty" }

    Start-PF "anomaly-detector-service" "8014:8014"
    try {
        $ready = HttpJson GET "http://localhost:8014/ready"
        if ($ready.service -eq "anomaly-detector-service") { Add-Pass "anomaly-detector-service ready" } else { Add-Fail "anomaly-detector-service not ready" }
        $models = HttpJson GET "http://localhost:8014/models/status"
        if ($models.threshold.available -and $models.rolling_zscore.available -and $null -ne $models.isolation_forest.available) { Add-Pass "/models/status reports model availability" } else { Add-Fail "/models/status invalid" }
        $detect = HttpJson POST "http://localhost:8014/detect" @{ lookback_minutes = 240; service = $script:SyntheticService; publish = $true }
        if ($detect.windows_scored -ge 1) { Add-Pass "POST /detect scores feature windows" } else { Add-Fail "POST /detect scored no windows" }
        if ($detect.anomalies_detected -ge 1) { Add-Pass "Detection persisted anomalies" } else { Add-Fail "No anomaly detected from synthetic feature window" }
    } finally { Stop-PF }
    if ([int](CH "SELECT count() FROM cascade.model_runs") -gt 0) { Add-Pass "model_runs has rows" } else { Add-Fail "model_runs empty" }
    if ([int](CH "SELECT count() FROM cascade.anomaly_events") -gt 0) { Add-Pass "anomaly_events has rows" } else { Add-Fail "anomaly_events empty" }

    $anomalyMsg = ""
    if ($rpPod) {
        $consume = Invoke-Kubectl @("-n", $Namespace, "exec", $rpPod, "--", "/bin/bash", "-lc", "timeout 10 rpk -X brokers=localhost:9092 topic consume anomalies.detected --num 1 --format '%v\n'")
        $anomalyMsg = @($consume.Output | Where-Object { ([string]$_).TrimStart().StartsWith("{") } | Select-Object -First 1)
    }
    if ($anomalyMsg) { try { $parsed = $anomalyMsg | ConvertFrom-Json; if ($parsed.event_type -eq "anomaly.detected") { Add-Pass "anomalies.detected receives valid JSON" } else { Add-Fail "anomalies.detected JSON has wrong event_type" } } catch { Add-Fail "anomalies.detected event is not JSON" } } else { Add-Fail "No anomalies.detected event consumed" }

    Start-PF "retrieval-service" "8012:8012"
    try {
        $anoms = HttpJson GET "http://localhost:8012/anomalies/recent?limit=5"
        if ($anoms.count -ge 1) { Add-Pass "retrieval-service /anomalies/recent returns JSON" } else { Add-Fail "retrieval /anomalies/recent empty" }
        $features = HttpJson GET "http://localhost:8012/features/recent?limit=5"
        if ($features.count -ge 1) { Add-Pass "retrieval-service /features/recent returns JSON" } else { Add-Fail "retrieval /features/recent empty" }
        $counts = HttpJson GET "http://localhost:8012/debug/counts"
        if ($null -ne $counts.telemetry_feature_windows -and $null -ne $counts.anomaly_events -and $null -ne $counts.model_runs) { Add-Pass "retrieval-service /debug/counts includes Anomaly detection counts" } else { Add-Fail "Anomaly detection counts missing from retrieval debug" }
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
if ($Failed.Count -eq 0) { Write-Host "ANOMALY DETECTION ACCEPTANCE: PASS"; exit 0 }
Write-Host "ANOMALY DETECTION ACCEPTANCE: FAIL"
exit 1
