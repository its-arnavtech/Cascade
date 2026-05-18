param(
    [string]$Namespace = "cascade-system",
    [string]$TargetNamespace = "cascade-targets",
    [switch]$ChaosSmoke
)

$ErrorActionPreference = "Continue"
$Passed = New-Object System.Collections.Generic.List[string]
$Failed = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]
$PortForwards = New-Object System.Collections.Generic.List[System.Diagnostics.Process]
$ChaosApplied = $false
$RedpandaPodName = ""
$RedpandaContainerName = ""
$Experiment = $null
$Incident = $null
$Impact = $null
$Report = $null
. "$PSScriptRoot\lib\kafka-topics.ps1"

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "============================================================"; Write-Host $Title; Write-Host "============================================================" }
function Add-Pass { param([string]$Message) $script:Passed.Add($Message) | Out-Null; Write-Host "PASS: $Message" }
function Add-Fail { param([string]$Message) $script:Failed.Add($Message) | Out-Null; Write-Host "FAIL: $Message" }
function Add-Warn { param([string]$Message) $script:Warnings.Add($Message) | Out-Null; Write-Host "WARN: $Message" }
function Invoke-Kubectl { param([string[]]$Arguments) $output = & kubectl @Arguments 2>&1; [pscustomobject]@{ Output=@($output); Text=($output -join "`n"); ExitCode=$LASTEXITCODE } }
function Get-KubectlJson { param([string[]]$Arguments) $r=Invoke-Kubectl $Arguments; if($r.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($r.Text)){return $null}; $lines=@($r.Output); $start=-1; for($i=0;$i -lt $lines.Count;$i++){ $line=[string]$lines[$i]; if($line.TrimStart().StartsWith("{") -or $line.TrimStart().StartsWith("[")){ $start=$i; break } }; $jsonText=if($start -ge 0){($lines[$start..($lines.Count-1)] -join "`n")}else{$r.Text}; try { $jsonText | ConvertFrom-Json } catch { $null } }
function Start-PortForward { param([string]$Service,[string]$Map) $p=Start-Process -FilePath kubectl -ArgumentList @("-n",$Namespace,"port-forward","svc/$Service",$Map) -WindowStyle Hidden -PassThru; $script:PortForwards.Add($p)|Out-Null; Start-Sleep -Seconds 2 }
function Stop-PortForwards { foreach($p in $script:PortForwards){ if($null -ne $p -and -not $p.HasExited){ Stop-Process -Id $p.Id -Force } }; $script:PortForwards.Clear() }
function Invoke-HttpJson { param([string]$Method,[string]$Url,[object]$Body=$null,[int]$Retries=10) for($i=1;$i -le $Retries;$i++){ try { if($null -eq $Body){ return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 8 } $json=$Body|ConvertTo-Json -Depth 20; return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body $json -TimeoutSec 8 } catch { Start-Sleep -Seconds 1 } }; return $null }

