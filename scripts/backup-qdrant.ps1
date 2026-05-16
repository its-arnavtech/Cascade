param(
    [string]$Namespace = "cascade-system",
    [string[]]$Collections = @("cascade_incident_memory", "cascade_knowledge_base"),
    [string]$OutputRoot = "backups/qdrant"
)

$ErrorActionPreference = "Stop"
$PortForward = $null

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}

try {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path $OutputRoot $timestamp
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

    $port = Get-FreePort
    $PortForward = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/qdrant", "$port`:6333") -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 3
    if ($PortForward.HasExited) { throw "qdrant port-forward exited early" }

    $baseUrl = "http://localhost:$port"
    $manifestCollections = @()
    foreach ($collection in $Collections) {
        $info = Invoke-RestMethod -Method GET -Uri "$baseUrl/collections/$collection" -TimeoutSec 20
        $count = Invoke-RestMethod -Method POST -Uri "$baseUrl/collections/$collection/points/count" -ContentType "application/json" -Body (@{ exact = $true } | ConvertTo-Json) -TimeoutSec 20
        $snapshot = Invoke-RestMethod -Method POST -Uri "$baseUrl/collections/$collection/snapshots" -TimeoutSec 60
        $snapshotName = $snapshot.result.name
        if (-not $snapshotName) { throw "Qdrant did not return a snapshot name for $collection" }
        $fileName = "$collection-$snapshotName"
        Invoke-WebRequest -Uri "$baseUrl/collections/$collection/snapshots/$snapshotName" -OutFile (Join-Path $backupDir $fileName) -UseBasicParsing -TimeoutSec 120
        $manifestCollections += [pscustomobject]@{
            name = $collection
            points = [int64]$count.result.count
            snapshot_file = $fileName
            vector_size = $info.result.config.params.vectors.size
        }
    }

    $gitCommit = ""
    try { $gitCommit = (& git rev-parse HEAD 2>$null).Trim() } catch { $gitCommit = "" }
    [pscustomobject]@{
        timestamp = $timestamp
        namespace = $Namespace
        qdrant_url = $baseUrl
        method = "Qdrant collection snapshot API via local port-forward"
        git_commit = $gitCommit
        collections = $manifestCollections
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $backupDir "manifest.json") -Encoding UTF8

    Write-Host "QDRANT BACKUP COMPLETE"
    Write-Host "Location: $backupDir"
} finally {
    if ($null -ne $PortForward -and -not $PortForward.HasExited) {
        Stop-Process -Id $PortForward.Id -Force
    }
}
