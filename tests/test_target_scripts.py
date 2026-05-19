from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_target_powershell_scripts_parse() -> None:
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if powershell is None:
        pytest.skip("PowerShell is not installed in this test environment")

    scripts = [
        ROOT / "scripts" / "validate-target.ps1",
        ROOT / "scripts" / "configure-target.ps1",
        ROOT / "scripts" / "demo-real-chaos.ps1",
        ROOT / "scripts" / "demo-real-remediation.ps1",
        ROOT / "scripts" / "enable-ui-live-demo.ps1",
        ROOT / "scripts" / "disable-ui-live-demo.ps1",
    ]
    for script in scripts:
        command = (
            "$errors=$null; "
            "$tokens=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr or result.stdout


def test_ui_live_demo_scripts_manage_only_explicit_flags() -> None:
    enable = (ROOT / "scripts" / "enable-ui-live-demo.ps1").read_text(encoding="utf-8")
    disable = (ROOT / "scripts" / "disable-ui-live-demo.ps1").read_text(encoding="utf-8")

    assert "kind-cascade" in enable
    assert "ConfirmLocalKind" in enable
    assert "CASCADE_ALLOWED_TARGET_NAMESPACE=$TargetNamespace" in enable
    assert "ENABLE_REAL_CHAOS=true" in enable
    assert "ENABLE_REAL_REMEDIATION=true" in enable
    assert "EXECUTION_ENABLED=true" in enable
    assert "deployment/command-center-api ENABLE_DANGEROUS_ACTIONS=true" in enable
    assert "/api/live-demo/status" in enable

    assert "ENABLE_REAL_CHAOS=false" in disable
    assert "ENABLE_REAL_REMEDIATION=false" in disable
    assert "EXECUTION_ENABLED=false" in disable
    assert "deployment/command-center-api ENABLE_DANGEROUS_ACTIONS=false" in disable
    assert "CASCADE_ACTIVE_CLUSTER_CONTEXT-" in disable
    assert "/api/live-demo/status" in disable
