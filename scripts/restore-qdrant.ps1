param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [string]$Namespace = "cascade-system",
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"
$PortForward = $null

function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}

if (-not (Test-Path $BackupPath)) { throw "Backup path not found: $BackupPath" }
$manifestPath = Join-Path $BackupPath "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "Backup manifest not found: $manifestPath" }

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
Write-Host "Qdrant restore candidate"
Write-Host "Timestamp: $($manifest.timestamp)"
Write-Host "Collections:"
foreach ($collection in @($manifest.collections)) {
    Write-Host "  - $($collection.name) points=$($collection.points) snapshot=$($collection.snapshot_file)"
}

if (-not $ConfirmRestore) {
    Write-Host ""
    Write-Host "DRY RUN ONLY: pass -ConfirmRestore to restore these snapshots."
    Write-Host "Restore does not silently overwrite collections; Qdrant will reject incompatible existing collections."
    exit 0
}

try {
    $port = Get-FreePort
    $PortForward = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/qdrant", "$port`:6333") -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 3
    if ($PortForward.HasExited) { throw "qdrant port-forward exited early" }

    $baseUrl = "http://localhost:$port"
    foreach ($collection in @($manifest.collections)) {
        $snapshotPath = Join-Path $BackupPath $collection.snapshot_file
        if (-not (Test-Path $snapshotPath)) { throw "Missing snapshot file: $snapshotPath" }

        $restoreUrl = "$baseUrl/collections/$($collection.name)/snapshots/upload?priority=snapshot"
        Invoke-RestMethod -Method POST -Uri $restoreUrl -Form @{ snapshot = Get-Item -LiteralPath $snapshotPath } -TimeoutSec 180 | Out-Null
        Write-Host "Submitted restore for $($collection.name)"
    }

    Write-Host "QDRANT RESTORE SUBMITTED"
} finally {
    if ($null -ne $PortForward -and -not $PortForward.HasExited) {
        Stop-Process -Id $PortForward.Id -Force
    }
}
