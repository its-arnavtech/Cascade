# Target Workload Template

This folder is a starting point for connecting an application you own or are authorized to test. It is not deployed by default.

## Use The Template

```powershell
cd C:\Cascade
Copy-Item -Recurse targets\template targets\my-app
```

Edit `targets/my-app`:

- Replace `my-app` with your target name.
- Replace `my-frontend` and other service names with your Kubernetes services.
- Keep stable labels on Pods and Services:
  - `app=<service-name>`
  - `app.kubernetes.io/name=<service-name>`
  - `app.kubernetes.io/part-of=<target-name>`
- Keep the namespace label `cascade.io/monitored=true`.
- Mark databases, brokers, caches, queues, auth stores, and stateful services as `protected_services`.
- Put only stateless services you own in `safe_chaos_services`.
- Define `dependency_edges` so Cascade can build topology and blast-radius views.

Deploy:

```powershell
kubectl apply -k targets\my-app
.\scripts\validate-target.ps1 -Namespace cascade-targets -TargetConfig targets\my-app\target.yaml -Strict
.\scripts\configure-target.ps1 -TargetConfig targets\my-app\target.yaml
```

Then ensure topics and validate telemetry:

```powershell
.\scripts\ensure-redpanda-topics.ps1
.\scripts\accept-telemetry.ps1
```

Start with dry-run chaos and dry-run remediation. Live controlled failure injection is opt-in local/dev/staging workflow only; do not run live chaos or remediation against production.
