# Installation on Kubernetes

For prerequisites, secrets, Kueue, ingress, and `kubectl apply -k kubernetes/base/`, follow **[`kubernetes/README.md`](../kubernetes/README.md)** first.

Optional: the repository may include an **`install-kubernetes.sh`** helper at the repo root that stages manifests and applies the stack; use it only if present in your checkout.

## Database migrations (automated)

Schema changes are applied **inside the cluster** before the API pod serves traffic:

1. The **`api` Deployment** defines an init container named **`run-migrations`**.
2. That container runs the **`migrations`** image (`ghcr.io/<owner>/reconhawx/migrations`), built from [`src/migrations/`](../src/migrations/).
3. It connects to the **`postgresql`** Service using the same credentials as the API (`postgres-secret` + `database.name` from `service-config`).
4. **By default**, every pending `V*__*.sql` file is **executed** against Postgres. This is required when migrations contain real DDL.

   **Optional:** set init-container env **`MIGRATIONS_BASELINE_AUTOMARK=1`** only if your migration files are bookkeeping for a DB that was already fully created from [`kubernetes/base/postgresql/schema.sql`](../kubernetes/base/postgresql/schema.sql) and you intentionally do **not** want that SQL run (same state as the dump). Leave it **`0`** (default in the Deployment) for normal upgrades.

   If wrong rows were inserted into `schema_migrations` without running SQL, remove them (e.g. `DELETE FROM schema_migrations WHERE version = '<version>';`) and restart the API pod so the init container runs again.

To use a **custom registry or tag**, keep these aligned:

- [`kubernetes/base/config/service-config.yaml`](../kubernetes/base/config/service-config.yaml) — key **`migrations.image`**
- [`kubernetes/base/api/api-deployment.yaml`](../kubernetes/base/api/api-deployment.yaml) — **`initContainers`** → **`run-migrations`** → **`image`**

**Logs and troubleshooting:**

```bash
kubectl logs -n reconhawx deploy/api -c run-migrations
kubectl describe pod -n reconhawx -l app=api
```

If the init container fails, the API container does not start until the migration issue is fixed and the Deployment rolls again.

**Local / CI outside the cluster:** you can still use [`scripts/migrate.sh`](../scripts/migrate.sh) or `python src/migrations/migrate.py` with `DATABASE_URL` (see [`AGENTS.md`](../AGENTS.md)).
