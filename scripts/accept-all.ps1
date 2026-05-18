param(
    [switch]$ContinueOnFailure,
    [switch]$SkipCommandCenter
)

$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path "run-output" "accept-all-$timestamp"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$phases = @(
    @{ Name = "Telemetry pipeline"; Script = ".\scripts\accept-telemetry.ps1"; Args = @() },
    @{ Name = "Storage and memory"; Script = ".\scripts\accept-storage-memory.ps1"; Args = @() },
    @{ Name = "Anomaly detection"; Script = ".\scripts\accept-anomaly-detection.ps1"; Args = @() },
    @{ Name = "Knowledge and RAG"; Script = ".\scripts\accept-knowledge-rag.ps1"; Args = @() },
    @{ Name = "Agent investigations"; Script = ".\scripts\accept-agents.ps1"; Args = @() },
    @{ Name = "Chaos engineering"; Script = ".\scripts\accept-chaos.ps1"; Args = @("-DryRunOnly") },
    @{ Name = "Remediation"; Script = ".\scripts\accept-remediation.ps1"; Args = @() }
)
if (-not $SkipCommandCenter) {
    $phases += @{ Name = "Command Center UI"; Script = ".\scripts\accept.ps1"; Args = @() }
}

$results = New-Object System.Collections.Generic.List[object]
foreach ($phase in $phases) {
    $safeName = ($phase.Name -replace "\s+", "-").ToLowerInvariant()
    $logPath = Join-Path $outputDir "$safeName.log"
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "Running $($phase.Name)"
    Write-Host "============================================================"
    switch ($phase.Name) {
        "Chaos engineering" { & ".\scripts\accept-chaos.ps1" -DryRunOnly *>&1 | Tee-Object -FilePath $logPath }
        default { & $phase.Script *>&1 | Tee-Object -FilePath $logPath }
    }
    $exitCode = $LASTEXITCODE
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $results.Add([pscustomobject]@{
        Area = $phase.Name
        Status = $status
        ExitCode = $exitCode
        Log = $logPath
    }) | Out-Null
    if ($exitCode -ne 0 -and -not $ContinueOnFailure) {
        break
    }
}

Write-Host ""
Write-Host "============================================================"
Write-Host "Cascade Acceptance Summary"
Write-Host "============================================================"
$results | Format-Table -AutoSize
Write-Host "Logs: $outputDir"

$failed = @($results | Where-Object { $_.Status -ne "PASS" })
if ($failed.Count -eq 0 -and $results.Count -eq $phases.Count) {
    Write-Host "CASCADE ACCEPTANCE: PASS"
    exit 0
}

Write-Host "CASCADE ACCEPTANCE: FAIL"
exit 1