function Test-Deployment { param([string]$Name) $d=Get-KubectlJson @("-n",$Namespace,"get","deployment",$Name,"-o","json"); if($null -eq $d){Add-Fail "Deployment $Name missing"; return}; $a=[int]$d.status.availableReplicas; $r=[int]$d.spec.replicas; if($r -gt 0 -and $a -ge $r){Add-Pass "Deployment $Name available"}else{Add-Fail "Deployment $Name not available ($a/$r)"} }
function Test-PodLabel { param([string]$Name,[string]$Label) $pods=Get-KubectlJson @("-n",$Namespace,"get","pods","-l",$Label,"-o","json"); if($null -eq $pods -or @($pods.items).Count -eq 0){Add-Fail "$Name pod missing"; return}; $ok=$false; foreach($pod in @($pods.items)){ $ready=@($pod.status.containerStatuses|Where-Object{$_.ready -eq $true}).Count; $total=@($pod.status.containerStatuses).Count; if($pod.status.phase -eq "Running" -and $total -gt 0 -and $ready -eq $total){$ok=$true} }; if($ok){Add-Pass "$Name pod Running"}else{Add-Fail "$Name pod not Running"} }
function Discover-Redpanda { $pods=Get-KubectlJson @("-n",$Namespace,"get","pods","-l","app=redpanda","-o","json"); if($null -eq $pods -or @($pods.items).Count -eq 0){Add-Fail "Redpanda pod missing"; return}; $pod=@($pods.items)[0]; $script:RedpandaPodName=$pod.metadata.name; $script:RedpandaContainerName=@($pod.spec.containers)[0].name; Test-PodLabel "redpanda" "app=redpanda" }
function Invoke-Rpk { param([string[]]$Arguments) if([string]::IsNullOrWhiteSpace($script:RedpandaPodName)){return [pscustomObject]@{Output=@();Text="";ExitCode=1}}; Invoke-Kubectl (@("-n",$Namespace,"exec",$script:RedpandaPodName,"-c",$script:RedpandaContainerName,"--","rpk","-X","brokers=localhost:9092")+$Arguments) }
function Invoke-RpkTimed {
    param([string[]]$Args,[int]$TimeoutSeconds=6)
    if([string]::IsNullOrWhiteSpace($script:RedpandaPodName)){return [pscustomObject]@{Output=@();Text="";ExitCode=1}}
    $stdout=[System.IO.Path]::GetTempFileName(); $stderr=[System.IO.Path]::GetTempFileName()
    $kubectlArgs=@("-n",$Namespace,"exec",$script:RedpandaPodName,"-c",$script:RedpandaContainerName,"--","rpk","-X","brokers=localhost:9092")+$Args
    try {
        $p=Start-Process -FilePath kubectl -ArgumentList $kubectlArgs -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if(-not $p.WaitForExit($TimeoutSeconds*1000)){ Stop-Process -Id $p.Id -Force; $exit=124 } else { $exit=$p.ExitCode }
        $out=@(Get-Content $stdout -ErrorAction SilentlyContinue)+@(Get-Content $stderr -ErrorAction SilentlyContinue)
        return [pscustomObject]@{Output=@($out);Text=($out -join "`n");ExitCode=$exit}
    } finally {
        Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
    }
}
function Get-TopicMessage { param([string]$Topic,[int]$Seconds) $deadline=(Get-Date).AddSeconds($Seconds); while((Get-Date)-lt $deadline){ $cmd="timeout 6 rpk -X brokers=localhost:9092 topic consume $Topic --num 1 --format '%v\n'"; $r=Invoke-Kubectl @("-n",$Namespace,"exec",$script:RedpandaPodName,"-c",$script:RedpandaContainerName,"--","/bin/bash","-lc",$cmd); $m=@($r.Output|Where-Object{([string]$_).TrimStart().StartsWith("{")}|Select-Object -First 1); if($m.Count -gt 0){return [string]$m[0]}; Start-Sleep -Seconds 2 }; "" }
function Test-Health { param([string]$Service,[int]$Port) Start-PortForward $Service "$Port`:$Port"; try { $h=Invoke-HttpJson GET "http://localhost:$Port/health"; if($null -ne $h -and $h.status -eq "ok"){Add-Pass "$Service healthy"}else{Add-Fail "$Service health failed"} } finally { Stop-PortForwards } }

function Cleanup-Chaos { if($script:ChaosApplied){ Invoke-Kubectl @("delete","-f","scripts\pod-kill-cartservice.yaml","--ignore-not-found=true") | Out-Null; $script:ChaosApplied=$false } }

