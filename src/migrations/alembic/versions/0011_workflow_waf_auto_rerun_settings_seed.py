"""Seed workflow_waf_auto_rerun system_settings row (defaults: on, max 3 reruns).

Revision ID: v010_waf_auto_rerun_settings
Revises: v009_wflogs_user_id
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v010_waf_auto_rerun_settings"
down_revision: Union[str, Sequence[str], None] = "v009_wflogs_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (
                'workflow_waf_auto_rerun',
                '{"enabled": true, "max_attempts": 3}'::jsonb,
                CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
            )
            ON CONFLICT (key) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM system_settings WHERE key = 'workflow_waf_auto_rerun'"))
