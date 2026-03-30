---
name: db-migrations
description: >-
  Runs and authors PostgreSQL schema migrations for this repo using scripts/migrate.sh
  or src/migrations/migrate.py. Use when the user or task involves database schema changes,
  migration status, rollbacks, or alignment between SQL migrations and SQLAlchemy models.
---

# Database migrations (Recon)

## Before you start

Read **`AGENTS.md`** (repo root) for the one-line command index. Full SQL conventions and versioning live in **`.cursor/rules/migrations.mdc`**.

Set **`DATABASE_URL`** for the target database. The shell wrapper defaults to a local Postgres URL if unset—confirm before `run`.

**Interpreter:** `scripts/migrate.sh` uses **`.devenv/state/venv/bin/python`** when that path exists (devenv); otherwise **`python3`**. Use the same when invoking `migrate.py` directly so imports like `psycopg2` resolve.

## Commands

From the repository root:

```bash
./scripts/migrate.sh status
./scripts/migrate.sh run --dry-run
./scripts/migrate.sh run
./scripts/migrate.sh create "Short description"
./scripts/migrate.sh validate
```

Python entrypoint (equivalent subcommands): `.devenv/state/venv/bin/python src/migrations/migrate.py …` or `python3 src/migrations/migrate.py …` (match the wrapper’s interpreter).

## Workflow for schema changes

1. Add a new migration file under `src/migrations/` following `V{major}.{minor}.{patch}__{description}.sql` (see the migrations rule).
2. Update SQLAlchemy models in `src/api/app/models/` as needed so code matches the schema.
3. Never edit migration files that are already applied in shared environments.
4. Prefer `run --dry-run` before applying.

## References

- Wrapper: `scripts/migrate.sh`
- CLI implementation: `src/migrations/cli.py`
- Models (typical touchpoint): `src/api/app/models/postgres.py`
