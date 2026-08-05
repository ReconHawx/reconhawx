"""job_status: runner_pod_output TEXT for batch job pod logs.

Revision ID: v024_job_runner_pod_output
Revises: v023_asset_discovery_source
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v024_job_runner_pod_output"
down_revision: Union[str, Sequence[str], None] = "v023_asset_discovery_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE job_status
                ADD COLUMN IF NOT EXISTS runner_pod_output TEXT;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE job_status DROP COLUMN IF EXISTS runner_pod_output;")
    )
