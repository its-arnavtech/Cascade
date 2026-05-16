param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [string]$Namespace = "cascade-system",
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"

function Invoke-Kubectl {
    param([string[]]$Arguments)
    $output = & kubectl @Arguments 2>&1
    [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE }
}

function Invoke-ClickHouse {
    param([string]$Query)
    $result = Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/clickhouse", "--", "clickhouse-client", "--query", $Query)
    if ($result.ExitCode -ne 0) { throw "ClickHouse query failed: $Query`n$($result.Text)" }
    $result.Text.Trim()
}

if (-not (Test-Path $BackupPath)) { throw "Backup path not found: $BackupPath" }
$manifestPath = Join-Path $BackupPath "manifest.json"
if (-not (Test-Path $manifestPath)) { throw "Backup manifest not found: $manifestPath" }

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
Write-Host "ClickHouse restore candidate"
Write-Host "Database: $($manifest.database)"
Write-Host "Timestamp: $($manifest.timestamp)"
Write-Host "Tables:"
foreach ($table in @($manifest.tables)) {
    Write-Host "  - $($table.name) rows=$($table.rows)"
}

if (-not $ConfirmRestore) {
    Write-Host ""
    Write-Host "DRY RUN ONLY: pass -ConfirmRestore to restore this backup into the existing database."
    exit 0
}

foreach ($table in @($manifest.tables)) {
    $schemaPath = Join-Path $BackupPath $table.schema_file
    $dataPath = Join-Path $BackupPath $table.data_file
    if (-not (Test-Path $schemaPath)) { throw "Missing schema file: $schemaPath" }
    if (-not (Test-Path $dataPath)) { throw "Missing data file: $dataPath" }

    $schema = Get-Content -LiteralPath $schemaPath -Raw
    Invoke-ClickHouse $schema | Out-Null
    Invoke-ClickHouse "TRUNCATE TABLE $($manifest.database).$($table.name)" | Out-Null

    if ((Get-Item -LiteralPath $dataPath).Length -gt 0) {
        $command = "clickhouse-client --query `"INSERT INTO $($manifest.database).$($table.name) FORMAT JSONEachRow`""
        Get-Content -LiteralPath $dataPath -Raw | kubectl -n $Namespace exec -i deployment/clickhouse -- sh -c $command
        if ($LASTEXITCODE -ne 0) { throw "Failed to restore data for $($table.name)" }
    }
    Write-Host "Restored $($table.name)"
}

Write-Host "CLICKHOUSE RESTORE COMPLETE"
