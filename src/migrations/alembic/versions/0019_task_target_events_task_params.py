"""Add task_params JSONB to task_target_events.

Revision ID: v018_tte_task_params
Revises: v017_finding_asset_fks

Stores effective task parameters at materialization time (from task_execution_logs.params).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v018_tte_task_params"
down_revision: Union[str, Sequence[str], None] = "v017_finding_asset_fks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE public.task_target_events
                ADD COLUMN IF NOT EXISTS task_params jsonb NOT NULL DEFAULT '{}'::jsonb;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE public.task_target_events
                DROP COLUMN IF EXISTS task_params;
            """
        )
    )
