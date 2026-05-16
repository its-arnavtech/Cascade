param(
    [string]$BackupRoot = "backups/clickhouse"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupRoot)) {
    Write-Host "No ClickHouse backups found at $BackupRoot"
    exit 0
}

Get-ChildItem -Path $BackupRoot -Directory | Sort-Object Name -Descending | ForEach-Object {
    $manifestPath = Join-Path $_.FullName "manifest.json"
    if (Test-Path $manifestPath) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $rows = 0
        foreach ($table in @($manifest.tables)) { $rows += [int64]$table.rows }
        [pscustomobject]@{
            Timestamp = $manifest.timestamp
            Database = $manifest.database
            Tables = @($manifest.tables).Count
            Rows = $rows
            Path = $_.FullName
        }
    } else {
        [pscustomobject]@{
            Timestamp = $_.Name
            Database = ""
            Tables = 0
            Rows = 0
            Path = $_.FullName
        }
    }
} | Format-Table -AutoSize
