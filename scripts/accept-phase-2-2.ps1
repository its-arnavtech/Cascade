param(
    [string]$Namespace = "cascade-system",
    [switch]$ChaosSmoke
)

$ErrorActionPreference = "Continue"

$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$ChaosApplied = $false
$RedpandaPodName = ""
$RedpandaContainerName = ""

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
    $lines = @($result.Output)
    $start = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = [string]$lines[$i]
        if ($line.TrimStart().StartsWith("{") -or $line.TrimStart().StartsWith("[")) {
            $start = $i
            break
        }
    }
    $jsonText = if ($start -ge 0) { ($lines[$start..($lines.Count - 1)] -join "`n") } else { $result.Text }
    try {
        return ($jsonText | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Test-KubectlConnectivity {
    $result = Invoke-Kubectl @("version", "--request-timeout=5s")
    if ($result.ExitCode -eq 0) {
        Add-Pass "Kubernetes API is reachable."
        return $true
    }
    Add-Fail "Kubernetes API is not reachable. $($result.Text)"
    return $false
}

function Test-DeploymentAvailable {
    param([string]$Name)
    $deployment = Get-KubectlJson @("-n", $Namespace, "get", "deployment", $Name, "-o", "json")
    if ($null -eq $deployment) {
        Add-Fail "Deployment $Name does not exist."
        return
    }

    $desired = [int]$deployment.spec.replicas
    $available = [int]$deployment.status.availableReplicas
    if ($desired -gt 0 -and $available -ge $desired) {
        Add-Pass "Deployment $Name is available ($available/$desired)."
    }
    else {
        Add-Fail "Deployment $Name is not available ($available/$desired)."
    }
}

function Get-PodsByLabel {
    param([string]$Label)
    $pods = Get-KubectlJson @("-n", $Namespace, "get", "pods", "-l", $Label, "-o", "json")
    if ($null -eq $pods) {
        return @()
    }
    return @($pods.items)
}

function Test-AppPodRunning {
    param(
        [string]$Name,
        [string]$Label
    )
    $pods = Get-PodsByLabel $Label
    if ($pods.Count -eq 0) {
        Add-Fail "$Name pod was not found with label $Label."
        return
    }

    $running = $false
    foreach ($pod in $pods) {
        $phase = [string]$pod.status.phase
        $ready = @($pod.status.containerStatuses | Where-Object { $_.ready -eq $true }).Count
        $total = @($pod.status.containerStatuses).Count
        Write-Host "$Name pod $($pod.metadata.name) phase=$phase ready=$ready/$total"
        if ($phase -eq "Running" -and $total -gt 0 -and $ready -eq $total) {
            $running = $true
        }
    }

    if ($running) {
        Add-Pass "$Name has a Running ready pod."
    }
    else {
        Add-Fail "$Name does not have a Running ready pod."
    }
}

function Discover-RedpandaPod {
    $pods = Get-PodsByLabel "app=redpanda"
    if ($pods.Count -eq 0) {
        Add-Fail "Redpanda pod was not found with label app=redpanda."
        return
    }

    $pod = $pods[0]
    $script:RedpandaPodName = [string]$pod.metadata.name
    $containers = @($pod.spec.containers | ForEach-Object { [string]$_.name })
    if ($containers.Count -gt 0) {
        $script:RedpandaContainerName = $containers[0]
    }

    $phase = [string]$pod.status.phase
    $ready = @($pod.status.containerStatuses | Where-Object { $_.ready -eq $true }).Count
    $total = @($pod.status.containerStatuses).Count
    Write-Host "Redpanda pod $script:RedpandaPodName phase=$phase ready=$ready/$total containers=$($containers -join ', ')"
    if ($phase -eq "Running" -and $ready -eq 1 -and $total -eq 1) {
        Add-Pass "Redpanda pod is 1/1 Running."
    }
    else {
        Add-Fail "Redpanda pod is not 1/1 Running."
    }
}

function Test-ServiceEndpoints {
    param([string]$ServiceName)
    $result = Invoke-Kubectl @("-n", $Namespace, "get", "endpoints", $ServiceName)
    $result.Output | ForEach-Object { Write-Host $_ }
    $endpointIp = (Invoke-Kubectl @("-n", $Namespace, "get", "endpoints", $ServiceName, "-o", "jsonpath={.subsets[0].addresses[0].ip}")).Text.Trim()
    $hasEndpoint = -not [string]::IsNullOrWhiteSpace($endpointIp)

    if ($hasEndpoint) {
        Add-Pass "service/$ServiceName has endpoints."
    }
    else {
        Add-Fail "service/$ServiceName has no endpoints."
    }
}

function Invoke-Rpk {
    param([string[]]$Arguments)
    if ([string]::IsNullOrWhiteSpace($script:RedpandaPodName) -or [string]::IsNullOrWhiteSpace($script:RedpandaContainerName)) {
        return [pscustomobject]@{ Output = @(); Text = ""; ExitCode = 1 }
    }
    $kubectlArgs = @("-n", $Namespace, "exec", $script:RedpandaPodName, "-c", $script:RedpandaContainerName, "--", "rpk", "-X", "brokers=localhost:9092") + $Arguments
    return Invoke-Kubectl $kubectlArgs
}

function Invoke-RpkTimed {
    param(
        [string[]]$Arguments,
        [int]$TimeoutSeconds = 6
    )
    if ([string]::IsNullOrWhiteSpace($script:RedpandaPodName) -or [string]::IsNullOrWhiteSpace($script:RedpandaContainerName)) {
        return [pscustomobject]@{ Output = @(); Text = ""; ExitCode = 1 }
    }

    $stdout = [System.IO.Path]::GetTempFileName()
    $stderr = [System.IO.Path]::GetTempFileName()
    $kubectlArgs = @("-n", $Namespace, "exec", $script:RedpandaPodName, "-c", $script:RedpandaContainerName, "--", "rpk", "-X", "brokers=localhost:9092") + $Arguments
    try {
        $process = Start-Process -FilePath "kubectl" -ArgumentList $kubectlArgs -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            Stop-Process -Id $process.Id -Force
            $exitCode = 124
        }
        else {
            $exitCode = $process.ExitCode
        }
        $output = @(Get-Content -LiteralPath $stdout -ErrorAction SilentlyContinue) + @(Get-Content -LiteralPath $stderr -ErrorAction SilentlyContinue)
        return [pscustomobject]@{
            Output = @($output)
            Text = ($output -join "`n")
            ExitCode = $exitCode
        }
    }
    finally {
        Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

function Test-Topics {
    $result = Invoke-Rpk -Arguments @("topic", "list")
    $result.Output | ForEach-Object { Write-Host $_ }
    if ($result.ExitCode -ne 0) {
        Add-Fail "Could not list topics using rpk."
        return
    }

    $missing = @()
    foreach ($topic in @("telemetry.raw", "telemetry.enriched", "experiments.events")) {
        if ($result.Text -notmatch [regex]::Escape($topic)) {
            $missing += $topic
        }
    }

    if ($missing.Count -eq 0) {
        Add-Pass "All required topics exist."
    }
    else {
        Add-Fail "Missing topics: $($missing -join ', ')."
    }
}

function Start-PortForward {
    param(
        [string]$ServiceName,
        [string]$PortMap
    )
    $process = Start-Process -FilePath "kubectl" -ArgumentList @("-n", $Namespace, "port-forward", "svc/$ServiceName", $PortMap) -WindowStyle Hidden -PassThru
    $script:PortForwards.Add($process) | Out-Null
    Start-Sleep -Seconds 2
    return $process
}

function Stop-PortForwards {
    foreach ($process in $script:PortForwards) {
        try {
            if ($null -ne $process -and -not $process.HasExited) {
                Stop-Process -Id $process.Id -Force
            }
        }
        catch {
            Write-Host "Failed to stop port-forward process $($process.Id): $($_.Exception.Message)"
        }
    }
    $script:PortForwards.Clear()
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

function Test-ObservationHttp {
    Start-PortForward "observation-service" "8000:8000" | Out-Null
    try {
        $health = Invoke-HttpJson "http://localhost:8000/health"
        if ($null -ne $health -and $health.status -eq "ok") {
            Add-Pass "observation-service /health returned ok."
        }
        else {
            Add-Fail "observation-service /health did not return ok."
        }

        $snapshot = Invoke-HttpJson "http://localhost:8000/snapshot" 20
        $pods = if ($null -ne $snapshot) { @($snapshot.pods) } else { @() }
        $targetPods = @($pods | Where-Object { $_.namespace -eq "cascade-targets" })
        if ($null -ne $snapshot -and $snapshot.namespace -eq "cascade-targets" -and $targetPods.Count -gt 0) {
            Add-Pass "observation-service /snapshot includes cascade-targets pods."
        }
        else {
            Add-Fail "observation-service /snapshot did not include cascade-targets pods."
        }
    }
    finally {
        Stop-PortForwards
    }
}

function Get-TopicMessage {
    param(
        [string]$Topic,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $command = "timeout 6 rpk -X brokers=localhost:9092 topic consume $Topic --num 1 --format '%v\n'"
        $result = Invoke-Kubectl @("-n", $Namespace, "exec", $script:RedpandaPodName, "-c", $script:RedpandaContainerName, "--", "/bin/bash", "-lc", $command)
        $candidate = @($result.Output | Where-Object {
            $line = [string]$_
            $line.TrimStart().StartsWith("{")
        } | Select-Object -First 1)
        if ($candidate.Count -gt 0) {
            return [string]$candidate[0]
        }
        Start-Sleep -Seconds 2
    }
    return ""
}

function Test-TopicFlow {
    param(
        [string]$Topic,
        [int]$TimeoutSeconds
    )
    $message = Get-TopicMessage $Topic $TimeoutSeconds
    if (-not [string]::IsNullOrWhiteSpace($message)) {
        Add-Pass "$Topic received at least one message within $TimeoutSeconds seconds."
        Write-Host "Sample $Topic message:"
        Write-Host $message
        return $message
    }
    Add-Fail "$Topic did not receive a message within $TimeoutSeconds seconds."
    return ""
}

function Test-EnrichedShape {
    param([string]$Message)
    if ([string]::IsNullOrWhiteSpace($Message)) {
        Add-Fail "Cannot validate enriched message shape because no enriched message was captured."
        return
    }
    try {
        $json = $Message | ConvertFrom-Json
    }
    catch {
        Add-Fail "Enriched message is not valid JSON."
        return
    }

    $missing = @()
    foreach ($key in @("event_id", "timestamp", "namespace", "pod_name", "service_name", "derived_status", "anomaly_flags", "ingestion_timestamp", "normalized_fields")) {
        if (@($json.PSObject.Properties.Name) -notcontains $key) {
            $missing += $key
        }
    }

    if ($missing.Count -eq 0) {
        Add-Pass "Enriched message contains all required fields."
    }
    else {
        Add-Fail "Enriched message is missing fields: $($missing -join ', ')."
    }
}

function Print-RecentLogs {
    param([string]$DeploymentName)
    Write-Host ""
    Write-Host "---- $DeploymentName logs ----"
    $result = Invoke-Kubectl @("-n", $Namespace, "logs", "deployment/$DeploymentName", "--tail=100")
    $result.Output | ForEach-Object { Write-Host $_ }

    $kafkaConnectionErrors = ([regex]::Matches($result.Text, "KafkaConnectionError")).Count
    if ($kafkaConnectionErrors -ge 3) {
        Add-Fail "$DeploymentName logs show persistent KafkaConnectionError ($kafkaConnectionErrors occurrences)."
    }
    elseif ($kafkaConnectionErrors -gt 0) {
        Add-Warn "$DeploymentName logs contain transient KafkaConnectionError ($kafkaConnectionErrors occurrence(s))."
    }

    foreach ($pattern in @("CrashLoopBackOff", "Connection refused", "Traceback")) {
        if ($result.Text -match [regex]::Escape($pattern)) {
            Add-Warn "$DeploymentName logs contain '$pattern'."
        }
    }
}

function Invoke-ChaosSmoke {
    $chaosPath = "scripts\pod-kill-cartservice.yaml"
    if (-not (Test-Path $chaosPath)) {
        Add-Warn "Chaos smoke requested, but $chaosPath does not exist."
        return
    }

    $apply = Invoke-Kubectl @("apply", "-f", $chaosPath)
    $apply.Output | ForEach-Object { Write-Host $_ }
    if ($apply.ExitCode -ne 0) {
        Add-Fail "Could not apply chaos smoke manifest."
        return
    }
    $script:ChaosApplied = $true
    Start-Sleep -Seconds 10

    $raw = Get-TopicMessage "telemetry.raw" 20
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
        Add-Pass "telemetry.raw still receives events during chaos smoke."
    }
    else {
        Add-Fail "telemetry.raw did not receive events during chaos smoke."
    }

    $enriched = Get-TopicMessage "telemetry.enriched" 30
    if (-not [string]::IsNullOrWhiteSpace($enriched)) {
        Add-Pass "telemetry.enriched still receives events during chaos smoke."
    }
    else {
        Add-Fail "telemetry.enriched did not receive events during chaos smoke."
    }
}

function Cleanup-Chaos {
    if ($script:ChaosApplied) {
        $delete = Invoke-Kubectl @("delete", "-f", "scripts\pod-kill-cartservice.yaml", "--ignore-not-found=true")
        $delete.Output | ForEach-Object { Write-Host $_ }
        $script:ChaosApplied = $false
    }
}

function Get-RecommendedFix {
    if ($script:Failed.Count -eq 0) {
        return "No fix needed. Phase 2.2 is ready for Phase 2.3."
    }
    $joined = $script:Failed -join " "
    if ($joined -match "Kubernetes API") {
        return "Start the kind cluster or switch to kind-cascade, then rerun acceptance."
    }
    if ($joined -match "Redpanda|service/redpanda|topics") {
        return "Fix Redpanda first: run .\scripts\debug-phase-2-2.ps1 and inspect infra/kubernetes/redpanda/."
    }
    if ($joined -match "telemetry.raw|observation-service") {
        return "Fix observation-service publisher or Prometheus snapshot path."
    }
    if ($joined -match "telemetry.enriched|stream-enricher|Enriched") {
        return "Fix stream-enricher consumer/producer path."
    }
    return "Run .\scripts\debug-phase-2-2.ps1 for a detailed report."
}

try {
    Write-Section "Phase 2.2 Redpanda Acceptance Test"
    Write-Host "Namespace: $Namespace"
    Write-Host "ChaosSmoke: $ChaosSmoke"
    Write-Host "Generated: $(Get-Date -Format o)"

    Write-Section "0. Kubernetes API"
    if (-not (Test-KubectlConnectivity)) {
        throw "Kubernetes API unreachable"
    }

    Write-Section "1. Namespace"
    if ($null -ne (Get-KubectlJson @("get", "namespace", $Namespace, "-o", "json"))) {
        Add-Pass "Namespace $Namespace exists."
    }
    else {
        Add-Fail "Namespace $Namespace does not exist."
    }

    Write-Section "2. Deployments"
    $deployments = Invoke-Kubectl @("-n", $Namespace, "get", "deployments")
    $deployments.Output | ForEach-Object { Write-Host $_ }
    foreach ($deployment in @("redpanda", "observation-service", "stream-enricher")) {
        Test-DeploymentAvailable $deployment
    }

    Write-Section "3. Pod Health"
    $pods = Invoke-Kubectl @("-n", $Namespace, "get", "pods", "-o", "wide")
    $pods.Output | ForEach-Object { Write-Host $_ }
    Discover-RedpandaPod
    Test-AppPodRunning "observation-service" "app=observation-service"
    Test-AppPodRunning "stream-enricher" "app=stream-enricher"

    Write-Section "4. Redpanda Endpoints"
    Test-ServiceEndpoints "redpanda"

    Write-Section "5. Topics"
    Test-Topics

    Write-Section "6. Observation Service HTTP"
    Test-ObservationHttp

    Write-Section "7. telemetry.raw Flow"
    $rawMessage = Test-TopicFlow "telemetry.raw" 20

    Write-Section "8. telemetry.enriched Flow"
    $enrichedMessage = Test-TopicFlow "telemetry.enriched" 30

    Write-Section "9. Enriched Message Shape"
    Test-EnrichedShape $enrichedMessage

    if ($ChaosSmoke) {
        Write-Section "10. Chaos Smoke"
        Invoke-ChaosSmoke
    }

    Write-Section "11. Recent Logs"
    Print-RecentLogs "redpanda"
    Print-RecentLogs "observation-service"
    Print-RecentLogs "stream-enricher"
}
catch {
    Add-Warn "Acceptance stopped early: $($_.Exception.Message)"
}
finally {
    Stop-PortForwards
    Cleanup-Chaos
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
    Write-Host "PHASE 2.2 ACCEPTANCE: PASS"
    exit 0
}

Write-Host "PHASE 2.2 ACCEPTANCE: FAIL"
exit 1
