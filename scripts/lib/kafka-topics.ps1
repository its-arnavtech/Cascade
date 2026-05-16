function Get-CascadeRedpandaTopicNames {
    param(
        [string]$Namespace = "cascade-system",
        [int]$Attempts = 6,
        [int]$SleepSeconds = 2
    )

    $lastRaw = ""
    $lastError = ""
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $podOutput = & kubectl -n $Namespace get pod -l app=redpanda -o "jsonpath={.items[0].metadata.name}" 2>&1
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace(($podOutput -join "`n"))) {
            $lastError = ($podOutput -join "`n")
            Start-Sleep -Seconds $SleepSeconds
            continue
        }

        $podName = ($podOutput -join "").Trim()
        $rawOutput = & kubectl -n $Namespace exec $podName -- rpk -X brokers=localhost:9092 topic list 2>&1
        $lastRaw = ($rawOutput -join "`n")
        if ($LASTEXITCODE -eq 0) {
            $names = New-Object System.Collections.Generic.List[string]
            foreach ($line in ($lastRaw -split "`r?`n")) {
                $trimmed = $line.Trim()
                if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
                if ($trimmed -match "^(NAME|TOPIC)\b") { continue }
                if ($trimmed -match "^-+$") { continue }
                $name = @($trimmed -split "\s+")[0]
                if (-not [string]::IsNullOrWhiteSpace($name) -and $name -notin @("NAME", "TOPIC")) {
                    $names.Add($name) | Out-Null
                }
            }
            return [pscustomobject]@{
                Success = $true
                Names = @($names | Select-Object -Unique)
                Raw = $lastRaw
                Error = ""
            }
        }

        $lastError = $lastRaw
        Start-Sleep -Seconds $SleepSeconds
    }

    [pscustomobject]@{
        Success = $false
        Names = @()
        Raw = $lastRaw
        Error = $lastError
    }
}

function Test-CascadeRedpandaTopic {
    param(
        [Parameter(Mandatory = $true)][string]$Topic,
        [string]$Namespace = "cascade-system",
        [int]$Attempts = 8,
        [int]$SleepSeconds = 2
    )

    $last = $null
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        $last = Get-CascadeRedpandaTopicNames -Namespace $Namespace -Attempts 1 -SleepSeconds $SleepSeconds
        if ($last.Success -and (@($last.Names) -contains $Topic)) {
            return [pscustomobject]@{
                Exists = $true
                Names = @($last.Names)
                Raw = $last.Raw
                Error = ""
            }
        }
        Start-Sleep -Seconds $SleepSeconds
    }

    [pscustomobject]@{
        Exists = $false
        Names = if ($null -eq $last) { @() } else { @($last.Names) }
        Raw = if ($null -eq $last) { "" } else { $last.Raw }
        Error = if ($null -eq $last) { "" } else { $last.Error }
    }
}
