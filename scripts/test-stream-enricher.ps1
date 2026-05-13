param(
    [string]$Namespace = "cascade-system",
    [string]$KafkaDeployment = "kafka",
    [string]$StreamEnricherDeployment = "stream-enricher",
    [int]$ConsumeTimeoutMs = 15000
)

$ErrorActionPreference = "Stop"

Write-Host "Checking stream-enricher deployment"
kubectl -n $Namespace rollout status "deployment/$StreamEnricherDeployment" --timeout=120s

Write-Host ""
Write-Host "Recent stream-enricher logs"
kubectl -n $Namespace logs "deployment/$StreamEnricherDeployment" --tail=80

Write-Host ""
Write-Host "Sampling telemetry.enriched for up to $ConsumeTimeoutMs ms"
kubectl -n $Namespace exec "deploy/$KafkaDeployment" -- /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic telemetry.enriched --from-beginning --timeout-ms $ConsumeTimeoutMs --max-messages 5

Write-Host ""
Write-Host "Stream enricher stats endpoint:"
Write-Host "  kubectl -n $Namespace port-forward svc/stream-enricher 8001:8001"
Write-Host "  curl http://localhost:8001/stats"
