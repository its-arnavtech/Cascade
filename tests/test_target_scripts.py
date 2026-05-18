from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_target_powershell_scripts_parse() -> None:
    scripts = [
        ROOT / "scripts" / "validate-target.ps1",
        ROOT / "scripts" / "configure-target.ps1",
        ROOT / "scripts" / "demo-real-chaos.ps1",
        ROOT / "scripts" / "demo-real-remediation.ps1",
    ]
    for script in scripts:
        command = (
            "$errors=$null; "
            "$tokens=$null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr or result.stdout
