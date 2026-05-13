param(
    [string]$Namespace = "cascade-system",
    [string]$KafkaDeployment = "kafka",
    [int]$ConsumeTimeoutMs = 10000
)

$ErrorActionPreference = "Stop"

Write-Host "Checking Kafka pods in namespace $Namespace"
kubectl -n $Namespace get pods -l app=kafka

Write-Host ""
Write-Host "Listing Kafka topics"
kubectl -n $Namespace exec "deploy/$KafkaDeployment" -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

Write-Host ""
Write-Host "Describing Cascade topics"
foreach ($topic in @("telemetry.raw", "telemetry.enriched", "experiments.events")) {
    Write-Host ""
    Write-Host "Topic: $topic"
    kubectl -n $Namespace exec "deploy/$KafkaDeployment" -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic $topic
}

Write-Host ""
Write-Host "Sampling telemetry.raw for up to $ConsumeTimeoutMs ms"
kubectl -n $Namespace exec "deploy/$KafkaDeployment" -- /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic telemetry.raw --from-beginning --timeout-ms $ConsumeTimeoutMs --max-messages 5
