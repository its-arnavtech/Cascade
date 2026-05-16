# CI/CD

Cascade uses GitHub Actions to validate the `main` branch safely. The workflow is validation-only: it does not deploy, publish images, require secrets, or require a live kind cluster.

## Workflow

Workflow file:

```text
.github/workflows/ci.yml
```

Triggers:

- Pull requests targeting `main`
- Pushes to `main`
- Manual `workflow_dispatch`

The workflow uses minimal repository permissions:

```yaml
permissions:
  contents: read
```

## Jobs

- `repo-hygiene`: checks required files, verifies generated sensitive directories are not tracked, runs `scripts/audit-secrets.ps1`, and prints basic git diagnostics.
- `python-tests`: installs service requirements, compiles `services` and `tests`, runs `pytest`, and runs Ruff.
- `frontend-build`: installs the Command Center dependencies, runs typecheck, and builds the Vite app.
- `powershell-parse`: parses every `scripts/*.ps1` file with the PowerShell parser.
- `k8s-manifest-validate`: parses every Kubernetes YAML file and runs client-side dry-run validation for core manifests without contacting a cluster.
- `docker-build-smoke`: builds representative Docker images locally on the runner and does not push them.
- `ci-summary`: reports job status and fails if any required job failed.

## What CI Does Not Do

- It does not deploy to kind or any cloud.
- It does not run phase acceptance scripts, because those require Docker Desktop/kind/Kubernetes state.
- It does not publish Docker images.
- It does not upload backups, support bundles, or environment files.
- It does not require GitHub secrets.

## Local Equivalent

Run the local mirror before pushing:

```powershell
pwsh ./scripts/ci-local.ps1 -SkipDockerBuild
```

For a fuller local smoke test with Docker available:

```powershell
pwsh ./scripts/ci-local.ps1
```

The local script supports:

- `-SkipFrontend`
- `-SkipDocker`
- `-SkipPython`
- `-SkipDockerBuild`
- `-ContinueOnFailure`

## Interpreting Failures

- Secret audit failures mean a tracked file likely contains a real credential-like value. Remove or replace it and rotate the credential if it was real.
- Python failures usually indicate service code, shared library, or test regressions.
- Frontend failures usually indicate TypeScript or Vite build regressions.
- PowerShell parse failures are syntax errors in operational scripts.
- Kubernetes YAML failures are manifest syntax or basic structure issues.
- Docker build failures indicate a Dockerfile or build-context regression.

## Future Deployment Options

A later workflow can add explicit image publishing or environment deployment, but it should be separate from this validation pipeline, require environment protection, and keep `contents: read` validation jobs independent from any write-capable release job.
