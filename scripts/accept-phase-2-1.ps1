param(
    [string]$Namespace = "cascade-system",
    [int]$LocalPort = 8000
)

$ErrorActionPreference = "Continue"
$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$PortForwardProcess = $null

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "============================================================"
}

function Add-Pass {
    param([string]$Message)
    $script:Passed.Add($Message) | Out-Null
    Write-Host "PASS: $Message"
}

function Add-Fail {
    param([string]$Message)
    $script:Failed.Add($Message) | Out-Null
    Write-Host "FAIL: $Message"
}

function Add-Warn {
    param([string]$Message)
    $script:Warnings.Add($Message) | Out-Null
    Write-Host "WARN: $Message"
}

function Invoke-Kubectl {
    param([string[]]$Arguments)
    $output = & kubectl @Arguments 2>&1
    [pscustomobject]@{
        Output = @($output)
        Text = ($output -join "`n")
        ExitCode = $LASTEXITCODE
    }
}

function Get-KubectlJson {
    param([string[]]$Arguments)
    $result = Invoke-Kubectl $Arguments
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.Text)) {
        return $null
    }
    try {
        return ($result.Text | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Invoke-HttpJson {
    param(
        [string]$Url,
        [int]$Retries = 10
    )

    for ($i = 1; $i -le $Retries; $i++) {
        try {
            return Invoke-RestMethod -Uri $Url -TimeoutSec 5
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }
    return $null
}

function Stop-PortForward {
    if ($null -ne $script:PortForwardProcess -and -not $script:PortForwardProcess.HasExited) {
        Stop-Process -Id $script:PortForwardProcess.Id -Force
    }
}

function Get-RecommendedFix {
    $joined = ($script:Failed -join " ")
    if ($script:Failed.Count -eq 0) {
        return "No fix needed. Phase 2.1 baseline is stable."
    }
    if ($joined -match "Kubernetes API") {
        return "Start the kind cluster or switch to context kind-cascade, then rerun the acceptance test."
    }
    if ($joined -match "deployment|pod|service|CrashLoopBackOff") {
        return "Run .\scripts\reset-to-phase-2-1.ps1, then inspect kubectl -n cascade-system describe pod -l app=observation-service."
    }
    if ($joined -match "metrics/raw|snapshot|Prometheus") {
        return "Check Prometheus, target namespace cascade-targets, and observation-service PROMETHEUS_URL."
    }
    return "Run .\scripts\reset-to-phase-2-1.ps1 and inspect observation-service logs."
}

try {
    Write-Section "Phase 2.1 Acceptance Test"
    Write-Host "Namespace: $Namespace"
    Write-Host "Generated: $(Get-Date -Format o)"

    Write-Section "1. Kubernetes API"
    $version = Invoke-Kubectl @("version", "--request-timeout=5s")
    if ($version.ExitCode -eq 0) {
        Add-Pass "Kubernetes API is reachable."
    }
    else {
        Add-Fail "Kubernetes API is not reachable. $($version.Text)"
        throw "Kubernetes API unreachable"
    }

    Write-Section "2. Namespace"
    $namespaceObject = Get-KubectlJson @("get", "namespace", $Namespace, "-o", "json")
    if ($null -ne $namespaceObject) {
        Add-Pass "Namespace $Namespace exists."
    }
    else {
        Add-Fail "Namespace $Namespace does not exist."
    }

    Write-Section "3. Deployment And Service"
    $deployment = Get-KubectlJson @("-n", $Namespace, "get", "deployment", "observation-service", "-o", "json")
    if ($null -ne $deployment) {
        $available = [int]$deployment.status.availableReplicas
        $desired = [int]$deployment.spec.replicas
        if ($available -ge $desired -and $desired -gt 0) {
            Add-Pass "observation-service deployment exists and is available ($available/$desired)."
        }
        else {
            Add-Fail "observation-service deployment is not available ($available/$desired)."
        }
    }
    else {
        Add-Fail "observation-service deployment does not exist."
    }

    $service = Get-KubectlJson @("-n", $Namespace, "get", "service", "observation-service", "-o", "json")
    if ($null -ne $service) {
        Add-Pass "observation-service service exists."
    }
    else {
        Add-Fail "observation-service service does not exist."
    }

    Write-Section "4. Pod Health"
    $pods = Get-KubectlJson @("-n", $Namespace, "get", "pods", "-l", "app=observation-service", "-o", "json")
    if ($null -eq $pods -or @($pods.items).Count -eq 0) {
        Add-Fail "No observation-service pod found."
    }
    else {
        $pod = @($pods.items)[0]
        $podName = [string]$pod.metadata.name
        $phase = [string]$pod.status.phase
        $ready = @($pod.status.containerStatuses | Where-Object { $_.ready -eq $true }).Count
        $total = @($pod.status.containerStatuses).Count
        Write-Host "Pod: $podName phase=$phase ready=$ready/$total"
        if ($phase -eq "Running" -and $ready -eq 1 -and $total -eq 1) {
            Add-Pass "observation-service pod is 1/1 Running."
        }
        else {
            Add-Fail "observation-service pod is not 1/1 Running."
        }
    }

    $allPods = Invoke-Kubectl @("-n", $Namespace, "get", "pods")
    $allPods.Output | ForEach-Object { Write-Host $_ }
    if ($allPods.Text -match "CrashLoopBackOff") {
        Add-Fail "CrashLoopBackOff detected in $Namespace."
    }
    else {
        Add-Pass "No CrashLoopBackOff detected in $Namespace."
    }

    Write-Section "5. HTTP Port-Forward"
    $arguments = @("-n", $Namespace, "port-forward", "svc/observation-service", "$LocalPort`:8000")
    $script:PortForwardProcess = Start-Process -FilePath "kubectl" -ArgumentList $arguments -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2

    $health = Invoke-HttpJson "http://localhost:$LocalPort/health"
    if ($null -ne $health -and $health.status -eq "ok") {
        Add-Pass "GET /health returns ok."
    }
    else {
        Add-Fail "GET /health did not return ok."
    }

    $rawMetrics = Invoke-HttpJson "http://localhost:$LocalPort/metrics/raw?query=up" 15
    if ($null -ne $rawMetrics -and $null -ne $rawMetrics.prometheus) {
        Add-Pass "GET /metrics/raw?query=up returns Prometheus data."
    }
    else {
        Add-Fail "GET /metrics/raw?query=up did not return Prometheus data."
    }

    $snapshot = Invoke-HttpJson "http://localhost:$LocalPort/snapshot" 20
    if ($null -ne $snapshot -and $snapshot.namespace -eq "cascade-targets") {
        Add-Pass "GET /snapshot returns JSON for namespace cascade-targets."
    }
    else {
        Add-Fail "GET /snapshot did not return valid cascade-targets JSON."
    }

    Write-Section "6. Logs"
    $logs = Invoke-Kubectl @("-n", $Namespace, "logs", "deployment/observation-service", "--tail=120")
    $logs.Output | ForEach-Object { Write-Host $_ }
    if ($logs.Text -match "Traceback") {
        Add-Fail "observation-service logs contain Traceback."
    }
    else {
        Add-Pass "observation-service logs do not contain Traceback."
    }
}
catch {
    Add-Warn "Acceptance test stopped early: $($_.Exception.Message)"
}
finally {
    Stop-PortForward
}

Write-Section "Final Result"
Write-Host "Passed:"
if ($Passed.Count -eq 0) {
    Write-Host "  - none"
}
else {
    foreach ($item in $Passed) {
        Write-Host "  - $item"
    }
}

Write-Host ""
Write-Host "Warnings:"
if ($Warnings.Count -eq 0) {
    Write-Host "  - none"
}
else {
    foreach ($item in $Warnings) {
        Write-Host "  - $item"
    }
}

Write-Host ""
Write-Host "Failed:"
if ($Failed.Count -eq 0) {
    Write-Host "  - none"
}
else {
    foreach ($item in $Failed) {
        Write-Host "  - $item"
    }
}

Write-Host ""
Write-Host "Recommended next fix:"
Write-Host "  $(Get-RecommendedFix)"
Write-Host ""

if ($Failed.Count -eq 0) {
    Write-Host "PHASE 2.1 ACCEPTANCE: PASS"
    exit 0
}

Write-Host "PHASE 2.1 ACCEPTANCE: FAIL"
exit 1
