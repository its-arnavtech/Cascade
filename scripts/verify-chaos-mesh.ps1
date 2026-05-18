param(
    [string]$ExpectedContext = "kind-cascade",
    [string]$TargetNamespace = "cascade-targets",
    [string]$ProtectedNamespace = "cascade-system",
    [switch]$AllowContextOverride
)

$ErrorActionPreference = "Continue"
$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]

function Add-Pass { param([string]$Message) $script:Passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Fail { param([string]$Message) $script:Failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Add-Warn { param([string]$Message) $script:Warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Text = ($output -join "`n"); ExitCode = $LASTEXITCODE } }
function Get-KubectlJson { param([string[]]$Arguments) $r = Invoke-Kubectl $Arguments; if ($r.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($r.Text)) { return $null }; try { $r.Text | ConvertFrom-Json } catch { return $null } }

Write-Host "Chaos Mesh verification"
$context = (Invoke-Kubectl @("config", "current-context")).Text.Trim()
if ($context -eq $ExpectedContext) {
    Add-Pass "Current kube context is $ExpectedContext"
} elseif ($AllowContextOverride) {
    Add-Warn "Current kube context is '$context'; expected '$ExpectedContext', override accepted"
} else {
    Add-Fail "Current kube context is '$context'; expected '$ExpectedContext'"
}

foreach ($crd in @("podchaos.chaos-mesh.org", "networkchaos.chaos-mesh.org", "stresschaos.chaos-mesh.org")) {
    $r = Invoke-Kubectl @("get", "crd", $crd)
    if ($r.ExitCode -eq 0) { Add-Pass "CRD $crd exists" } else { Add-Fail "CRD $crd missing" }
}

$controllers = Get-KubectlJson @("get", "pods", "-A", "-l", "app.kubernetes.io/name=chaos-mesh", "-o", "json")
if ($null -eq $controllers -or $controllers.items.Count -eq 0) {
    $controllers = Get-KubectlJson @("get", "pods", "-A", "-l", "app.kubernetes.io/component=controller-manager", "-o", "json")
}
if ($null -ne $controllers -and $controllers.items.Count -gt 0) {
    $notRunning = @($controllers.items | Where-Object { $_.status.phase -ne "Running" })
    if ($notRunning.Count -eq 0) { Add-Pass "Chaos Mesh controller pods are Running" } else { Add-Fail "Some Chaos Mesh controller pods are not Running" }
} else {
    Add-Fail "Chaos Mesh controller pods not found"
}

$target = Invoke-Kubectl @("get", "namespace", $TargetNamespace)
if ($target.ExitCode -eq 0) { Add-Pass "Target namespace $TargetNamespace exists" } else { Add-Fail "Target namespace $TargetNamespace missing" }

$protected = Invoke-Kubectl @("get", "role", "chaos-executor-targets", "-n", $ProtectedNamespace)
if ($protected.ExitCode -ne 0) { Add-Pass "$ProtectedNamespace has no chaos-executor target Role" } else { Add-Fail "$ProtectedNamespace unexpectedly has a chaos-executor target Role" }

$targetRole = Invoke-Kubectl @("get", "role", "chaos-executor-targets", "-n", $TargetNamespace)
if ($targetRole.ExitCode -eq 0) { Add-Pass "Chaos executor Role is scoped to $TargetNamespace" } else { Add-Warn "Chaos executor Role not found in $TargetNamespace; deploy Cascade chaos components before live demos" }

Write-Host ""
Write-Host "Passed:"; if ($Passed.Count -eq 0) { Write-Host "  - none" } else { foreach ($p in $Passed) { Write-Host "  - $p" } }
Write-Host "Warnings:"; if ($Warnings.Count -eq 0) { Write-Host "  - none" } else { foreach ($w in $Warnings) { Write-Host "  - $w" } }
Write-Host "Failed:"; if ($Failed.Count -eq 0) { Write-Host "  - none" } else { foreach ($f in $Failed) { Write-Host "  - $f" } }
if ($Failed.Count -gt 0) { exit 1 }
exit 0
