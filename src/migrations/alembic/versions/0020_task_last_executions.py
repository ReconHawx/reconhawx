"""Add task_last_executions summary table for runner last-execution checks.

Revision ID: v019_task_last_executions
Revises: v018_tte_task_params

One row per ingested asset (asset_id) or direct input string (target_key) with last
successful run time, keyed by task_type and params_fingerprint.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v019_task_last_executions"
down_revision: Union[str, Sequence[str], None] = "v018_tte_task_params"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS public.task_last_executions (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                program_id uuid NOT NULL REFERENCES public.programs(id) ON DELETE CASCADE,
                task_type text NOT NULL,
                asset_type text NOT NULL,
                asset_id uuid,
                target_key text,
                params_fingerprint text NOT NULL,
                last_success_at timestamp without time zone NOT NULL,
                updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT task_last_executions_asset_type_check CHECK (
                    asset_type IN (
                        'subdomain',
                        'apex_domain',
                        'ip',
                        'url',
                        'service',
                        'certificate',
                        'target'
                    )
                ),
                CONSTRAINT task_last_executions_target_or_asset_check CHECK (
                    (asset_id IS NOT NULL AND target_key IS NULL)
                    OR (asset_id IS NULL AND target_key IS NOT NULL)
                )
            );

            CREATE INDEX IF NOT EXISTS ix_task_last_executions_eligible
                ON public.task_last_executions (
                    program_id,
                    task_type,
                    asset_type,
                    params_fingerprint,
                    last_success_at DESC
                );

            CREATE INDEX IF NOT EXISTS ix_task_last_executions_asset
                ON public.task_last_executions (asset_type, asset_id);

            CREATE UNIQUE INDEX IF NOT EXISTS uq_task_last_execution_asset
                ON public.task_last_executions (
                    program_id,
                    task_type,
                    asset_type,
                    asset_id,
                    params_fingerprint
                )
                WHERE asset_id IS NOT NULL;

            CREATE UNIQUE INDEX IF NOT EXISTS uq_task_last_execution_target
                ON public.task_last_executions (
                    program_id,
                    task_type,
                    target_key,
                    params_fingerprint
                )
                WHERE target_key IS NOT NULL;

            CREATE INDEX IF NOT EXISTS ix_task_last_executions_target
                ON public.task_last_executions (
                    program_id,
                    task_type,
                    params_fingerprint,
                    target_key,
                    last_success_at DESC
                )
                WHERE target_key IS NOT NULL;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS public.ix_task_last_executions_target;
            DROP INDEX IF EXISTS public.uq_task_last_execution_target;
            DROP INDEX IF EXISTS public.uq_task_last_execution_asset;
            DROP INDEX IF EXISTS public.ix_task_last_executions_asset;
            DROP INDEX IF EXISTS public.ix_task_last_executions_eligible;
            DROP TABLE IF EXISTS public.task_last_executions;
            """
        )
    )
