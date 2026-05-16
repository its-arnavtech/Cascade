param(
    [string]$Namespace = "cascade-system"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\kafka-topics.ps1"

Write-Host "Ensuring Cascade Redpanda topics in namespace '$Namespace'..."
$result = Ensure-CascadeRedpandaTopics -Namespace $Namespace

if ($result.Success) {
    Write-Host "PASS: required Redpanda topics exist"
    foreach ($topic in $CascadeRequiredRedpandaTopics) {
        Write-Host "  - $topic"
    }
    exit 0
}

Write-Host "FAIL: one or more required Redpanda topics are missing"
Write-Host "Raw topic list:"
Write-Host $result.Raw
if ($result.Error) {
    Write-Host "Last error:"
    Write-Host $result.Error
}
exit 1
