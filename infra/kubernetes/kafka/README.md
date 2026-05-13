# Archived Apache Kafka Manifests

These manifests are kept as source history for the earlier Apache Kafka KRaft attempt. They are not part of the current Phase 2 deployment path.

The active Phase 2 event backbone is Kafka-compatible Redpanda:

```powershell
.\scripts\deploy-phase-2.ps1
.\scripts\accept-phase-2.ps1
```

Use `infra/kubernetes/redpanda/` for the supported local kind broker.
