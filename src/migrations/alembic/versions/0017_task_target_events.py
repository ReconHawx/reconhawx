"""Task target events link workflow task runs to program assets.

Revision ID: v016_task_target_events
Revises: v015_drop_nuclei_wpscan

Materialized from ``workflow_logs.task_execution_logs`` at ingest time for
per-asset task history queries.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v016_task_target_events"
down_revision: Union[str, Sequence[str], None] = "v015_drop_nuclei_wpscan"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS public.task_target_events (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                workflow_log_id uuid NOT NULL REFERENCES public.workflow_logs(id) ON DELETE CASCADE,
                program_id uuid NOT NULL,
                step_name text NOT NULL,
                task_name text NOT NULL,
                task_type text,
                asset_type text NOT NULL,
                asset_id uuid NOT NULL,
                started_at timestamp without time zone NOT NULL,
                completed_at timestamp without time zone,
                status text,
                created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT task_target_events_asset_type_check CHECK (
                    asset_type IN (
                        'subdomain',
                        'apex_domain',
                        'ip',
                        'url',
                        'service',
                        'certificate'
                    )
                ),
                CONSTRAINT uq_task_target_event UNIQUE (
                    workflow_log_id,
                    step_name,
                    task_name,
                    asset_type,
                    asset_id
                )
            );
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_task_target_events_asset_started
            ON public.task_target_events (asset_type, asset_id, started_at DESC);
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_task_target_events_workflow_log
            ON public.task_target_events (workflow_log_id);
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_task_target_events_program_started
            ON public.task_target_events (program_id, started_at DESC);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS public.task_target_events CASCADE;"))
