# Agent and contributor hub

Use this file as a **first stop** for how the repo is laid out and how to run common operations. Deeper conventions live in [`.cursor/rules/`](.cursor/rules/) (scoped by area) and service READMEs—avoid duplicating long prose here.

## Repository map

| Area | Role | Path |
|------|------|------|
| API | FastAPI backend | [`src/api/`](src/api/) |
| Frontend | React UI | [`src/frontend/`](src/frontend/) |
| Runner | Workflow and batch job orchestration | [`src/runner/`](src/runner/) |
| Worker | Workflow task worker (dispatched by runner) | [`src/worker/`](src/worker/) |
| CT-Monitor | Certificate transparency log monitoring | [`src/ct-monitor/`](src/ct-monitor/) |
| Event handler | Event consumers / handlers | [`src/event-handler/`](src/event-handler/) |
| Migrations | PostgreSQL schema migrations (SQL + CLI) | [`src/migrations/`](src/migrations/) |
| Kubernetes | Base manifests and Kueue (`kubectl apply -k kubernetes/base/`); user lifecycle: [`docs/install-on-kubernetes.md`](docs/install-on-kubernetes.md), [`docs/update-reconhawx.md`](docs/update-reconhawx.md), [`docs/uninstall-reconhawx.md`](docs/uninstall-reconhawx.md); scripts: [`.cursor/rules/k8s-cluster-lifecycle.mdc`](.cursor/rules/k8s-cluster-lifecycle.mdc) | [`kubernetes/`](kubernetes/) |

## Shell and devenv