try {
    Write-Section "Telemetry pipeline Acceptance"
    $api=Invoke-Kubectl @("version","--request-timeout=5s"); if($api.ExitCode -eq 0){Add-Pass "Kubernetes API reachable"}else{Add-Fail "Kubernetes API unreachable"; throw "No cluster"}
    if($null -ne (Get-KubectlJson @("get","namespace",$Namespace,"-o","json"))){Add-Pass "$Namespace exists"}else{Add-Fail "$Namespace missing"}
    if($null -ne (Get-KubectlJson @("get","namespace",$TargetNamespace,"-o","json"))){Add-Pass "$TargetNamespace exists"}else{Add-Fail "$TargetNamespace missing"}
    $targetPods=Get-KubectlJson @("-n",$TargetNamespace,"get","pods","-o","json"); if($null -ne $targetPods -and @($targetPods.items|Where-Object{$_.status.phase -eq "Running"}).Count -gt 0){Add-Pass "Online Boutique pods Running"}else{Add-Fail "Online Boutique pods not Running"}

    foreach($d in @("redpanda","observation-service","stream-enricher","experiment-tracker-service","topology-service","causal-reconstruction-service","incident-timeline-service")){ Test-Deployment $d }
    Discover-Redpanda
    foreach($pair in @(@("observation-service","app=observation-service"),@("stream-enricher","app=stream-enricher"),@("experiment-tracker-service","app=experiment-tracker-service"),@("topology-service","app=topology-service"),@("causal-reconstruction-service","app=causal-reconstruction-service"),@("incident-timeline-service","app=incident-timeline-service"))){ Test-PodLabel $pair[0] $pair[1] }

    $endpointIp=(Invoke-Kubectl @("-n",$Namespace,"get","endpoints","redpanda","-o","jsonpath={.subsets[0].addresses[0].ip}")).Text.Trim(); if(-not [string]::IsNullOrWhiteSpace($endpointIp)){Add-Pass "Redpanda service has endpoints"}else{Add-Fail "Redpanda service has no endpoints"}
    foreach($t in @("telemetry.raw","telemetry.enriched","experiments.events")){
        $topicCheck = Test-CascadeRedpandaTopic -Namespace $Namespace -Topic $t
        if($topicCheck.Exists){Add-Pass "Topic $t exists"}else{Add-Fail "Topic $t missing. Raw topic list: $($topicCheck.Raw)"}
    }

    Start-PortForward "observation-service" "8000:8000"; try { $h=Invoke-HttpJson GET "http://localhost:8000/health"; if($h.status -eq "ok"){Add-Pass "observation-service /health works"}else{Add-Fail "observation-service /health failed"}; $raw=Invoke-HttpJson GET "http://localhost:8000/metrics/raw?query=up" $null 15; if($null -ne $raw.prometheus){Add-Pass "Prometheus reachable through observation-service"}else{Add-Fail "Prometheus raw query failed"}; $snap=Invoke-HttpJson GET "http://localhost:8000/snapshot" $null 20; if($snap.namespace -eq "cascade-targets"){Add-Pass "observation-service /snapshot works"}else{Add-Fail "observation-service /snapshot failed"} } finally { Stop-PortForwards }
    Test-Health "stream-enricher" 8001

    $rawMsg=Get-TopicMessage "telemetry.raw" 20; if($rawMsg){Add-Pass "telemetry.raw receives messages"}else{Add-Fail "telemetry.raw no messages"}
    $enrichedMsg=Get-TopicMessage "telemetry.enriched" 30; if($enrichedMsg){Add-Pass "telemetry.enriched receives messages"}else{Add-Fail "telemetry.enriched no messages"}
    if($enrichedMsg){ try { $ej=$enrichedMsg|ConvertFrom-Json; $missing=@(); foreach($k in @("event_id","timestamp","namespace","pod_name","service_name","derived_status","anomaly_flags","ingestion_timestamp","normalized_fields")){ if(@($ej.PSObject.Properties.Name) -notcontains $k){$missing+=$k} }; if($missing.Count -eq 0){Add-Pass "Enriched message has required fields"}else{Add-Fail "Enriched missing fields: $($missing -join ', ')"} } catch { Add-Fail "Enriched message is not JSON" } }

    Test-Health "experiment-tracker-service" 8002
    Start-PortForward "experiment-tracker-service" "8002:8002"; try { $script:Experiment=Invoke-HttpJson POST "http://localhost:8002/experiments" @{experiment_type="pod-kill";target_service="cartservice";namespace="cascade-targets";duration_seconds=30;chaos_mesh_resource="kill-cartservice-once"} 10; if($null -ne $script:Experiment.experiment_id){Add-Pass "POST /experiments works"}else{Add-Fail "POST /experiments failed"} } finally { Stop-PortForwards }
    $expMsg=Get-TopicMessage "experiments.events" 20; if($expMsg){Add-Pass "experiments.events receives messages"}else{Add-Fail "experiments.events no messages"}

    Test-Health "topology-service" 8004
    Start-PortForward "topology-service" "8004:8004"; try { $script:Impact=Invoke-HttpJson POST "http://localhost:8004/topology/impact" @{root_service="cartservice"} 10; if($null -ne $script:Impact.affected_services){Add-Pass "Topology impact works"}else{Add-Fail "Topology impact failed"} } finally { Stop-PortForwards }

    Test-Health "causal-reconstruction-service" 8005
    Start-Sleep -Seconds 3
    Start-PortForward "causal-reconstruction-service" "8005:8005"; try { $eid=if($script:Experiment.experiment_id){$script:Experiment.experiment_id}else{"acceptance-smoke"}; $script:Incident=Invoke-HttpJson POST "http://localhost:8005/reconstruct" @{experiment_id=$eid;lookback_seconds=60;window_seconds=300} 10; if($null -ne $script:Incident.incident_id){Add-Pass "/reconstruct returns incident JSON"}else{Add-Fail "/reconstruct failed"} } finally { Stop-PortForwards }

    Test-Health "incident-timeline-service" 8006
    Start-PortForward "incident-timeline-service" "8006:8006"; try { $script:Report=Invoke-HttpJson POST "http://localhost:8006/report" @{experiment=$script:Experiment;incident=$script:Incident;topology_impact=$script:Impact} 10; if($null -ne $script:Report.markdown -and $null -ne $script:Report.summary){Add-Pass "/report returns JSON and Markdown"}else{Add-Fail "/report failed"} } finally { Stop-PortForwards }

    if($ChaosSmoke -and (Test-Path "scripts\pod-kill-cartservice.yaml")){ $apply=Invoke-Kubectl @("apply","-f","scripts\pod-kill-cartservice.yaml"); if($apply.ExitCode -eq 0){$script:ChaosApplied=$true; Add-Pass "Chaos smoke applied"; Start-Sleep -Seconds 15; if(Get-TopicMessage "telemetry.raw" 20){Add-Pass "Events flow during chaos"}else{Add-Fail "No raw events during chaos"} }else{Add-Fail "Chaos smoke apply failed"} }

    $podsText=(Invoke-Kubectl @("-n",$Namespace,"get","pods")).Text; if($podsText -match "CrashLoopBackOff"){Add-Fail "CrashLoopBackOff detected"}else{Add-Pass "No CrashLoopBackOff detected"}
    foreach($svc in @("redpanda","observation-service","stream-enricher","experiment-tracker-service","causal-reconstruction-service","topology-service","incident-timeline-service")){ $logs=(Invoke-Kubectl @("-n",$Namespace,"logs","deployment/$svc","--tail=80")).Text; $fatal=([regex]::Matches($logs,"Traceback|FATAL|KafkaConnectionError")).Count; if($fatal -ge 3){Add-Fail "$svc logs show persistent fatal exceptions"} }
} catch { Add-Warn "Acceptance stopped early: $($_.Exception.Message)" } finally { Stop-PortForwards; Cleanup-Chaos }

Write-Section "Final Result"
Write-Host "Passed:"; if($Passed.Count -eq 0){Write-Host "  - none"}else{foreach($p in $Passed){Write-Host "  - $p"}}
Write-Host ""; Write-Host "Warnings:"; if($Warnings.Count -eq 0){Write-Host "  - none"}else{foreach($w in $Warnings){Write-Host "  - $w"}}
Write-Host ""; Write-Host "Failed:"; if($Failed.Count -eq 0){Write-Host "  - none"}else{foreach($f in $Failed){Write-Host "  - $f"}}
Write-Host ""; if($Failed.Count -eq 0){Write-Host "TELEMETRY ACCEPTANCE: PASS"; exit 0}
Write-Host "Recommended next fix:"; if(($Failed -join " ") -match "Redpanda|Topic|telemetry"){Write-Host "  Run .\scripts\debug-redpanda-legacy.ps1 and inspect Redpanda/topics first."}else{Write-Host "  Fix the first failed service check above, then rerun acceptance."}
Write-Host "TELEMETRY ACCEPTANCE: FAIL"; exit 1
