# Cascade Kafka Local Development

This starts a single-node Kafka broker in KRaft mode for Phase 2.2. It exposes Kafka on `localhost:9092` and creates:

- `telemetry.raw`
- `telemetry.enriched`
- `experiments.events`

## Start Kafka

```powershell
docker compose -f infra/kafka/docker-compose.yaml up -d
```

## Verify Topics

```powershell
docker exec cascade-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

## Inspect Messages

Consume raw telemetry:

```powershell
docker exec -it cascade-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic telemetry.raw --from-beginning
```

Consume enriched telemetry:

```powershell
docker exec -it cascade-kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic telemetry.enriched --from-beginning
```

Produce an experiment event:

```powershell
'{"experiment_id":"exp-001","experiment_type":"pod-kill","target_service":"cartservice","namespace":"cascade-targets","started_at":"2026-05-13T00:00:00Z","duration":60,"chaos_mesh_resource":"pod-kill-cartservice","status":"running"}' |
  docker exec -i cascade-kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic experiments.events
```

## Stop Kafka

```powershell
docker compose -f infra/kafka/docker-compose.yaml down
```
