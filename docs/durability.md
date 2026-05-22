# Cascade Durability

Cascade local MVP state is now split into durable state, retained event streams, and explicitly ephemeral demo data. The goal is to keep evidence and history available after pod restarts without making first-time local kind setup heavy.

## Persistent State

The base Kubernetes manifests create single-node `ReadWriteOnce` PVCs:

| Component | PVC | Mount | Default size | Low-resource size |
|---|---:|---|---:|---:|
| ClickHouse | `clickhouse-data` | `/var/lib/clickhouse` | `10Gi` | `4Gi` |
| Redpanda | `redpanda-data` | `/var/lib/redpanda/data` | `5Gi` | `2Gi` |
| Qdrant | `qdrant-data` | `/qdrant/storage` | `5Gi` | `2Gi` |

ClickHouse stores durable operational history: telemetry windows, RCA reports, policy decisions, remediation executions, verification results, rollback plans, Autopilot history, chaos/campaign history, topology snapshots, and audit events. Qdrant stores semantic memory and knowledge vectors. Redpanda keeps short-lived replay buffers with explicit retention.

## Retention Defaults

ClickHouse applies TTL to high-volume tables:

| Table | Retention |
|---|---:|
| `telemetry_events` | 14 days |
| `telemetry_feature_windows` | 45 days |
| `anomaly_events` | 90 days |
| `experiment_events` | 90 days |
| `model_runs` | 90 days |

Audit, RCA, remediation, verification, rollback, Autopilot, topology, chaos, and campaign history are not TTL-deleted by default in the local MVP because they are lower-volume evidence records.

Redpanda topic retention is configured by the topic init job and `scripts/lib/kafka-topics.ps1`:

| Topic class | Retention |
|---|---:|
| `telemetry.raw` | 7 days / 512 MiB |
| `telemetry.enriched` | 14 days / 1 GiB |
| anomaly and experiment topics | 90 days / 256 MiB |
| investigation, chaos, remediation, Autopilot, causality topics | 180 days / 256 MiB |

## Backup

Create a complete local state backup:

```powershell
.\scripts\backup-cascade-state.ps1
```

Component backups remain available:

```powershell
.\scripts\backup-clickhouse.ps1
.\scripts\backup-qdrant.ps1
```

Backups are written under `backups/`, which is ignored by git. Scripts print locations and row/point counts, not secrets.

## Restore

Restore scripts dry-run by default. They require explicit confirmation before mutating stores:

```powershell
.\scripts\restore-clickhouse.ps1 -BackupPath backups\clickhouse\<timestamp>
.\scripts\restore-clickhouse.ps1 -BackupPath backups\clickhouse\<timestamp> -ConfirmRestore

.\scripts\restore-qdrant.ps1 -BackupPath backups\qdrant\<timestamp>
.\scripts\restore-qdrant.ps1 -BackupPath backups\qdrant\<timestamp> -ConfirmRestore
```

ClickHouse restore recreates schemas and truncates/restores listed tables. Qdrant restore uploads snapshots through a local port-forward and relies on Qdrant compatibility checks.

## Validation

Run durability acceptance:

```powershell
.\scripts\accept-durability.ps1
```

Use `-SkipRestart` to validate PVC wiring, ClickHouse tables, Redpanda topics, and Qdrant collections without restarting stateful pods:

```powershell
.\scripts\accept-durability.ps1 -SkipRestart
```

## Reset Guide

Most reset scripts redeploy component services and keep durable state unless a clear destructive flag is passed.

Storage reset:

```powershell
.\scripts\reset-storage-memory.ps1
```

Full local storage wipe for ClickHouse, Redpanda, and Qdrant:

```powershell
.\scripts\wipe-cascade-state.ps1 -ConfirmWipe
```

Component reset for storage and memory:

```powershell
.\scripts\reset-storage-memory.ps1 -WipePersistentData
```

The component reset wipe path deletes ClickHouse and Qdrant PVCs only. Use `wipe-cascade-state.ps1 -ConfirmWipe` when the Redpanda replay buffer should be removed too.

## Limits

This is durable local MVP storage, not production HA. Production still needs multi-replica storage design, encryption-at-rest policy, scheduled off-cluster backups, restore drills in CI/staging, retention sizing from real workloads, and authenticated access to backup locations.
