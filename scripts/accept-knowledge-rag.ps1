param([string]$Namespace = "cascade-system")

$ErrorActionPreference = "Continue"
$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Add-Pass { param([string]$Message) $script:Passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Fail { param([string]$Message) $script:Failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Add-Warn { param([string]$Message) $script:Warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Get-KubectlJson { param([string[]]$Arguments) $r = Invoke-Kubectl $Arguments; if ($r.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($r.Text)) { return $null }; try { $r.Text | ConvertFrom-Json } catch { return $null } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null, [int]$Retries = 10) for ($i = 1; $i -le $Retries; $i++) { try { if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 180 } return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 180 } catch { Start-Sleep -Seconds 2 } }; return $null }
function Test-Deployment { param([string]$Name) $d = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json"); if ($null -eq $d) { Add-Fail "Deployment $Name missing"; return }; $a = [int]$d.status.availableReplicas; $r = [int]$d.spec.replicas; if ($r -gt 0 -and $a -ge $r) { Add-Pass "Deployment $Name available" } else { Add-Fail "Deployment $Name not available ($a/$r)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if (-not $pod) { return "" }; (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text.Trim() }

try {
    Write-Section "Knowledge and RAG Acceptance"
    $api = Invoke-Kubectl @("version", "--request-timeout=5s"); if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unreachable"; throw "No cluster" }
    foreach ($d in @("redpanda", "clickhouse", "qdrant", "retrieval-service", "feature-extractor-service", "anomaly-detector-service", "knowledge-ingestion-service", "knowledge-retrieval-service")) { Test-Deployment $d }
    foreach ($t in @("telemetry_feature_windows", "anomaly_events", "knowledge_documents", "knowledge_chunks", "knowledge_ingestion_runs", "knowledge_queries")) {
        $tables = CH "SHOW TABLES FROM cascade"
        if ($tables -match "(?m)^$t$") { Add-Pass "ClickHouse table $t exists" } else { Add-Fail "ClickHouse table $t missing" }
    }
    try { [void][int](CH "SELECT count() FROM cascade.anomaly_events"); Add-Pass "anomaly_events is queryable" } catch { Add-Fail "anomaly_events is not queryable" }

    Start-PF "qdrant" "6333:6333"
    try {
        $collection = HttpJson GET "http://localhost:6333/collections/cascade_knowledge_base" $null 2
        if ($collection.result.config.params.vectors.size -eq 128) { Add-Pass "Qdrant cascade_knowledge_base exists" } else { Add-Fail "Qdrant cascade_knowledge_base missing" }
    } finally { Stop-PF }

    Start-PF "knowledge-ingestion-service" "8015:8015"
    try {
        $ready = HttpJson GET "http://localhost:8015/ready"
        if ($ready.service -eq "knowledge-ingestion-service") { Add-Pass "knowledge-ingestion-service ready" } else { Add-Fail "knowledge-ingestion-service not ready" }
        $ingest = HttpJson POST "http://localhost:8015/ingest/all" $null 1
        if ($ingest.status -eq "ok" -or $ingest.status -eq "partial") { Add-Pass "POST /ingest/all succeeds" } else { Add-Fail "POST /ingest/all failed" }
    } finally { Stop-PF }

    if ([int](CH "SELECT count() FROM cascade.knowledge_documents") -gt 0) { Add-Pass "knowledge_documents has rows" } else { Add-Fail "knowledge_documents empty" }
    if ([int](CH "SELECT count() FROM cascade.knowledge_chunks") -gt 0) { Add-Pass "knowledge_chunks has rows" } else { Add-Fail "knowledge_chunks empty" }
    $lastStatus = CH "SELECT status FROM cascade.knowledge_ingestion_runs ORDER BY started_at DESC LIMIT 1"
    if ($lastStatus -eq "success") { Add-Pass "latest ingestion run status is success" } else { Add-Fail "latest ingestion run status is not success: $lastStatus" }

    Start-PF "knowledge-retrieval-service" "8016:8016"
    try {
        $ready = HttpJson GET "http://localhost:8016/ready"
        if ($ready.service -eq "knowledge-retrieval-service") { Add-Pass "knowledge-retrieval-service ready" } else { Add-Fail "knowledge-retrieval-service not ready" }
        $stats = HttpJson GET "http://localhost:8016/knowledge/stats"
        if ($stats.qdrant_knowledge_points -gt 0) { Add-Pass "cascade_knowledge_base has points" } else { Add-Fail "cascade_knowledge_base point count is zero" }
        $search = HttpJson POST "http://localhost:8016/knowledge/search" @{ query = "pod restart unhealthy service anomaly"; limit = 5; filters = @{} }
        if ($search.count -ge 1 -and $search.results[0].chunk_id -and $search.results[0].chunk_text) { Add-Pass "/knowledge/search returns source-grounded chunks" } else { Add-Fail "/knowledge/search missing results or chunk text" }
        $ctx = HttpJson POST "http://localhost:8016/knowledge/context" @{ query = "how do I investigate recommendationservice restart anomaly"; limit = 8; filters = @{} }
        if ($ctx.evidence_chunks.Count -ge 1 -and $ctx.sources.Count -ge 1 -and $ctx.limitations.Count -ge 1) { Add-Pass "/knowledge/context returns evidence and limitations" } else { Add-Fail "/knowledge/context invalid" }
    } finally { Stop-PF }

    Start-PF "retrieval-service" "8012:8012"
    try {
        $stats = HttpJson GET "http://localhost:8012/knowledge/stats"
        if ($null -ne $stats.knowledge_documents) { Add-Pass "retrieval-service /knowledge/stats returns JSON" } else { Add-Fail "retrieval-service /knowledge/stats invalid" }
        $search = HttpJson POST "http://localhost:8012/knowledge/search" @{ query = "pod restart unhealthy service anomaly"; limit = 3; filters = @{} }
        if ($search.count -ge 1) { Add-Pass "retrieval-service /knowledge/search returns JSON" } else { Add-Fail "retrieval-service /knowledge/search empty" }
        $counts = HttpJson GET "http://localhost:8012/debug/counts"
        if ($null -ne $counts.knowledge_documents -and $null -ne $counts.qdrant_knowledge_points) { Add-Pass "retrieval-service /debug/counts includes Knowledge and RAG counts" } else { Add-Fail "Knowledge and RAG counts missing from retrieval debug" }
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
if ($Failed.Count -eq 0) { Write-Host "KNOWLEDGE ACCEPTANCE: PASS"; exit 0 }
Write-Host "KNOWLEDGE ACCEPTANCE: FAIL"
exit 1
