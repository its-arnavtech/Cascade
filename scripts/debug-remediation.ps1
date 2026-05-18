param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets"
)

$ErrorActionPreference = "Continue"
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Start-PF { param([string]$Svc, [string]$Map) $p = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/$Svc", $Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p) | Out-Null; Start-Sleep -Seconds 2 }
function Stop-PF { foreach ($p in $script:PortForwards) { if ($null -ne $p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function HttpJson { param([string]$Method, [string]$Url) try { Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 30 | ConvertTo-Json -Depth 30 } catch { "ERROR: $($_.Exception.Message)" } }
function CH { param([string]$Query) $pod = (Invoke-Kubectl @("-n", $Namespace, "get", "pod", "-l", "app=clickhouse", "-o", "jsonpath={.items[0].metadata.name}")).Text.Trim(); if ($pod) { (Invoke-Kubectl @("-n", $Namespace, "exec", $pod, "--", "clickhouse-client", "--query", $Query)).Text } }

try {
    Write-Section "Namespace Status"
    kubectl -n $Namespace get pods,deployments,svc,endpoints -o wide
    Write-Section "Recent Events"
    kubectl -n $Namespace get events --sort-by=.lastTimestamp | Select-Object -Last 80
    Write-Section "Target Namespace Status"
    kubectl -n $TargetNamespace get pods,deployments,svc -o wide
    Write-Section "Redpanda Topics"
    kubectl -n $Namespace exec deployment/redpanda -- rpk topic list
    Write-Section "Remediation ClickHouse Counts"
    foreach ($table in @("remediation_plans", "remediation_approvals", "remediation_executions", "remediation_safety_violations", "remediation_policy_audit")) {
        Write-Host "$table = $(CH "SELECT count() FROM cascade.$table")"
    }
    Write-Section "Recent Remediation Plans"
    CH "SELECT plan_id, status, service, namespace, action_type, confidence, created_at FROM cascade.remediation_plans ORDER BY created_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Recent Approvals"
    CH "SELECT approval_id, plan_id, decision, approver, decided_at FROM cascade.remediation_approvals ORDER BY decided_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Recent Executions"
    CH "SELECT execution_id, plan_id, status, dry_run, executed, validation_status, started_at FROM cascade.remediation_executions ORDER BY started_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Recent Safety Violations"
    CH "SELECT violation_id, violation_type, severity, message, created_at FROM cascade.remediation_safety_violations ORDER BY created_at DESC LIMIT 8 FORMAT PrettyCompact"
    Write-Section "Service Logs"
    kubectl -n $Namespace logs deployment/remediation-recommender-service --tail=160
    kubectl -n $Namespace logs deployment/approval-service --tail=120
    kubectl -n $Namespace logs deployment/remediation-executor-service --tail=180
    Start-PF "remediation-recommender-service" "8021:8021"
    Start-PF "approval-service" "8022:8022"
    Start-PF "remediation-executor-service" "8023:8023"
    Write-Section "Health And Ready"
    HttpJson GET "http://localhost:8021/health"
    HttpJson GET "http://localhost:8021/ready"
    HttpJson GET "http://localhost:8022/health"
    HttpJson GET "http://localhost:8022/ready"
    HttpJson GET "http://localhost:8023/health"
    HttpJson GET "http://localhost:8023/ready"
    Write-Section "Policy And Recent API Output"
    HttpJson GET "http://localhost:8023/safety/policy"
    HttpJson GET "http://localhost:8021/plans?limit=5"
    HttpJson GET "http://localhost:8022/approvals?limit=5"
    HttpJson GET "http://localhost:8023/executions?limit=5"
} finally {
    Stop-PF
}