Many dev tools live only on `PATH` after [devenv](https://devenv.sh/) loads (see [`devenv.nix`](devenv.nix): e.g. `kubectl`, `helm`, `docker`, `grype`, `node`/`npm`, Postgres client binaries, `k9s`, and others). **Agent and CI subshells often skip direnv**, so a bare command can fail with “not found” even though your interactive shell works.

From the **repository root**, wrap those invocations:

```bash
devenv shell -- kubectl get pods
devenv shell -- grype --version
```

[`migrate.sh`](scripts/migrate.sh) already prefers `.devenv/state/venv/bin/python` when that path exists; you do not need `devenv shell` just for that wrapper. Agent-facing detail: [`.cursor/rules/devenv-shell.mdc`](.cursor/rules/devenv-shell.mdc).

## Golden commands

### Database migrations

Set `DATABASE_URL` for your environment. The wrapper defaults to a local Postgres URL—see [`scripts/migrate.sh`](scripts/migrate.sh). If **`.devenv/state/venv/bin/python`** exists, the wrapper uses it (instead of system `python3`).

```bash
./scripts/migrate.sh status
./scripts/migrate.sh run --dry-run
./scripts/migrate.sh run
./scripts/migrate.sh create "Short description of change"
```

Equivalent CLI: `python src/migrations/migrate.py ...` (see [`src/migrations/migrate.py`](src/migrations/migrate.py)).

**Conventions** (versioning, UP/DOWN SQL, model alignment): [`.cursor/rules/migrations.mdc`](.cursor/rules/migrations.mdc). **UP migrations must be idempotent**: re-running against a DB that already matches (for example after a restore from [`kubernetes/base/postgresql/schema.sql`](kubernetes/base/postgresql/schema.sql)) or after a partial run must not fail. Patterns: `IF NOT EXISTS` / `IF EXISTS`, conditional `DO` blocks, `duplicate_object` for constraints—see the migrations rule.

**Kubernetes:** the API `Deployment` runs init containers before `uvicorn`: **`wait-for-postgresql`** (`postgres:15`, `pg_isready` against the `postgresql` Service and app database) then **`run-migrations`** (pending SQL). Image: **`run-migrations`** init container in [`kubernetes/base/api/api-deployment.yaml`](kubernetes/base/api/api-deployment.yaml) (semver tag aligned with [`kubernetes/base/config/reconhawx-version.yaml`](kubernetes/base/config/reconhawx-version.yaml) via [`kubernetes/base/components/pinned-releases`](kubernetes/base/components/pinned-releases/kustomization.yaml)). Logs: `kubectl logs -n reconhawx deploy/api -c run-migrations`. Entrypoint: [`src/migrations/k8s_entrypoint.py`](src/migrations/k8s_entrypoint.py). Optional env **`MIGRATIONS_BASELINE_AUTOMARK=1`** skips executing pending SQL when treating files as dump-only bookkeeping (default **`0`**: always run pending migrations). **In-cluster upgrades:** [`update-kubernetes.sh`](update-kubernetes.sh) / [`update-minikube.sh`](update-minikube.sh) apply [`kubernetes/base-update/`](kubernetes/base-update/kustomization.yaml) (no secret re-apply from git) and restart app deployments.

### Database backup and restore (admin UI)

Superusers use **Admin → System maintenance** (`/admin/system-maintenance`) to download a `pg_dump`, run **maintenance mode** (UI toggle → `system_settings`; optional env **`MAINTENANCE_MODE`** break-glass), **Hold** all Kueue **ClusterQueues** (graceful: running jobs finish), watch drain status, then restore. **Cluster restore** uses a Kubernetes **Job** only (`/admin/database/maintenance/restore/*`): staging upload on the API pod, Job `pg_restore`, mandatory dump cleanup on the Job pod. The API image installs **`postgresql-client-15`**. Restore is destructive (`--clean --if-exists`). After restore, **Redis/NATS** may be inconsistent with Postgres—plan runner restarts or cache/stream hygiene. See [`kubernetes/README.md`](kubernetes/README.md) for DB touchpoints, `dummy_batch`, and ordering.

### Kubernetes deploy

Preferred entrypoint is [`scripts/deploy.py`](scripts/deploy.py) (requires `rich`, `pyyaml`; Docker + `kubectl` for real deploys).

```bash
python scripts/deploy.py -e dev d all
python scripts/deploy.py -e dev d api
python scripts/deploy.py -e dev bd api
python scripts/deploy.py -e production d all
```

(Subcommands: `b` build, `d` deploy, `bd` build+deploy—see [`scripts/README.md`](scripts/README.md).)

**Detail** (service list, flags, build/deploy flows): [`scripts/README.md`](scripts/README.md), [`kubernetes/README.md`](kubernetes/README.md). **Ordering, kubectl snippets, environments**: [`.cursor/rules/kubernetes-deployment-operations.mdc`](.cursor/rules/kubernetes-deployment-operations.mdc).

### GitHub Container Registry (CI)

Workflow [`.github/workflows/docker-ghcr.yml`](.github/workflows/docker-ghcr.yml) pushes to `ghcr.io/<lowercase_github_owner>/reconhawx/<service>`. Images are built via **`workflow_call`** (chained from release-please after a release) or **`workflow_dispatch`** (manual). Both accept an optional `version` input for semver tagging. All **7** application images are built on every run (`api`, `frontend`, `migrations`, `runner`, `worker`, `event-handler`, `ct-monitor`). The **worker** image is **linux/amd64** and **linux/arm64** as one multi-arch manifest (`latest`, short SHA, optional release tag). **`build-worker-amd64`** and **`build-worker-arm64`** run in parallel on **`[self-hosted, linux, x64]`** and **`[self-hosted, linux, ARM64]`** (GitHub’s default architecture labels for self-hosted runners); add a native ARM64 host with the usual defaults or equivalent custom labels, push staging tags `<short-sha>-amd64` / `<short-sha>-arm64`, then **`merge-worker-manifest`** on **`ubuntu-latest`** runs `docker buildx imagetools create` to publish the real tags. Staging tags remain in GHCR unless you delete them manually.

### Versioning and releases

The project uses a **single semver** for all services, managed by [release-please](https://github.com/googleapis/release-please).

**Source of truth:** [`version.txt`](version.txt) (plain text, e.g. `0.1.0`). The same version is mirrored in [`src/frontend/package.json`](src/frontend/package.json) by release-please.

**Configuration:** [`release-please-config.json`](release-please-config.json) and [`.release-please-manifest.json`](.release-please-manifest.json). Workflow: [`.github/workflows/release-please.yml`](.github/workflows/release-please.yml).

**Release flow:**

1. Develop on feature branches, merge to `develop` via PR.
2. Merge `develop` into `main` via PR when ready to release.
3. release-please auto-creates a Release PR on `main` with a `CHANGELOG.md` update and version bump.
4. Merge the Release PR to publish: release-please tags `v<version>` and creates a GitHub Release.
5. The `v*` tag triggers `docker-ghcr.yml`, which builds all application images (including `migrations`) tagged with the semver.

**Conventional commits:** Commit messages on `main` must follow the [Conventional Commits](https://www.conventionalcommits.org/) format so release-please can determine the version bump. Key prefixes: `feat:` (minor bump), `fix:` (patch bump), `feat!:` / `BREAKING CHANGE:` footer (minor pre-1.0, major post-1.0). Prefixes like `chore:`, `docs:`, `ci:`, `refactor:` do not trigger a version bump. Scopes are optional (e.g. `feat(api): ...`). Feature-branch commits can be freeform if you squash-merge into `main`.

### Frontend local dev

See [`src/frontend/README.md`](src/frontend/README.md).

## Scoped Cursor rules (high level)

Browse [`.cursor/rules/`](.cursor/rules/). Entry points by component (globs in each file decide when it attaches):

| Component | Path | Rule files |
|-----------|------|------------|
| API | [`src/api/`](src/api/) | [`api-core.mdc`](.cursor/rules/api-core.mdc), [`api-data.mdc`](.cursor/rules/api-data.mdc), [`api-http.mdc`](.cursor/rules/api-http.mdc), [`api-testing.mdc`](.cursor/rules/api-testing.mdc), [`api-workflow-k8s.mdc`](.cursor/rules/api-workflow-k8s.mdc) |
| Frontend | [`src/frontend/`](src/frontend/) | [`frontend-architecture.mdc`](.cursor/rules/frontend-architecture.mdc), [`frontend-api-services.mdc`](.cursor/rules/frontend-api-services.mdc), [`frontend-component-patterns.mdc`](.cursor/rules/frontend-component-patterns.mdc), [`frontend-state-management.mdc`](.cursor/rules/frontend-state-management.mdc), [`frontend-workflow-builder.mdc`](.cursor/rules/frontend-workflow-builder.mdc) |
| Runner | [`src/runner/`](src/runner/) | [`runner-architecture.mdc`](.cursor/rules/runner-architecture.mdc), [`runner-job-management.mdc`](.cursor/rules/runner-job-management.mdc), [`runner-models.mdc`](.cursor/rules/runner-models.mdc), [`runner-task-patterns.mdc`](.cursor/rules/runner-task-patterns.mdc) |
| Worker | [`src/worker/`](src/worker/) | [`worker-architecture.mdc`](.cursor/rules/worker-architecture.mdc) |
| CT-Monitor | [`src/ct-monitor/`](src/ct-monitor/) | [`ct-monitor.mdc`](.cursor/rules/ct-monitor.mdc) |
| Event handler | [`src/event-handler/`](src/event-handler/) | [`event-handler-architecture.mdc`](.cursor/rules/event-handler-architecture.mdc), [`event-handler-integration.mdc`](.cursor/rules/event-handler-integration.mdc), [`event-handler-patterns.mdc`](.cursor/rules/event-handler-patterns.mdc) |
| Kubernetes | [`kubernetes/`](kubernetes/) | [`k8s-architecture.mdc`](.cursor/rules/k8s-architecture.mdc), [`k8s-deployment-operations.mdc`](.cursor/rules/k8s-deployment-operations.mdc), [`k8s-kustomize-patterns.mdc`](.cursor/rules/k8s-kustomize-patterns.mdc), [`k8s-nats-messaging.mdc`](.cursor/rules/k8s-nats-messaging.mdc) |
| Migrations | [`src/migrations/`](src/migrations/) | [`migrations.mdc`](.cursor/rules/migrations.mdc) |
| Always-on | — | [`project-hub.mdc`](.cursor/rules/project-hub.mdc), [`devenv-shell.mdc`](.cursor/rules/devenv-shell.mdc), [`dynamic-wordlists.mdc`](.cursor/rules/dynamic-wordlists.mdc) (`alwaysApply`) |

**Feature / domain rules** (narrow globs): [`typosquat-detection.mdc`](.cursor/rules/typosquat-detection.mdc), [`gather-typosquat-vendor-api.mdc`](.cursor/rules/gather-typosquat-vendor-api.mdc), [`broken-links-detection.mdc`](.cursor/rules/broken-links-detection.mdc), [`ai-analysis-runner.mdc`](.cursor/rules/ai-analysis-runner.mdc)

## Cursor skills (project)

Agent skills are markdown guides under [`.cursor/skills/`](.cursor/skills/). Cursor loads them when the task matches the skill `description`.

| Skill | Path | When to use |
|-------|------|-------------|
| Conventional commit | [`.cursor/skills/conventional-commit/SKILL.md`](.cursor/skills/conventional-commit/SKILL.md) | Preparing `feat`/`fix`/… commit messages (release-please), transcript-assisted intent, **approval before commit** |
| Database migrations | [`.cursor/skills/db-migrations/SKILL.md`](.cursor/skills/db-migrations/SKILL.md) | `migrate.sh` / schema migrations |
| Kubernetes deploy | [`.cursor/skills/kubernetes-deploy/SKILL.md`](.cursor/skills/kubernetes-deploy/SKILL.md) | `scripts/deploy.py`, cluster deploy |
| Runner workflow task | [`.cursor/skills/runner-workflow-task/SKILL.md`](.cursor/skills/runner-workflow-task/SKILL.md) | Runner tasks, worker dispatch |

## Agent workflow (minimal)

1. **Schema changes**: Add a new migration under `src/migrations/`; do not rewrite applied migration files. Keep SQLAlchemy models in sync (see migrations rule). Write **idempotent** UP SQL (same rule as above). Verify with `status` / `run --dry-run` before applying.
2. **Deploy / Kueue**: Public users deploy directly from `kubernetes/base/` (see [`kubernetes/README.md`](kubernetes/README.md)). Internal environments use `scripts/deploy.py` with private overlays under `kubernetes/overlays/` (gitignored). Respect infrastructure and app ordering from the k8s deployment rule when applying manually.
3. **Feature work**: Use the **Scoped Cursor rules** table above for the area you edit (API, frontend, runner, worker, event-handler, ct-monitor, k8s).

## Maintenance

When a change updates **how a component works**, **how to run or operate it**, or **invariants agents should follow**, update documentation in the **same** branch—do not leave `AGENTS.md`, READMEs, and Cursor rules drifting from the code.

**Typical touchpoints:**

| What changed | Prefer updating |
|--------------|-----------------|
| Any listed component (API, frontend, runner, worker, CT-monitor, event-handler) | Matching `.mdc` row in **Scoped Cursor rules**, and [`AGENTS.md`](AGENTS.md) if commands, paths, or overview change |
| Schema / migrations | [`migrations.mdc`](.cursor/rules/migrations.mdc), [`scripts/README.md`](scripts/README.md) if CLI changes |
| Deploy, overlays, Kueue, cluster layout | [`k8s-*.mdc`](.cursor/rules/), [`scripts/README.md`](scripts/README.md), [`kubernetes/README.md`](kubernetes/README.md), this file |
| [`scripts/`](scripts/) (deploy, migrate, init DB, admin user, …) | [`scripts/README.md`](scripts/README.md) and this file if behavior or flags change |
| CI: Docker builds to GHCR | This file (**GitHub Container Registry**), [`.github/workflows/docker-ghcr.yml`](.github/workflows/docker-ghcr.yml) |
| Versioning / release-please config | This file (**Versioning and releases**), [`release-please-config.json`](release-please-config.json), [`.release-please-manifest.json`](.release-please-manifest.json) |
| Agent skills (commit workflow, etc.) | [`.cursor/skills/`](.cursor/skills/) and **Cursor skills** table above |
| Domain features (e.g. typosquat, broken links, vendor API gather) | Respective feature `.mdc` under `.cursor/rules/` |

**Always-on or cross-cutting rules** ([`project-hub.mdc`](.cursor/rules/project-hub.mdc), [`devenv-shell.mdc`](.cursor/rules/devenv-shell.mdc), [`dynamic-wordlists.mdc`](.cursor/rules/dynamic-wordlists.mdc)): change when the hub instructions, devenv CLI conventions, or dynamic-wordlist behavior warrant it.

Optional link hygiene (local): `npx markdown-link-check -q AGENTS.md` if Node is available.
