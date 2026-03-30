---
name: runner-workflow-task
description: >-
  Implements or modifies Runner workflow tasks and worker dispatch (CommandSpec,
  generate_commands, task modules under src/runner). Use when adding or changing
  workflow steps, runner tasks, or worker task_name mappings for this project.
---

# Runner workflow tasks (Recon)

## Before you start

Read **`AGENTS.md`** for component paths (`src/runner/`, `src/worker/`). Detailed patterns:

- **`.cursor/rules/runner-architecture.mdc`** — runner layout and orchestration
- **`.cursor/rules/runner-task-patterns.mdc`** — `CommandSpec`, `generate_commands`, executor flow
- **`.cursor/rules/runner-job-management.mdc`** — jobs and Kueue-oriented behavior where applicable
- **`.cursor/rules/worker-architecture.mdc`** — worker side of dispatched commands

## Typical locations

- Task implementations: `src/runner/app/tasks/*.py`
- Executor / dispatch: `src/runner/app/task_executor.py` (and related modules per architecture rule)
- Worker handlers: `src/worker/app/` (mirror `task_name` from `CommandSpec`)

## Implementation checklist

1. Prefer **`generate_commands`** returning `CommandSpec` list; avoid legacy one-off executor paths described in the task patterns rule.
2. Keep **`task_name`** aligned with the worker entry that consumes the command.
3. Implement **`parse_output`** (and optional **`get_synthetic_assets`**) consistent with existing tasks in the same family.
4. **New asset kinds**: add **`AssetType`** if results must be stored for downstream steps (see **`runner-task-patterns.mdc`** — `store_assets` ignores non-enum keys). Add **`task_executor._resolve_step_output`** `asset_type_mapping` entries for new frontend output handle ids (e.g. `apex_domains` → `apex_domain`).
5. **New worker scripts**: add under **`src/worker/app/`**, **`COPY`** in **`src/worker/Dockerfile`**, rebuild worker image.
6. **Persisted fields on API assets** (e.g. WHOIS columns on `apex_domains`): migration + SQLAlchemy model + repository; align runner **`parse_output`** payloads with what **`create_or_update_*`** accepts.
7. **Frontend**: **`src/frontend/src/components/workflow/constants.js`** — `TASK_TYPES` entry (`inputs` / `outputs` / `params`) so the task appears in the builder and single-task run (uses `TASK_TYPES` keys).
8. If workflow definitions or job YAML change, update kubernetes/worker manifests per **`AGENTS.md`** deploy section and the k8s rules.

## When changing behavior

Update scoped `.mdc` rules or **`AGENTS.md`** only if you change how tasks are run, deployed, or discovered—not for every small task tweak.
