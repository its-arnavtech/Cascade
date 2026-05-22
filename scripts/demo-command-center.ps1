param(
    [ValidateSet("Validate", "Telemetry", "Chaos", "Remediation", "Autopilot", "Reset", "All")]
    [string]$Stage = "All",
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [string]$Service = "catalogue"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "============================================================"
}

function Invoke-DemoScript {
    param(
        [string]$ScriptName,
        [string[]]$Arguments = @()
    )
    $path = Join-Path $PSScriptRoot $ScriptName
    if (-not (Test-Path $path)) { throw "Missing script: $path" }
    Write-Host "RUN: powershell -ExecutionPolicy Bypass -File .\scripts\$ScriptName $($Arguments -join ' ')"
    & powershell -ExecutionPolicy Bypass -File $path @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$ScriptName failed with exit code $LASTEXITCODE" }
}

function Show-NextSteps {
    Write-Host ""
    Write-Host "Command Center:"
    Write-Host "  kubectl port-forward -n $Namespace svc/command-center 18300:8030"
    Write-Host "  http://localhost:18300"
    Write-Host ""
    Write-Host "Expected dashboard signals:"
    Write-Host "  - Overview: live data badges, anomaly/RCA/remediation/Autopilot status"
    Write-Host "  - Causality: RCA bundle with confidence or explicit insufficient evidence"
    Write-Host "  - Chaos: dry-run plan/run records, not live execution"
    Write-Host "  - Remediation: plan, approval, dry-run validation, rollback/verification state"
    Write-Host "  - Autopilot: investigated -> planned -> policy checked -> dry-run -> verified"
}

Set-Location $Root

Write-Section "Cascade Command Center Demo"
Write-Host "Stage: $Stage"
Write-Host "Namespace: $Namespace"
Write-Host "Target namespace: $TargetNamespace"
Write-Host "Service: $Service"
Write-Host "Safety: dry-run first; this wrapper does not enable live chaos or live remediation."

if ($Stage -in @("Validate", "All")) {
    Write-Section "Fresh Validation"
    Invoke-DemoScript "validate-target.ps1" @("-Namespace", $TargetNamespace)
    Invoke-DemoScript "accept-telemetry.ps1"
}

if ($Stage -in @("Telemetry", "All")) {
    Write-Section "Run Demo Telemetry"
    Invoke-DemoScript "demo-anomaly-detection.ps1"
    Write-Host "Expected result: telemetry feature windows and anomalies appear in Overview and Telemetry."
}

if ($Stage -in @("Chaos", "All")) {
    Write-Section "Run Demo Chaos Dry-run"
    Invoke-DemoScript "demo-chaos.ps1" @("-TargetService", $Service, "-DryRunOnly", "-NoAgent")
    Write-Host "Expected result: Chaos page shows a dry-run plan/run and policy-gated status."
}

if ($Stage -in @("Remediation", "All")) {
    Write-Section "Run Demo Remediation Dry-run"
    Invoke-DemoScript "demo-remediation.ps1" @("-Service", $Service)
    Write-Host "Expected result: Remediation page shows evidence-backed plan, approval, dry-run validation, and blocked real execution."
}

if ($Stage -in @("Autopilot", "All")) {
    Write-Section "Run Demo Autopilot Dry-run"
    Invoke-DemoScript "accept-autopilot.ps1" @("-Namespace", $Namespace)
    Write-Host "Expected result: Autopilot page shows investigated, planned, policy checked, dry-run, and verified states."
}

if ($Stage -eq "Reset") {
    Write-Section "Reset Demo Flags and UI State"
    Invoke-DemoScript "disable-ui-live-demo.ps1"
    Invoke-DemoScript "reset-command-center.ps1"
    Write-Host "Expected result: live-demo UI actions hidden, Command Center returns to dry-run mode."
}

Show-NextSteps
