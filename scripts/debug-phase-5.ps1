param([string]$Namespace = "cascade-system")

$ErrorActionPreference = "Continue"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) try { if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 10 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 30) -TimeoutSec 20 } } catch { $_.Exception.Message } }
function CH { param([string]$Query) $pod = kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath='{.items[0].metadata.name}' 2>$null; if ($pod) { kubectl -n $Namespace exec $pod -- clickhouse-client --query $Query } }

try {
    Write-Section "Namespaces"; kubectl get namespaces
    Write-Section "Pods"; kubectl -n $Namespace get pods -o wide
    Write-Section "Deployments"; kubectl -n $Namespace get deployments
    Write-Section "Services"; kubectl -n $Namespace get services
    Write-Section "Endpoints"; kubectl -n $Namespace get endpoints
    Write-Section "Recent Events"; kubectl -n $Namespace get events --sort-by=.lastTimestamp
    Write-Section "ClickHouse Phase 5 Counts"
    foreach ($table in @("knowledge_documents", "knowledge_chunks", "knowledge_ingestion_runs", "knowledge_queries")) { Write-Host "$table=$(CH "SELECT count() FROM cascade.$table")" }
    Write-Section "Recent Knowledge Runs"; CH "SELECT started_at, source, documents_ingested, chunks_indexed, status, error_message FROM cascade.knowledge_ingestion_runs ORDER BY started_at DESC LIMIT 10"
    Write-Section "Recent Knowledge Documents"; CH "SELECT title, source_type, document_type, service, phase FROM cascade.knowledge_documents ORDER BY updated_at DESC LIMIT 10"
    Write-Section "Qdrant Knowledge Collection"
    Start-PF "qdrant" "6333:6333"
    try {
        HttpJson GET "http://localhost:6333/collections/cascade_knowledge_base" | ConvertTo-Json -Depth 20
        HttpJson POST "http://localhost:6333/collections/cascade_knowledge_base/points/count" @{ exact = $true } | ConvertTo-Json -Depth 20
    } finally { Stop-PF }
    foreach ($svc in @("knowledge-ingestion-service", "knowledge-retrieval-service", "retrieval-service")) {
        Write-Section "$svc logs"; kubectl -n $Namespace logs "deployment/$svc" --tail=160
    }
    Start-PF "knowledge-ingestion-service" "8015:8015"
    try { Write-Section "Knowledge Ingestion Health"; HttpJson GET "http://localhost:8015/health" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8015/ready" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8015/stats" | ConvertTo-Json -Depth 10 } finally { Stop-PF }
    Start-PF "knowledge-retrieval-service" "8016:8016"
    try { Write-Section "Knowledge Retrieval Health"; HttpJson GET "http://localhost:8016/health" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8016/ready" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8016/knowledge/stats" | ConvertTo-Json -Depth 10; HttpJson POST "http://localhost:8016/knowledge/search" @{ query = "pod restart unhealthy service anomaly"; limit = 3; filters = @{} } | ConvertTo-Json -Depth 20 } finally { Stop-PF }
    Start-PF "retrieval-service" "8012:8012"
    try { Write-Section "Retrieval Integration"; HttpJson GET "http://localhost:8012/debug/counts" | ConvertTo-Json -Depth 10; HttpJson GET "http://localhost:8012/knowledge/stats" | ConvertTo-Json -Depth 10 } finally { Stop-PF }
} finally {
    Stop-PF
}
