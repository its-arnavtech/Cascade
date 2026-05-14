param(
    [string]$ClusterName = "cascade",
    [string]$Namespace = "cascade-system",
    [switch]$ClearPhase6Tables
)

$ErrorActionPreference = "Stop"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Assert-NativeSuccess { param([string]$Description) if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE" } }
function CH { param([string]$Query) $pod = (kubectl -n $Namespace get pod -l app=clickhouse -o jsonpath="{.items[0].metadata.name}"); if ($pod) { kubectl -n $Namespace exec $pod -- clickhouse-client --query $Query; Assert-NativeSuccess "ClickHouse query" } }

Write-Section "Reset Cascade Phase 6"
kubectl config use-context "kind-$ClusterName" | Out-Null
kubectl -n $Namespace delete deployment agent-orchestrator-service agent-tool-gateway --ignore-not-found=true
kubectl -n $Namespace delete service agent-orchestrator-service agent-tool-gateway --ignore-not-found=true

if ($ClearPhase6Tables) {
    Write-Section "Clear Phase 6 Tables"
    foreach ($table in @("investigation_runs", "agent_steps", "investigation_reports", "agent_tool_calls")) {
        CH "TRUNCATE TABLE IF EXISTS cascade.$table"
    }
}

Write-Section "Redeploy Phase 6"
& .\scripts\deploy-phase-6.ps1 -ClusterName $ClusterName -Namespace $Namespace -SkipPhase5Deploy
Assert-NativeSuccess "Deploy Phase 6"
Write-Host "PHASE 6 RESET: PASS"
