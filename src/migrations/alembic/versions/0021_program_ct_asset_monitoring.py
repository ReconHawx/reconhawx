"""programs.ct_asset_monitoring_enabled (CT scope-based asset discovery).

Revision ID: v020_ct_asset_monitoring
Revises: v019_task_last_executions
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v020_ct_asset_monitoring"
down_revision: Union[str, Sequence[str], None] = "v019_task_last_executions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE programs
                ADD COLUMN IF NOT EXISTS ct_asset_monitoring_enabled BOOLEAN NOT NULL DEFAULT FALSE;
            """
        )
    )
    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN programs.ct_asset_monitoring_enabled IS
                'CT log monitoring for in-scope subdomain (asset) discovery; matched SANs are ingested via POST /assets.';
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE programs DROP COLUMN IF EXISTS ct_asset_monitoring_enabled;"
        )
    )
