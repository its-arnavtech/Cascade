param(
    [switch]$ContinueOnFailure,
    [switch]$SkipPhase9
)

$ErrorActionPreference = "Continue"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outputDir = Join-Path "run-output" "accept-all-$timestamp"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$phases = @(
    @{ Name = "Phase 2"; Script = ".\scripts\accept-phase-2.ps1"; Args = @() },
    @{ Name = "Phase 3"; Script = ".\scripts\accept-phase-3.ps1"; Args = @() },
    @{ Name = "Phase 4"; Script = ".\scripts\accept-phase-4.ps1"; Args = @() },
    @{ Name = "Phase 5"; Script = ".\scripts\accept-phase-5.ps1"; Args = @() },
    @{ Name = "Phase 6"; Script = ".\scripts\accept-phase-6.ps1"; Args = @() },
    @{ Name = "Phase 7"; Script = ".\scripts\accept-phase-7.ps1"; Args = @("-DryRunOnly") },
    @{ Name = "Phase 8"; Script = ".\scripts\accept-phase-8.ps1"; Args = @() }
)
if (-not $SkipPhase9) {
    $phases += @{ Name = "Phase 9"; Script = ".\scripts\accept-phase-9.ps1"; Args = @() }
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
        "Phase 7" { & ".\scripts\accept-phase-7.ps1" -DryRunOnly *>&1 | Tee-Object -FilePath $logPath }
        default { & $phase.Script *>&1 | Tee-Object -FilePath $logPath }
    }
    $exitCode = $LASTEXITCODE
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $results.Add([pscustomobject]@{
        Phase = $phase.Name
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
