param(
    [string]$Namespace = "cascade-system",
    [string]$OutputRoot = "backups/cascade-state",
    [switch]$SkipQdrant
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Kubectl {
    param([string[]]$Arguments)
    $output = & kubectl @Arguments 2>&1
    [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE }
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $OutputRoot $timestamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

Write-Section "Backup Cascade state"
Write-Host "Writing backup manifests under $backupDir"
Write-Host "Secrets are not printed. Generated backup files stay under gitignored backups/."

$clickhouseRoot = Join-Path $backupDir "clickhouse"
& "$PSScriptRoot\backup-clickhouse.ps1" -Namespace $Namespace -OutputRoot $clickhouseRoot
if ($LASTEXITCODE -ne 0) { throw "ClickHouse backup failed" }

$qdrantBackupPath = ""
if (-not $SkipQdrant) {
    $qdrantRoot = Join-Path $backupDir "qdrant"
    & "$PSScriptRoot\backup-qdrant.ps1" -Namespace $Namespace -OutputRoot $qdrantRoot
    if ($LASTEXITCODE -ne 0) { throw "Qdrant backup failed" }
    $qdrantBackupPath = $qdrantRoot
}

$redpandaPath = Join-Path $backupDir "redpanda-topics.txt"
$topicResult = Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/redpanda", "--", "rpk", "-X", "brokers=localhost:9092", "topic", "list")
if ($topicResult.ExitCode -eq 0) {
    $topicResult.Text | Set-Content -LiteralPath $redpandaPath -Encoding UTF8
} else {
    "Redpanda topic list unavailable: $($topicResult.Text)" | Set-Content -LiteralPath $redpandaPath -Encoding UTF8
}

$gitCommit = ""
try { $gitCommit = (& git rev-parse HEAD 2>$null).Trim() } catch { $gitCommit = "" }

[pscustomobject]@{
    timestamp = $timestamp
    namespace = $Namespace
    git_commit = $gitCommit
    clickhouse = "clickhouse"
    qdrant = if ($SkipQdrant) { "skipped" } else { "qdrant" }
    redpanda_topics = "redpanda-topics.txt"
    restore = @{
        clickhouse = ".\scripts\restore-clickhouse.ps1 -BackupPath <this>\clickhouse\<timestamp> -ConfirmRestore"
        qdrant = ".\scripts\restore-qdrant.ps1 -BackupPath <this>\qdrant\<timestamp> -ConfirmRestore"
    }
} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $backupDir "manifest.json") -Encoding UTF8

Write-Host "CASCADE STATE BACKUP COMPLETE"
Write-Host "Location: $backupDir"
