param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')]
    [string]$Namespace,

    [ValidateScript({
        foreach ($item in $_) {
            if ($item -notmatch '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$') { throw "Expected service '$item' is not a valid Kubernetes service name." }
        }
        $true
    })]
    [string[]]$ExpectedServices = @(),

    [switch]$ShowLabels,
    [switch]$Strict,

    [ValidateScript({
        if (-not $_) { return $true }
        if (-not (Test-Path -LiteralPath $_ -PathType Leaf)) { throw "Target config not found: $_" }
        $true
    })]
    [string]$TargetConfig = ""
)

$ErrorActionPreference = "Continue"
$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Add-Pass { param([string]$Message) $script:Passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Fail { param([string]$Message) $script:Failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Add-Warn { param([string]$Message) $script:Warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Get-KubectlJson { param([string[]]$Arguments) $result = Invoke-Kubectl $Arguments; if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.Text)) { return $null }; try { $result.Text | ConvertFrom-Json } catch { return $null } }
function Label-Value { param([object]$Labels, [string]$Name) if ($null -eq $Labels) { return "" }; $property = $Labels.PSObject.Properties[$Name]; if ($null -eq $property) { return "" }; [string]$property.Value }

function Read-TargetConfig {
    param([string]$Path)
    $config = [ordered]@{
        Namespace = ""
        Services = @()
        SafeChaosServices = @()
        ProtectedServices = @()
    }
    if ([string]::IsNullOrWhiteSpace($Path)) { return $config }
    $section = ""
    foreach ($raw in Get-Content -LiteralPath $Path) {
        $line = ([string]$raw).Split("#")[0].TrimEnd()
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line -match '^namespace:\s*(?<value>\S+)') { $config.Namespace = $Matches.value.Trim("'`""); continue }
        if ($line -match '^(services|safe_chaos_services|protected_services):\s*$') { $section = $Matches[1]; continue }
        if ($line -match '^\S') { $section = ""; continue }
        if ($section -and $line.Trim() -match '^-\s*(?<value>[a-z0-9]([-a-z0-9]*[a-z0-9])?)\s*$') {
            $value = $Matches.value
            if ($section -eq "services") { $config.Services += $value }
            if ($section -eq "safe_chaos_services") { $config.SafeChaosServices += $value }
            if ($section -eq "protected_services") { $config.ProtectedServices += $value }
        }
    }
    return $config
}

function Test-PodReady {
    param([object]$Pod)
    if ($Pod.status.phase -ne "Running") { return $false }
    $statuses = @($Pod.status.containerStatuses)
    if ($statuses.Count -eq 0) { return $false }
    return (@($statuses | Where-Object { $_.ready -eq $true }).Count -eq $statuses.Count)
}

function Get-PodFailureReason {
    param([object]$Pod)
    $badReasons = @("CrashLoopBackOff", "Error", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError", "RunContainerError")
    $reasons = New-Object System.Collections.Generic.List[string]
    if ($Pod.status.phase -eq "Failed") { $reasons.Add("phase=Failed") | Out-Null }
    foreach ($status in @($Pod.status.initContainerStatuses) + @($Pod.status.containerStatuses)) {
        if ($null -eq $status) { continue }
        $waitingReason = [string]$status.state.waiting.reason
        if ($waitingReason -and ($badReasons -contains $waitingReason)) { $reasons.Add("$($status.name): $waitingReason") | Out-Null }
        $terminated = $status.state.terminated
        if ($null -ne $terminated -and [int]$terminated.exitCode -ne 0) { $reasons.Add("$($status.name): terminated $($terminated.exitCode) $($terminated.reason)") | Out-Null }
    }
    return ($reasons -join "; ")
}

Write-Section "Validate Target Workload"

$cluster = Invoke-Kubectl @("version", "--request-timeout=5s")
if ($cluster.ExitCode -eq 0) { Add-Pass "kubectl can reach Kubernetes" } else { Add-Fail "kubectl cannot reach Kubernetes"; Write-Host $cluster.Text }

if ($Namespace -eq "cascade-system") { Add-Fail "Target namespace must not be cascade-system" }
$namespaceJson = Get-KubectlJson @("get", "namespace", $Namespace, "-o", "json")
if ($null -eq $namespaceJson) {
    Add-Fail "Namespace $Namespace does not exist"
} else {
    Add-Pass "Namespace $Namespace exists"
    $monitored = Label-Value $namespaceJson.metadata.labels "cascade.io/monitored"
    if ($monitored -eq "true") { Add-Pass "Namespace has cascade.io/monitored=true" } else { Add-Fail "Namespace is missing cascade.io/monitored=true" }
}

$config = Read-TargetConfig $TargetConfig
if ($TargetConfig) {
    Add-Pass "Target config parsed: $TargetConfig"
    if ($config.Namespace -and $config.Namespace -ne $Namespace) { Add-Fail "Target config namespace '$($config.Namespace)' does not match -Namespace '$Namespace'" }
    $ExpectedServices = @($ExpectedServices + $config.Services | Select-Object -Unique)
}

$pods = Get-KubectlJson @("-n", $Namespace, "get", "pods", "-o", "json")
$services = Get-KubectlJson @("-n", $Namespace, "get", "services", "-o", "json")
$podItems = if ($null -ne $pods) { @($pods.items) } else { @() }
$serviceItems = if ($null -ne $services) { @($services.items) } else { @() }

if ($podItems.Count -gt 0) { Add-Pass "$($podItems.Count) pod(s) found" } else { Add-Fail "No pods found in $Namespace" }
if ($serviceItems.Count -gt 0) { Add-Pass "$($serviceItems.Count) service(s) found" } else { Add-Fail "No services found in $Namespace" }

$notReady = @()
$badState = @()
$missingLabels = @()
foreach ($pod in $podItems) {
    if (-not (Test-PodReady $pod)) { $notReady += $pod.metadata.name }
    $reason = Get-PodFailureReason $pod
    if (-not [string]::IsNullOrWhiteSpace($reason)) { $badState += "$($pod.metadata.name): $reason" }
    $app = Label-Value $pod.metadata.labels "app"
    $appName = Label-Value $pod.metadata.labels "app.kubernetes.io/name"
    if (-not $app -and -not $appName) { $missingLabels += $pod.metadata.name }
}
if ($notReady.Count -eq 0 -and $podItems.Count -gt 0) { Add-Pass "All pods are Running/Ready" } elseif ($notReady.Count -gt 0) { Add-Fail "Pods not Running/Ready: $($notReady -join ', ')" }
if ($badState.Count -eq 0) { Add-Pass "No CrashLoopBackOff/Error/ImagePullBackOff/CreateContainerConfigError states found" } else { Add-Fail "Bad pod states: $($badState -join '; ')" }
if ($missingLabels.Count -eq 0 -and $podItems.Count -gt 0) { Add-Pass "Pods have app or app.kubernetes.io/name labels" } elseif ($missingLabels.Count -gt 0) { Add-Fail "Pods missing usable app labels: $($missingLabels -join ', ')" }

$podLabelNames = New-Object System.Collections.Generic.HashSet[string]
foreach ($pod in $podItems) {
    foreach ($key in @("app", "app.kubernetes.io/name")) {
        $value = Label-Value $pod.metadata.labels $key
        if ($value) { [void]$podLabelNames.Add($value) }
    }
}
$serviceNames = @($serviceItems | ForEach-Object { [string]$_.metadata.name })
foreach ($expected in $ExpectedServices) {
    if ($serviceNames -contains $expected) { Add-Pass "Expected service exists: $expected" } else { Add-Fail "Expected Kubernetes service missing: $expected" }
    if ($podLabelNames.Contains($expected)) { Add-Pass "Expected pod label exists: $expected" } else { Add-Warn "No pod app/app.kubernetes.io/name label found for expected service: $expected" }
}

foreach ($protected in $config.ProtectedServices) {
    if ($serviceNames -notcontains $protected -and -not $podLabelNames.Contains($protected)) {
        Add-Warn "Protected service '$protected' was not found as a Service or pod label"
    }
}

if ($ShowLabels) {
    Write-Section "Labels"
    foreach ($pod in $podItems) {
        $labels = @()
        foreach ($property in @($pod.metadata.labels.PSObject.Properties)) { $labels += "$($property.Name)=$($property.Value)" }
        Write-Host "pod/$($pod.metadata.name): $($labels -join ', ')"
    }
    foreach ($svc in $serviceItems) {
        $labels = @()
        foreach ($property in @($svc.metadata.labels.PSObject.Properties)) { $labels += "$($property.Name)=$($property.Value)" }
        Write-Host "service/$($svc.metadata.name): $($labels -join ', ')"
    }
}

Write-Section "Next Commands"
Write-Host ".\scripts\configure-target.ps1 -TargetConfig <path-to-target.yaml>"
Write-Host ".\scripts\ensure-redpanda-topics.ps1"
Write-Host ".\scripts\accept-telemetry.ps1"
Write-Host "kubectl port-forward -n cascade-system svc/command-center 18300:8030"
Write-Host "Use dry-run chaos/remediation first. Live controlled failure injection is opt-in for local/dev/staging only."

Write-Section "Validation Result"
Write-Host "Passed:"; if ($Passed.Count -eq 0) { Write-Host "  - none" } else { foreach ($item in $Passed) { Write-Host "  - $item" } }
Write-Host ""; Write-Host "Warnings:"; if ($Warnings.Count -eq 0) { Write-Host "  - none" } else { foreach ($item in $Warnings) { Write-Host "  - $item" } }
Write-Host ""; Write-Host "Failed:"; if ($Failed.Count -eq 0) { Write-Host "  - none" } else { foreach ($item in $Failed) { Write-Host "  - $item" } }

if ($Failed.Count -gt 0) {
    Write-Host ""
    Write-Host "TARGET VALIDATION: FAIL"
    if ($Strict) { exit 1 }
    exit 0
}

Write-Host ""
Write-Host "TARGET VALIDATION: PASS"
exit 0
