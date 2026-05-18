param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets"
)

$ErrorActionPreference = "Stop"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$ChaosApplied = $false

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Output = @($output); Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url, [object]$Body = $null) if ($null -eq $Body) { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 10 } else { Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 20) -TimeoutSec 10 } }
function Cleanup { Stop-PF; if ($script:ChaosApplied) { Invoke-Kubectl @("delete", "-f", "scripts\pod-kill-catalogue.yaml", "--ignore-not-found=true") | Out-Null } }

try {
    Write-Section "Telemetry pipeline Demo"
    kubectl version --request-timeout=5s | Out-Null
    kubectl get namespace $TargetNamespace | Out-Null
    kubectl -n $TargetNamespace get pods
    kubectl -n $Namespace get endpoints redpanda
    $rpPod = kubectl -n $Namespace get pod -l app=redpanda -o jsonpath='{.items[0].metadata.name}'
    kubectl -n $Namespace exec $rpPod -- rpk -X brokers=localhost:9092 topic list

    foreach ($svc in @("observation-service:8000", "stream-enricher:8001", "experiment-tracker-service:8002", "causal-reconstruction-service:8005", "topology-service:8004", "incident-timeline-service:8006")) {
        $parts = $svc.Split(":")
        Start-PF $parts[0] "$($parts[1]):$($parts[1])"
        try {
            $h = HttpJson GET "http://localhost:$($parts[1])/health"
            Write-Host "$($parts[0]) health=$($h.status)"
        }
        finally {
            Stop-PF
        }
    }

    Write-Section "Create Experiment"
    Start-PF "experiment-tracker-service" "8002:8002"
    $experiment = HttpJson POST "http://localhost:8002/experiments" @{ experiment_type = "pod-kill"; target_service = "catalogue"; namespace = "cascade-targets"; duration_seconds = 30; chaos_mesh_resource = "kill-catalogue-once" }
    Stop-PF
    $experiment | ConvertTo-Json -Depth 10

    if (Test-Path "scripts\pod-kill-catalogue.yaml") {
        Write-Section "Apply PodChaos"
        kubectl apply -f scripts\pod-kill-catalogue.yaml
        $script:ChaosApplied = $true
    }

    Write-Section "Wait For Telemetry"
    Start-Sleep -Seconds 30

    Write-Section "Complete Experiment"
    Start-PF "experiment-tracker-service" "8002:8002"
    $experiment = HttpJson POST "http://localhost:8002/experiments/$($experiment.experiment_id)/complete"
    Stop-PF

    Write-Section "Reconstruct Incident"
    Start-PF "causal-reconstruction-service" "8005:8005"
    $incident = HttpJson POST "http://localhost:8005/reconstruct" @{ experiment_id = $experiment.experiment_id; lookback_seconds = 60; window_seconds = 300 }
    Stop-PF
    $incident | ConvertTo-Json -Depth 10

    Write-Section "Topology Impact"
    Start-PF "topology-service" "8004:8004"
    $impact = HttpJson POST "http://localhost:8004/topology/impact" @{ root_service = "catalogue" }
    Stop-PF
    $impact | ConvertTo-Json -Depth 10

    Write-Section "Incident Report"
    Start-PF "incident-timeline-service" "8006:8006"
    $report = HttpJson POST "http://localhost:8006/report" @{ experiment = $experiment; incident = $incident; topology_impact = $impact }
    Stop-PF
    Write-Host $report.markdown
}
finally {
    Cleanup
}
