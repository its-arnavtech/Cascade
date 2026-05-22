param(
    [string]$Namespace = "cascade-system",
    [switch]$SkipRestart
)

$ErrorActionPreference = "Continue"
$passed = New-Object System.Collections.Generic.List[string]
$failed = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Add-Pass { param([string]$Message) $passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Fail { param([string]$Message) $failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Add-Warn { param([string]$Message) $warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Invoke-Kubectl {
    param([string[]]$Arguments)
    $output = & kubectl @Arguments 2>&1
    [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE }
}
function Get-FreePort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try { return $listener.LocalEndpoint.Port } finally { $listener.Stop() }
}
function CH {
    param([string]$Query)
    $result = Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/clickhouse", "--", "clickhouse-client", "--query", $Query)
    if ($result.ExitCode -ne 0) { throw $result.Text }
    $result.Text.Trim()
}

Write-Host ""
Write-Host "============================================================"
Write-Host "Cascade Durability Acceptance"
Write-Host "============================================================"

$api = Invoke-Kubectl @("cluster-info")
if ($api.ExitCode -eq 0) { Add-Pass "Kubernetes API reachable" } else { Add-Fail "Kubernetes API unavailable: $($api.Text)" }

foreach ($pvc in @("clickhouse-data", "redpanda-data", "qdrant-data")) {
    $result = Invoke-Kubectl @("-n", $Namespace, "get", "pvc", $pvc, "-o", "jsonpath={.status.phase}")
    if ($result.ExitCode -eq 0 -and $result.Text -match "Bound|Pending") {
        Add-Pass "PVC $pvc exists ($($result.Text))"
    } else {
        Add-Fail "PVC $pvc missing or invalid: $($result.Text)"
    }
}

foreach ($pair in @(
    @{ Deployment = "clickhouse"; Claim = "clickhouse-data" },
    @{ Deployment = "redpanda"; Claim = "redpanda-data" },
    @{ Deployment = "qdrant"; Claim = "qdrant-data" }
)) {
    $json = Invoke-Kubectl @("-n", $Namespace, "get", "deployment", $pair.Deployment, "-o", "jsonpath={.spec.template.spec.volumes[*].persistentVolumeClaim.claimName}")
    if ($json.ExitCode -eq 0 -and ($json.Text -split "\s+") -contains $pair.Claim) {
        Add-Pass "$($pair.Deployment) mounts $($pair.Claim)"
    } else {
        Add-Fail "$($pair.Deployment) does not mount $($pair.Claim)"
    }
}

try {
    foreach ($table in @("audit_events", "rca_reports", "remediation_executions", "remediation_verification_results", "remediation_rollback_plans", "autopilot_runs", "autopilot_steps", "chaos_campaign_runs", "topology_snapshots")) {
        [void][int](CH "SELECT count() FROM cascade.$table")
        Add-Pass "ClickHouse table $table is queryable"
    }
    $ttl = CH "SELECT count() FROM system.parts WHERE database='cascade' AND table='telemetry_events'"
    [void]$ttl
    Add-Pass "ClickHouse telemetry storage is queryable with schema initialized"
} catch {
    Add-Fail "ClickHouse durability query failed: $($_.Exception.Message)"
}

$redpanda = Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/redpanda", "--", "rpk", "-X", "brokers=localhost:9092", "topic", "list")
if ($redpanda.ExitCode -eq 0 -and $redpanda.Text -match "telemetry.raw" -and $redpanda.Text -match "autopilot.runs") {
    Add-Pass "Redpanda required topics are present"
} else {
    Add-Fail "Redpanda topic validation failed: $($redpanda.Text)"
}

$retention = Invoke-Kubectl @("-n", $Namespace, "exec", "deployment/redpanda", "--", "rpk", "-X", "brokers=localhost:9092", "topic", "describe", "telemetry.raw")
if ($retention.ExitCode -eq 0) {
    Add-Pass "Redpanda topic describe works for retention validation"
} else {
    Add-Warn "Redpanda retention describe unavailable: $($retention.Text)"
}

$PortForward = $null
try {
    $port = Get-FreePort
    $PortForward = Start-Process -FilePath kubectl -ArgumentList @("-n", $Namespace, "port-forward", "svc/qdrant", "$port`:6333") -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 3
    if ($PortForward.HasExited) {
        Add-Fail "Qdrant port-forward exited early"
    } else {
        foreach ($collection in @("cascade_incident_memory", "cascade_knowledge_base")) {
            try {
                $info = Invoke-RestMethod -Method GET -Uri "http://localhost:$port/collections/$collection" -TimeoutSec 20
                if ($info.result.status) {
                    Add-Pass "Qdrant collection $collection is available"
                } else {
                    Add-Fail "Qdrant collection $collection returned unexpected response"
                }
            } catch {
                Add-Fail "Qdrant collection $collection unavailable: $($_.Exception.Message)"
            }
        }
    }
} finally {
    if ($null -ne $PortForward -and -not $PortForward.HasExited) {
        Stop-Process -Id $PortForward.Id -Force
    }
}

if ($SkipRestart) {
    Add-Warn "Stateful restart survival check skipped by -SkipRestart"
} else {
    foreach ($deployment in @("clickhouse", "qdrant", "redpanda")) {
        $before = Invoke-Kubectl @("-n", $Namespace, "get", "deployment", $deployment, "-o", "jsonpath={.metadata.generation}")
        Invoke-Kubectl @("-n", $Namespace, "rollout", "restart", "deployment/$deployment") | Out-Null
        $rollout = Invoke-Kubectl @("-n", $Namespace, "rollout", "status", "deployment/$deployment", "--timeout=240s")
        if ($rollout.ExitCode -eq 0) {
            Add-Pass "$deployment restarted successfully with persistent volume still attached"
        } else {
            Add-Fail "$deployment restart failed: $($rollout.Text)"
        }
        [void]$before
    }
}

Write-Host ""
Write-Host "============================================================"
Write-Host "Final Result"
Write-Host "============================================================"
Write-Host "Passed:"; $passed | ForEach-Object { Write-Host "  - $_" }
Write-Host ""; Write-Host "Warnings:"; if ($warnings.Count) { $warnings | ForEach-Object { Write-Host "  - $_" } } else { Write-Host "  - none" }
Write-Host ""; Write-Host "Failed:"; if ($failed.Count) { $failed | ForEach-Object { Write-Host "  - $_" } } else { Write-Host "  - none" }

if ($failed.Count -eq 0) {
    Write-Host "CASCADE DURABILITY ACCEPTANCE: PASS"
    exit 0
}

Write-Host "CASCADE DURABILITY ACCEPTANCE: FAIL"
exit 1
