# Hardening: Production Hardening And Final Polish

Hardening makes Cascade safer to run, easier to debug, easier to demo, and safer to publish as a portfolio project.

## Hardening Changes

- Command Center UI deployment and acceptance remain the required final UI gate.
- Command Center API includes local in-memory rate limiting.
- Redpanda topic checks use exact topic matching and shared helper logic.
- ClickHouse, Redpanda, and Qdrant use local PVCs with low-resource overlay sizing.
- ClickHouse and Qdrant backup/list/restore helpers are available, plus an aggregate Cascade state backup.
- Redpanda topics have explicit local retention defaults.
- Secret audit and `.gitignore` hardening reduce publish risk.
- `docs/security.md` documents local mode, production-safe auth, approval binding, RBAC, ingress/TLS, and secret hygiene.
- Live chaos/remediation demo scripts require explicit local-kind opt-in, approval, and dry-run-first validation.
- `accept-all.ps1` provides a single end-to-end acceptance runner.
- `debug-all.ps1` creates a local support bundle.

## Rate Limiting

`command-center-api` reads:

- `RATE_LIMIT_ENABLED`
- `RATE_LIMIT_REQUESTS_PER_MINUTE`
- `RATE_LIMIT_BURST`

`/health` and `/ready` are exempt. HTTP `429` responses include JSON and `Retry-After`.

This is local single-pod protection only. Production should use an ingress, API gateway, or shared backing store such as Redis.

## Security

See [security.md](security.md) for Cascade's configurable auth guard, sensitive route protection, approval binding, least-privilege RBAC expectations, ingress/TLS guidance, and known limitations.

## Backups

ClickHouse scripts export schema and table data under `backups/clickhouse/<timestamp>/`.

Qdrant scripts create collection snapshots under `backups/qdrant/<timestamp>/`.

`backup-cascade-state.ps1` creates an aggregate folder with ClickHouse exports, Qdrant snapshots, Redpanda topic metadata, and a top-level manifest.

Restore scripts are dry-run by default and require `-ConfirmRestore`.

## Secret Hygiene

Run before publishing:

```powershell
.\scripts\audit-secrets.ps1
```

The scanner reports suspicious keys without values and fails on high-confidence non-placeholder assignments.

## Final Acceptance

```powershell
.\scripts\deploy.ps1
.\scripts\accept.ps1
.\scripts\accept-all.ps1
```

`CASCADE ACCEPTANCE: PASS` is printed only when every selected acceptance script exits successfully.

## Publishing Checklist

- Command Center UI acceptance passes.
- `accept-all.ps1` passes.
- `audit-secrets.ps1` passes.
- `.env.example` contains placeholders only.
- No real kubeconfigs, tokens, credentials, private keys, backups, or support bundles are tracked.
- README states that Cascade is production-inspired local infrastructure, not a production deployment.
- Live demo mode is disabled again after any local real-action demonstration.

## Future Work

- Production authentication and authorization.
- Distributed rate limiting.
- Network policies.
- Scheduled off-cluster backups.
- Restore drills in CI.
- Ingress/TLS/WAF configuration.
