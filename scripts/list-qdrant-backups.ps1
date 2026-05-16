param(
    [string]$BackupRoot = "backups/qdrant"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupRoot)) {
    Write-Host "No Qdrant backups found at $BackupRoot"
    exit 0
}

Get-ChildItem -Path $BackupRoot -Directory | Sort-Object Name -Descending | ForEach-Object {
    $manifestPath = Join-Path $_.FullName "manifest.json"
    if (Test-Path $manifestPath) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $points = 0
        foreach ($collection in @($manifest.collections)) { $points += [int64]$collection.points }
        [pscustomobject]@{
            Timestamp = $manifest.timestamp
            Collections = @($manifest.collections).Count
            Points = $points
            Path = $_.FullName
        }
    } else {
        [pscustomobject]@{
            Timestamp = $_.Name
            Collections = 0
            Points = 0
            Path = $_.FullName
        }
    }
} | Format-Table -AutoSize
