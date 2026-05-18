# Target Onboarding Checklist

Use this checklist before connecting an external Kubernetes application to Cascade.

- [ ] I own this workload or have explicit permission to perform reliability testing on it.
- [ ] I am using a local, development, or staging environment, not production.
- [ ] I deployed the workload into `cascade-targets` or another intentionally selected safe namespace.
- [ ] I labeled the namespace with `cascade.io/monitored=true`.
- [ ] My Pods and Services have stable labels: `app` or `app.kubernetes.io/name`.
- [ ] I identified only stateless services as candidates for controlled failure injection.
- [ ] I marked databases, brokers, caches, queues, auth stores, and other stateful services as protected.
- [ ] I defined service dependency edges in a target config.
- [ ] I validated the target with `.\scripts\validate-target.ps1 -Namespace <namespace> -TargetConfig <path> -Strict`.
- [ ] I configured Cascade with `.\scripts\configure-target.ps1 -TargetConfig <path>` or verified the equivalent environment/config mount.
- [ ] I ensured Redpanda topics with `.\scripts\ensure-redpanda-topics.ps1`.
- [ ] I verified telemetry with `.\scripts\accept-telemetry.ps1`.
- [ ] I ran dry-run chaos and remediation first.
- [ ] I reviewed topology and blast-radius output before considering any live test.
- [ ] I have rollback and recovery commands for the target workload.
- [ ] I understand live chaos and remediation are opt-in only and should not be run against production.
