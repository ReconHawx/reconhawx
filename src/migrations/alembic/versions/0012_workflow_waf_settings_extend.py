"""Extend workflow_waf_auto_rerun JSON with delay and quarantine fields.

Revision ID: v011_waf_settings_extend
Revises: v010_waf_auto_rerun_settings
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v011_waf_settings_extend"
down_revision: Union[str, Sequence[str], None] = "v010_waf_auto_rerun_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO system_settings (key, value, updated_at)
            VALUES (
                'workflow_waf_auto_rerun',
                '{"enabled": true, "max_attempts": 3, "delay_seconds": 2100, "quarantine_ttl": 1800, "secondary_promote": 2, "secondary_window": 900}'::jsonb,
                CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
            )
            ON CONFLICT (key) DO UPDATE
            SET value = (
                '{"enabled": true, "max_attempts": 3, "delay_seconds": 2100, "quarantine_ttl": 1800, "secondary_promote": 2, "secondary_window": 900}'::jsonb
                || system_settings.value
            ),
                updated_at = CURRENT_TIMESTAMP AT TIME ZONE 'UTC';
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE system_settings
            SET value = value
                - 'delay_seconds'
                - 'quarantine_ttl'
                - 'secondary_promote'
                - 'secondary_window',
                updated_at = CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
            WHERE key = 'workflow_waf_auto_rerun';
            """
        )
    )
