# Experiment Tracker Service

Tracks Phase 2 chaos experiment metadata in memory and publishes experiment lifecycle events to `experiments.events`.

## Endpoints

- `GET /health`
- `POST /experiments`
- `GET /experiments`
- `GET /experiments/{experiment_id}`
- `POST /experiments/{experiment_id}/complete`

## Configuration

| Environment variable | Default |
| --- | --- |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` |
| `EXPERIMENT_TOPIC` | `experiments.events` |
