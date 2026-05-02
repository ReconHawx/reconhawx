"""workflow_logs: user_id FK to users (workflow initiator for auto-rerun).

Revision ID: v009_wflogs_user_id
Revises: v008_workflow_logs_waf
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v009_wflogs_user_id"
down_revision: Union[str, Sequence[str], None] = "v008_workflow_logs_waf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE workflow_logs
                ADD COLUMN IF NOT EXISTS user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL;

            CREATE INDEX IF NOT EXISTS idx_workflow_logs_user_id
                ON workflow_logs (user_id);
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS idx_workflow_logs_user_id;

            ALTER TABLE workflow_logs DROP COLUMN IF EXISTS user_id;
            """
        )
    )
