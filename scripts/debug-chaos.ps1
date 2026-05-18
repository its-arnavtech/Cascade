param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets"
)

$ErrorActionPreference = "Continue"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Start-PF { param([string]$Service, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Service", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url) try { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 30 | ConvertTo-Json -Depth 20 } catch { "ERROR: $($_.Exception.Message)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if ($pod) { (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text } }

try {
    Write-Section "Namespace Status"
    kubectl -n $Namespace get pods,deployments,svc,endpoints -o wide

    Write-Section "Recent Events"
    kubectl -n $Namespace get events --sort-by=.lastTimestamp | Select-Object -Last 50

    Write-Section "Chaos Mesh CRDs"
    kubectl get crd podchaos.chaos-mesh.org networkchaos.chaos-mesh.org stresschaos.chaos-mesh.org

    Write-Section "Cascade-managed Chaos Resources"
    kubectl -n $TargetNamespace get podchaos,networkchaos,stresschaos -l cascade.io/phase=phase7 --ignore-not-found -o wide

    Write-Section "Redpanda Topics"
    kubectl -n $Namespace exec deployment/redpanda -- rpk topic list

    Write-Section "Chaos engineering ClickHouse Counts"
    foreach ($table in @("chaos_experiment_plans", "chaos_experiment_runs", "chaos_observations", "resilience_scores", "chaos_safety_violations")) {
        Write-Host "$table = $(CH "SELECT count() FROM cascade.$table")"
    }

    Write-Section "Recent Plans"
    CH "SELECT plan_id, status, experiment_kind, target_service, safety_score, risk_level, created_at FROM cascade.chaos_experiment_plans ORDER BY created_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Recent Runs"
    CH "SELECT run_id, plan_id, status, dry_run, cleanup_status, started_at FROM cascade.chaos_experiment_runs ORDER BY started_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Recent Observations"
    CH "SELECT observation_id, run_id, telemetry_events_count, anomaly_events_count, incidents_count, investigation_id FROM cascade.chaos_observations ORDER BY observed_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Recent Scores"
    CH "SELECT score_id, run_id, service, resilience_score, grade, computed_at FROM cascade.resilience_scores ORDER BY computed_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Recent Safety Violations"
    CH "SELECT violation_id, violation_type, severity, message, created_at FROM cascade.chaos_safety_violations ORDER BY created_at DESC LIMIT 8 FORMAT PrettyCompact"

    Write-Section "Service Logs"
    kubectl -n $Namespace logs deployment/chaos-planner-service --tail=120
    kubectl -n $Namespace logs deployment/chaos-executor-service --tail=180

    Start-PF "chaos-planner-service" "8019:8019"
    Start-PF "chaos-executor-service" "8020:8020"
    Write-Section "Health And Ready"
    HttpJson GET "http://localhost:8019/health"
    HttpJson GET "http://localhost:8019/ready"
    HttpJson GET "http://localhost:8020/health"
    HttpJson GET "http://localhost:8020/ready"

    Write-Section "Policy And Recent API Output"
    HttpJson GET "http://localhost:8020/safety/policy"
    HttpJson GET "http://localhost:8019/plans?limit=5"
    HttpJson GET "http://localhost:8020/runs?limit=5"
    HttpJson GET "http://localhost:8020/scores/recent?limit=5"
} finally {
    Stop-PF
}
