param(
    [string]$ClusterName = "cascade",
    [string]$TargetPath = "targets/sock-shop",
    [string]$TargetNamespace = "cascade-targets",
    [switch]$SkipContextSwitch
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function Invoke-Checked { param([string]$Description, [scriptblock]$Command) Write-Host ""; Write-Host "---- $Description ----"; & $Command; Assert-NativeSuccess $Description }
function Invoke-Kubectl {
    param([string[]]$Arguments)
    $output = & kubectl @Arguments 2>&1
    [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE }
}
function Get-KubectlJson {
    param([string[]]$Arguments)
    $result = Invoke-Kubectl $Arguments
    if ($result.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($result.Text)) { return $null }
    try { $result.Text | ConvertFrom-Json } catch { return $null }
}
function ConvertTo-IntOrDefault {
    param([object]$Value, [int]$Default = 0)
    if ($null -eq $Value) { return $Default }
    return [int]$Value
}
function Get-PodFailureReason {
    param([object]$Pod)
    $reasons = New-Object System.Collections.Generic.List[string]
    $badWaitingReasons = @("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull", "CreateContainerConfigError", "RunContainerError", "Error")
    if ($Pod.status.phase -eq "Failed") {
        $reasons.Add("pod phase Failed") | Out-Null
    }
    foreach ($status in @($Pod.status.initContainerStatuses) + @($Pod.status.containerStatuses)) {
        if ($null -eq $status) { continue }
        $waitingReason = [string]$status.state.waiting.reason
        if ($waitingReason -and ($badWaitingReasons -contains $waitingReason)) {
            $reasons.Add("$($status.name): $waitingReason") | Out-Null
        }
        $terminated = $status.state.terminated
        if ($null -ne $terminated -and [int]$terminated.exitCode -ne 0) {
            $reasons.Add("$($status.name): terminated exit $($terminated.exitCode) $($terminated.reason)") | Out-Null
        }
    }
    return ($reasons -join "; ")
}
function Get-FailingPods {
    $pods = Get-KubectlJson @("-n", $TargetNamespace, "get", "pods", "-o", "json")
    $failures = @()
    if ($null -eq $pods) { return @($failures) }
    foreach ($pod in @($pods.items)) {
        $reason = Get-PodFailureReason $pod
        if (-not [string]::IsNullOrWhiteSpace($reason)) {
            $failures += [pscustomobject]@{ Name = $pod.metadata.name; Reason = $reason }
        }
    }
    return @($failures)
}
function Write-TargetDiagnostics {
    param([string]$Reason, [object[]]$FailingPods = @())
    Write-Section "Sock Shop Target Diagnostics"
    Write-Host "Reason: $Reason"
    kubectl -n $TargetNamespace get pods
    foreach ($pod in @($FailingPods)) {
        Write-Host ""
        Write-Host "---- describe pod/$($pod.Name) ----"
        kubectl -n $TargetNamespace describe pod $pod.Name
        Write-Host ""
        Write-Host "---- logs pod/$($pod.Name) --tail=100 ----"
        kubectl -n $TargetNamespace logs $pod.Name --all-containers --tail=100
        Write-Host ""
        Write-Host "---- previous logs pod/$($pod.Name) --tail=100 ----"
        kubectl -n $TargetNamespace logs $pod.Name --all-containers --previous --tail=100 2>$null
    }
}
function Assert-NoFailedTargetPods {
    $failures = @(Get-FailingPods)
    if ($failures.Count -gt 0) {
        Write-TargetDiagnostics -Reason "Failing target pods detected" -FailingPods @($failures)
        throw (($failures | ForEach-Object { "$($_.Name): $($_.Reason)" }) -join "; ")
    }
}
function Assert-DeploymentAvailable {
    param([string]$Deployment)
    $deploymentJson = Get-KubectlJson @("-n", $TargetNamespace, "get", "deployment", $Deployment, "-o", "json")
    if ($null -eq $deploymentJson) { throw "deployment/$Deployment missing" }
    $desired = ConvertTo-IntOrDefault $deploymentJson.spec.replicas 1
    $available = ConvertTo-IntOrDefault $deploymentJson.status.availableReplicas 0
    if ($desired -gt 0 -and $available -lt $desired) {
        throw "deployment/$Deployment unavailable ($available/$desired)"
    }
}
function Assert-LoadTestHealthy {
    $deployment = Get-KubectlJson @("-n", $TargetNamespace, "get", "deployment", "load-test", "-o", "json")
    if ($null -ne $deployment) {
        Invoke-Checked "Wait for load-test rollout" { kubectl -n $TargetNamespace rollout status "deployment/load-test" --timeout=240s }
        Assert-DeploymentAvailable "load-test"
        return
    }
    $job = Get-KubectlJson @("-n", $TargetNamespace, "get", "job", "load-test", "-o", "json")
    if ($null -eq $job) { throw "load-test workload missing" }
    if ((ConvertTo-IntOrDefault $job.status.failed 0) -gt 0) { throw "job/load-test has failed pods" }
    if ((ConvertTo-IntOrDefault $job.status.succeeded 0) -lt 1 -and (ConvertTo-IntOrDefault $job.status.active 0) -lt 1) {
        throw "job/load-test is neither active nor complete"
    }
}

try {
    Write-Section "Deploy Sock Shop Target Workload"

    if (-not (Test-Path (Join-Path $TargetPath "kustomization.yaml"))) {
        throw "Target kustomization not found at $TargetPath"
    }

    Invoke-Checked "Verify kubectl can reach Kubernetes" { kubectl version --request-timeout=5s | Out-Null }

    if (-not $SkipContextSwitch) {
        Invoke-Checked "Use kind context" { kubectl config use-context "kind-$ClusterName" | Out-Null }
    }

    Invoke-Checked "Remove stale load-test Job if present" { kubectl -n $TargetNamespace delete job load-test --ignore-not-found=true }
    Invoke-Checked "Apply target manifests" { kubectl apply -k $TargetPath }

    Write-Section "Wait For Sock Shop Rollouts"
    foreach ($deployment in @("front-end", "catalogue", "catalogue-db", "carts", "carts-db", "orders", "orders-db", "payment", "shipping", "queue-master", "rabbitmq", "user", "user-db")) {
        Invoke-Checked "Wait for $deployment rollout" { kubectl -n $TargetNamespace rollout status "deployment/$deployment" --timeout=240s }
        Assert-DeploymentAvailable $deployment
        Assert-NoFailedTargetPods
    }
    Assert-LoadTestHealthy
    Assert-NoFailedTargetPods

    Write-Section "Sock Shop Target Ready"
    kubectl -n $TargetNamespace get deploy,svc,pods
    Write-Host ""
    Write-Host "Local access:"
    Write-Host "kubectl port-forward -n $TargetNamespace svc/front-end 18099:80"
    Write-Host "Open http://localhost:18099"
} catch {
    Write-Host "ERROR: $($_.Exception.Message)"
    try {
        $failures = @(Get-FailingPods)
        Write-TargetDiagnostics -Reason $_.Exception.Message -FailingPods @($failures)
    } catch {
        Write-Host "WARN: Failed to collect Sock Shop diagnostics: $($_.Exception.Message)"
    }
    exit 1
}
