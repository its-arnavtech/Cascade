param(
    [string]$Namespace = "cascade-system",
    [string]$Database = "cascade",
    [string]$OutputRoot = "backups/clickhouse"
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

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$tables = @((Invoke-ClickHouse "SHOW TABLES FROM $Database") -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
$manifestTables = @()

foreach ($table in $tables) {
    $safeTable = $table.Trim()
    $schemaPath = Join-Path $backupDir "$safeTable.schema.sql"
    $dataPath = Join-Path $backupDir "$safeTable.jsonl"
    $schema = Invoke-ClickHouse "SHOW CREATE TABLE $Database.$safeTable"
    Set-Content -LiteralPath $schemaPath -Value $schema -Encoding UTF8

    $data = Invoke-ClickHouse "SELECT * FROM $Database.$safeTable FORMAT JSONEachRow"
    Set-Content -LiteralPath $dataPath -Value $data -Encoding UTF8

    $rowCount = Invoke-ClickHouse "SELECT count() FROM $Database.$safeTable"
    $manifestTables += [pscustomobject]@{
        name = $safeTable
        rows = [int64]$rowCount
        schema_file = (Split-Path -Leaf $schemaPath)
        data_file = (Split-Path -Leaf $dataPath)
    }
}

$gitCommit = ""
try { $gitCommit = (& git rev-parse HEAD 2>$null).Trim() } catch { $gitCommit = "" }

$manifest = [pscustomobject]@{
    timestamp = $timestamp
    database = $Database
    namespace = $Namespace
    method = "clickhouse-client JSONEachRow export from deployment/clickhouse"
    git_commit = $gitCommit
    tables = $manifestTables
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $backupDir "manifest.json") -Encoding UTF8

Write-Host "CLICKHOUSE BACKUP COMPLETE"
Write-Host "Location: $backupDir"
Write-Host "Tables: $($tables.Count)"
