---
name: db-migrations
description: >-
  Runs and authors PostgreSQL schema migrations for this repo using Alembic
  (scripts/migrate.sh, src/migrations/alembic.ini). Use when the user or task
  involves database schema changes, migration status, rollbacks, or alignment
  between Alembic revisions and SQLAlchemy models.
---

# Database migrations (Recon)

## Before you start

Read **`AGENTS.md`** (repo root) for the command index. Conventions live in **`.cursor/rules/migrations.mdc`**.

Set **`DATABASE_URL`** or **`POSTGRES_*`** for the target database. The shell wrapper builds a default local URL if **`DATABASE_URL`** is unset.

**Interpreter:** `scripts/migrate.sh` uses **`.devenv/state/venv/bin/python`** when present (devenv). Ensure **`alembic`** is installed—root **`requirements.txt`** and **`src/migrations/requirements.txt`** list it; sync the devenv venv if `import alembic` fails.

## Commands

From the repository root:

```bash
./scripts/migrate.sh status
./scripts/migrate.sh run --dry-run
./scripts/migrate.sh run
./scripts/migrate.sh create "Short description"
./scripts/migrate.sh validate
./scripts/migrate.sh history
```

`python src/migrations/migrate.py …` forwards to **`python -m alembic -c src/migrations/alembic.ini`**.

## Workflow for schema changes

1. Edit SQLAlchemy models under `src/api/app/models/` as needed.
2. **`./scripts/migrate.sh create "…"`** (autogenerate). Review **`src/migrations/alembic/versions/`** output—especially around unmapped tables (see **`include_object`** in **`alembic/env.py`**).
3. **`./scripts/migrate.sh run`** locally.
4. **`./scripts/refresh_schema.sh`** then commit **`kubernetes/base/postgresql/schema.sql`** with the new revision.
5. Never rewrite Alembic revision files that are already applied in shared environments—add a new revision.

## References

- Wrapper: `scripts/migrate.sh`
- Revisions: `src/migrations/alembic/versions/`
- K8s entrypoint: `src/migrations/k8s_entrypoint.py`
- Models: `src/api/app/models/postgres.py`, `refresh_token.py`
