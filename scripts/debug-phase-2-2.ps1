param(
    [string]$Namespace = "cascade-system",
    [switch]$FixImagePullPolicy,
    [switch]$Restart,
    [switch]$Watch
)

$ErrorActionPreference = "Continue"

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "============================================================"
}

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "---- $Title ----"
    try {
        & $Command
        if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
            Write-Host "Command exited with code $LASTEXITCODE"
        }
    }
    catch {
        Write-Host "Failed: $($_.Exception.Message)"
    }
}

function Get-Json {
    param([string[]]$KubectlArgs)
    try {
        $raw = & kubectl @KubectlArgs 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
            return $null
        }
        return ($raw | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Print-DeploymentEnv {
    param(
        [string]$DeploymentName,
        [string[]]$NamePatterns
    )
    $deployment = Get-Json @("-n", $Namespace, "get", "deployment", $DeploymentName, "-o", "json")
    if ($null -eq $deployment) {
        Write-Host "Deployment $DeploymentName not found."
        return
    }

    foreach ($container in $deployment.spec.template.spec.containers) {
        Write-Host "Container: $($container.name)"
        $matched = $false
        foreach ($env in @($container.env)) {
            foreach ($pattern in $NamePatterns) {
                if ($env.name -like $pattern) {
                    $matched = $true
                    $value = if ($null -ne $env.value) { $env.value } else { "<valueFrom>" }
                    Write-Host "  $($env.name)=$value"
                }
            }
        }
        if (-not $matched) {
            Write-Host "  No matching env vars found."
        }
    }
}

Write-Section "Phase 2.2 Redpanda Debug Report"
Write-Host "Namespace: $Namespace"
Write-Host "Generated: $(Get-Date -Format o)"
Write-Host "Mutating flags: FixImagePullPolicy=$FixImagePullPolicy Restart=$Restart Watch=$Watch"

Write-Section "0. Kubernetes API"
Invoke-Step "kubectl version --request-timeout=5s" {
    kubectl version --request-timeout=5s
}

if ($FixImagePullPolicy) {
    Write-Section "Requested Fix: imagePullPolicy Never"
    foreach ($deployment in @("observation-service", "stream-enricher")) {
        Invoke-Step "Patch $deployment imagePullPolicy" {
            kubectl -n $Namespace patch deployment $deployment --type='json' -p='[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Never"}]'
        }
    }
}

if ($Restart) {
    Write-Section "Requested Restart"
    foreach ($deployment in @("redpanda", "observation-service", "stream-enricher")) {
        Invoke-Step "Restart deployment/$deployment" {
            kubectl -n $Namespace rollout restart "deployment/$deployment"
        }
    }
}

Write-Section "1. Namespace"
Invoke-Step "kubectl get namespace $Namespace" {
    kubectl get namespace $Namespace
}

Write-Section "2. Pods"
Invoke-Step "kubectl get pods -n $Namespace -o wide" {
    kubectl get pods -n $Namespace -o wide
}

Write-Section "3. Deployments"
Invoke-Step "kubectl get deployments -n $Namespace" {
    kubectl get deployments -n $Namespace
}

Write-Section "4. Services"
Invoke-Step "kubectl get svc -n $Namespace" {
    kubectl get svc -n $Namespace
}

Write-Section "5. Redpanda Pod Discovery"
$redpandaPods = Get-Json @("-n", $Namespace, "get", "pods", "-l", "app=redpanda", "-o", "json")
$redpandaPodName = ""
$redpandaContainers = @()
if ($null -ne $redpandaPods -and @($redpandaPods.items).Count -gt 0) {
    $pod = @($redpandaPods.items)[0]
    $redpandaPodName = [string]$pod.metadata.name
    $redpandaContainers = @($pod.spec.containers | ForEach-Object { [string]$_.name })
    Write-Host "Redpanda pod: $redpandaPodName"
    Write-Host "Containers: $($redpandaContainers -join ', ')"
    foreach ($status in @($pod.status.containerStatuses)) {
        Write-Host "Container status: $($status.name) ready=$($status.ready) restartCount=$($status.restartCount)"
        if ($null -ne $status.lastState.terminated) {
            Write-Host "  last termination: reason=$($status.lastState.terminated.reason) exitCode=$($status.lastState.terminated.exitCode)"
        }
        if ($null -ne $status.state.waiting) {
            Write-Host "  waiting: reason=$($status.state.waiting.reason) message=$($status.state.waiting.message)"
        }
    }
}
else {
    Write-Host "No Redpanda pod found with label app=redpanda."
}

Write-Section "6. Redpanda Logs"
if (-not [string]::IsNullOrWhiteSpace($redpandaPodName)) {
    foreach ($container in $redpandaContainers) {
        Invoke-Step "Logs for $redpandaPodName container $container" {
            kubectl -n $Namespace logs $redpandaPodName -c $container --tail=160
        }
        Invoke-Step "Previous logs for $redpandaPodName container $container" {
            kubectl -n $Namespace logs $redpandaPodName -c $container --previous --tail=160
        }
    }
}
else {
    Write-Host "Skipped Redpanda logs because no pod was found."
}

Write-Section "7. Redpanda Pod Describe"
if (-not [string]::IsNullOrWhiteSpace($redpandaPodName)) {
    Invoke-Step "kubectl describe pod $redpandaPodName -n $Namespace" {
        kubectl describe pod $redpandaPodName -n $Namespace
    }
}

Write-Section "8. Redpanda Service Endpoints"
Invoke-Step "kubectl get endpoints redpanda -n $Namespace" {
    kubectl get endpoints redpanda -n $Namespace
}
Invoke-Step "kubectl describe svc redpanda -n $Namespace" {
    kubectl describe svc redpanda -n $Namespace
}

Write-Section "9. In-Cluster DNS And Port Probe"
$probeName = "cascade-phase-22-rp-debug-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
Invoke-Step "Run temporary netshoot probe pod" {
    kubectl -n $Namespace run $probeName --rm -i --restart=Never --image=nicolaka/netshoot --command -- /bin/sh -c "echo DNS lookup; nslookup redpanda.cascade-system.svc.cluster.local; echo Port probe; if command -v nc >/dev/null 2>&1; then nc -vz redpanda.cascade-system.svc.cluster.local 9092; else echo nc not available; fi"
}
if ($LASTEXITCODE -ne 0) {
    $busyboxName = "cascade-phase-22-rp-busybox-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    Invoke-Step "Fallback temporary busybox DNS probe" {
        kubectl -n $Namespace run $busyboxName --rm -i --restart=Never --image=busybox:1.36 --command -- /bin/sh -c "echo DNS lookup; nslookup redpanda.cascade-system.svc.cluster.local; echo Port probe; if command -v nc >/dev/null 2>&1; then nc -vz redpanda.cascade-system.svc.cluster.local 9092; else echo nc not available; fi"
    }
}

Write-Section "10. Topic Listing"
if (-not [string]::IsNullOrWhiteSpace($redpandaPodName) -and $redpandaContainers.Count -gt 0) {
    $container = $redpandaContainers[0]
    Invoke-Step "rpk topic list via localhost" {
        kubectl -n $Namespace exec $redpandaPodName -c $container -- rpk -X brokers=localhost:9092 topic list
    }
    Invoke-Step "rpk topic list via service DNS" {
        kubectl -n $Namespace exec $redpandaPodName -c $container -- rpk -X brokers=redpanda.cascade-system.svc.cluster.local:9092 topic list
    }
}
else {
    Write-Host "Skipped topic listing because no Redpanda pod/container was found."
}

Write-Section "11. Observation Service Logs"
Invoke-Step "kubectl -n $Namespace logs deployment/observation-service --tail=120" {
    kubectl -n $Namespace logs deployment/observation-service --tail=120
}

Write-Section "12. Stream Enricher Logs"
Invoke-Step "kubectl -n $Namespace logs deployment/stream-enricher --tail=120" {
    kubectl -n $Namespace logs deployment/stream-enricher --tail=120
}

Write-Section "13. Deployment Environment"
Write-Host "observation-service env:"
Print-DeploymentEnv "observation-service" @("KAFKA_BOOTSTRAP_SERVERS", "KAFKA_*", "TELEMETRY_*")
Write-Host ""
Write-Host "stream-enricher env:"
Print-DeploymentEnv "stream-enricher" @("KAFKA_BOOTSTRAP_SERVERS", "KAFKA_*", "HIGH_MEMORY_*")
Write-Host ""
Write-Host "redpanda command/env:"
kubectl -n $Namespace get deployment redpanda -o jsonpath='{.spec.template.spec.containers[0].command}{" "}{.spec.template.spec.containers[0].args}{"`n"}'

Write-Section "14. Resource Usage"
Invoke-Step "kubectl top pods -n $Namespace" {
    $topOutput = kubectl top pods -n $Namespace 2>&1
    $topOutput
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Metrics API is unavailable or metrics-server is not installed. Continuing."
    }
}

Write-Section "15. Diagnosis Hints"
Write-Host "If Redpanda is not Ready: inspect logs, resource pressure, and image pull state."
Write-Host "If service/redpanda has no endpoints: pod readiness or selector app=redpanda is wrong."
Write-Host "If apps show KafkaConnectionError: verify KAFKA_BOOTSTRAP_SERVERS=redpanda.cascade-system.svc.cluster.local:9092 and service endpoints exist."
Write-Host "If topics are missing: rerun kubectl apply -f infra/kubernetes/redpanda/topics-job.yaml after deleting the old job."

if ($Watch) {
    Write-Section "16. Watch Pods"
    kubectl get pods -n $Namespace -w
}
