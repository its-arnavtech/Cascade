param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [int]$LogTail = 160
)

$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$bundleDir = Join-Path "support-bundles" $timestamp
New-Item -ItemType Directory -Force -Path $bundleDir | Out-Null

function Save-Command {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    $path = Join-Path $bundleDir $Name
    try {
        & $Command 2>&1 |
            ForEach-Object { [string]$_ -replace '(?i)(authorization:\s*bearer\s+)[^\s]+', '$1<redacted>' -replace '(?i)(token|password|secret|api[_-]?key)(["'':=\s]+)[^,''"\s]+', '$1$2<redacted>' } |
            Set-Content -LiteralPath $path -Encoding UTF8
    } catch {
        "ERROR: $($_.Exception.Message)" | Set-Content -LiteralPath $path -Encoding UTF8
    }
}

function Get-ServiceHealth {
    param([string]$Service, [int]$Port)
    $localPort = $Port + 10000
    $pf = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", "$localPort`:$Port") -WindowStyle Hidden -PassThru
    try {
        Start-Sleep -Seconds 2
        if ($pf.HasExited) { throw "port-forward exited early" }
        Invoke-RestMethod -Method GET -Uri "http://localhost:$localPort/health" -TimeoutSec 8 | ConvertTo-Json -Depth 20
        try { Invoke-RestMethod -Method GET -Uri "http://localhost:$localPort/ready" -TimeoutSec 8 | ConvertTo-Json -Depth 20 } catch { "ready unavailable: $($_.Exception.Message)" }
    } finally {
        if ($null -ne $pf -and -not $pf.HasExited) { Stop-Process -Id $pf.Id -Force }
    }
}

Save-Command "kubernetes-system.txt" { kubectl -n $Namespace get pods,deployments,svc,endpoints,endpointslice -o wide }
Save-Command "kubernetes-targets.txt" { kubectl -n $TargetNamespace get pods,deployments,svc,endpoints -o wide }
Save-Command "events-system.txt" { kubectl -n $Namespace get events --sort-by=.lastTimestamp }
Save-Command "events-targets.txt" { kubectl -n $TargetNamespace get events --sort-by=.lastTimestamp }
Save-Command "redpanda-topics.txt" { kubectl -n $Namespace exec deployment/redpanda -- rpk -X brokers=localhost:9092 topic list }
Save-Command "clickhouse-counts.txt" {
    $tables = kubectl -n $Namespace exec deployment/clickhouse -- clickhouse-client --query "SHOW TABLES FROM cascade"
    foreach ($table in $tables) {
        if (-not [string]::IsNullOrWhiteSpace($table)) {
            $count = kubectl -n $Namespace exec deployment/clickhouse -- clickhouse-client --query "SELECT count() FROM cascade.$table"
            "$table=$count"
        }
    }
}
Save-Command "qdrant-collections.txt" {
    kubectl -n $Namespace run debug-all-qdrant --rm -i --restart=Never --image=curlimages/curl:8.10.1 --image-pull-policy=IfNotPresent --command -- sh -c "curl -fsS http://qdrant:6333/collections; echo; curl -fsS http://qdrant:6333/collections/cascade_incident_memory; echo; curl -fsS http://qdrant:6333/collections/cascade_knowledge_base; echo"
}
Save-Command "command-center.txt" { kubectl -n $Namespace get deploy,svc,endpoints,pods | Select-String command-center }

$services = @{
    "observation-service" = 8000
    "stream-enricher" = 8001
    "experiment-tracker-service" = 8002
    "topology-service" = 8004
    "causal-reconstruction-service" = 8005
    "incident-timeline-service" = 8006
    "retrieval-service" = 8012
    "knowledge-retrieval-service" = 8016
    "agent-tool-gateway" = 8017
    "agent-orchestrator-service" = 8018
    "chaos-planner-service" = 8019
    "chaos-executor-service" = 8020
    "remediation-recommender-service" = 8021
    "approval-service" = 8022
    "remediation-executor-service" = 8023
    "command-center-api" = 8031
}

foreach ($service in $services.Keys) {
    Save-Command "logs-$service.txt" { kubectl -n $Namespace logs "deployment/$service" --tail=$LogTail }
    Save-Command "health-$service.txt" { Get-ServiceHealth -Service $service -Port $services[$service] }
}

Write-Host "DEBUG SUPPORT BUNDLE COMPLETE"
Write-Host "Location: $bundleDir"
