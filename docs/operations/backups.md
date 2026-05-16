# Cascade Local Backup And Restore Runbook

Cascade Phase 10 adds local helper scripts for ClickHouse and Qdrant backups. These are intended for the local kind environment and portfolio demos. They are not a substitute for production storage replication, tested offsite backups, or disaster recovery automation.

## ClickHouse

Create a backup:

```powershell
.\scripts\backup-clickhouse.ps1
```

List backups:

```powershell
.\scripts\list-clickhouse-backups.ps1
```

Dry-run a restore:

```powershell
.\scripts\restore-clickhouse.ps1 -BackupPath backups\clickhouse\<timestamp>
```

Restore with explicit confirmation:

```powershell
.\scripts\restore-clickhouse.ps1 -BackupPath backups\clickhouse\<timestamp> -ConfirmRestore
```

The backup script exports every table from the `cascade` database as schema SQL plus `JSONEachRow` data and writes a `manifest.json` with table names, row counts, timestamp, backup method, namespace, and git commit when available.

Verify after restore:

```sql
SHOW TABLES FROM cascade;
SELECT count() FROM cascade.telemetry_events;
SELECT count() FROM cascade.investigation_runs;
SELECT count() FROM cascade.remediation_plans;
```

## Qdrant

Create snapshots for Cascade collections:

```powershell
.\scripts\backup-qdrant.ps1
```

List snapshots:

```powershell
.\scripts\list-qdrant-backups.ps1
```

Dry-run a restore:

```powershell
.\scripts\restore-qdrant.ps1 -BackupPath backups\qdrant\<timestamp>
```

Restore with explicit confirmation:

```powershell
.\scripts\restore-qdrant.ps1 -BackupPath backups\qdrant\<timestamp> -ConfirmRestore
```

Collections included:

- `cascade_incident_memory`
- `cascade_knowledge_base`

The backup script uses Qdrant collection snapshots through a local `kubectl port-forward`, downloads snapshot files, and writes a manifest with collection names, point counts, vector size, timestamp, and git commit when available.

## Limitations

- Local kind storage is not production durable.
- Backups are written under `backups/`, which is gitignored by default.
- Repeated demos and acceptance runs intentionally add rows; use latest-state queries for demos rather than assuming raw row counts are unique business objects.
- Production deployments should use persistent volumes, scheduled backups, encryption at rest, restore drills, and off-cluster storage.
