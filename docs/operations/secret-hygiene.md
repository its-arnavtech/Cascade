# Secret Hygiene

Cascade is designed to be publishable as a local portfolio project without committing real credentials.

## Pre-Publish Audit

Run:

```powershell
.\scripts\audit-secrets.ps1
```

The script scans tracked files only, reports file path and matched key name, and does not print suspected values. It exits nonzero when it finds high-confidence non-placeholder assignments or private key blocks.

## Expected Safe Patterns

- `.env.example` contains placeholders only.
- Real `.env` files are ignored.
- Kubeconfigs, service account keys, private keys, cloud credentials, local backups, support bundles, and generated diagnostics are ignored.
- `EXECUTION_ENABLED=false` and `VITE_ENABLE_DANGEROUS_ACTIONS=false` remain the safe defaults.

## If A Secret Is Found

1. Remove the value and replace it with a placeholder.
2. Rotate the exposed credential if it was real.
3. Re-run `.\scripts\audit-secrets.ps1`.
4. Do not publish the repo until the audit passes.

The audit is a guardrail, not a full secret scanning product. Before public release, also review Git history and use a dedicated scanner if the repo has ever contained real credentials.
