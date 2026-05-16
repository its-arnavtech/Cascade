param(
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$keywords = @(
    "api_key", "apikey", "secret", "password", "passwd", "token", "bearer", "authorization",
    "private_key", "client_secret", "DATABASE_URL", "CLICKHOUSE_PASSWORD", "QDRANT_API_KEY",
    "OPENAI_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "kubeconfig",
    "BEGIN RSA PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY", "service_account"
)

$safeValues = @("", "none", "null", "false", "true", "changeme", "change-me", "placeholder", "example", "replace-me", "replace-with-local-key-if-needed", "<redacted>", "<placeholder>", "your-value-here")
$findings = New-Object System.Collections.Generic.List[object]
$tracked = @(& git ls-files)

foreach ($file in $tracked) {
    if (-not (Test-Path $file)) { continue }
    $lineNumber = 0
    foreach ($line in Get-Content -LiteralPath $file -ErrorAction SilentlyContinue) {
        $lineNumber++
        foreach ($keyword in $keywords) {
            if ($line -notmatch [regex]::Escape($keyword)) { continue }

            $highConfidence = $false
            $reason = "keyword"
            $assignmentPattern = '(?i)^\s*["'']?([A-Z0-9_.-]*(api[_-]?key|apikey|secret|password|passwd|token|authorization|private[_-]?key|client[_-]?secret|database_url|clickhouse_password|qdrant_api_key|openai_api_key|aws_access_key_id|aws_secret_access_key|service_account)[A-Z0-9_.-]*)["'']?\s*=\s*["'']?([^"'',\s#]+)'
            $match = [regex]::Match($line, $assignmentPattern)
            if ($match.Success) {
                $keyName = $match.Groups[1].Value.Trim()
                $value = $match.Groups[3].Value.Trim()
                $normalized = $value.ToLowerInvariant()
                $keyLooksCredentialLike = ($keyName -cmatch '[A-Z]' -or $keyName -match 'api|secret|password|passwd|authorization|private|client|database|aws|openai|qdrant|clickhouse|service_account')
                $fileAllowsCodeIdentifiers = $file -match 'package-lock\.json$|deterministic\.py$'
                if ($keyLooksCredentialLike -and -not $fileAllowsCodeIdentifiers -and $safeValues -notcontains $normalized -and $value -notmatch '^\$\{?[A-Z0-9_]+\}?$') {
                    $highConfidence = $true
                    $reason = "non-placeholder assignment"
                } else {
                    $reason = "placeholder assignment"
                }
            }
            if ($line -match "-----BEGIN (RSA|OPENSSH|DSA|EC) PRIVATE KEY-----") {
                $highConfidence = $true
                $reason = "private key block"
            }

            $findings.Add([pscustomobject]@{
                File = $file
                Line = $lineNumber
                Key = $keyword
                Severity = if ($highConfidence) { "high" } else { "info" }
                Reason = $reason
            }) | Out-Null
        }
    }
}

if ($Json) {
    $findings | ConvertTo-Json -Depth 4
} else {
    if ($findings.Count -eq 0) {
        Write-Host "PASS: no suspicious secret keywords found in tracked files"
    } else {
        Write-Host "Secret hygiene scan findings (values redacted by design):"
        $findings | Sort-Object Severity, File, Line | Format-Table File, Line, Key, Severity, Reason -AutoSize
    }
}

$high = @($findings | Where-Object { $_.Severity -eq "high" })
if ($high.Count -gt 0) {
    Write-Host "FAIL: high-confidence secret-like assignments found. Remove real values or replace with placeholders before publishing."
    exit 1
}

Write-Host "PASS: no high-confidence secrets found in tracked files"
exit 0
