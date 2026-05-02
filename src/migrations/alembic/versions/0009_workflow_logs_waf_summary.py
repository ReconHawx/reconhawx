"""workflow_logs: waf_summary JSONB for aggregated WAF precheck state.

Revision ID: v008_workflow_logs_waf
Revises: v007_screenshots_prog_id
Create Date: 2026-05-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v008_workflow_logs_waf"
down_revision: Union[str, Sequence[str], None] = "v007_screenshots_prog_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE workflow_logs
                ADD COLUMN IF NOT EXISTS waf_summary JSONB;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE workflow_logs DROP COLUMN IF EXISTS waf_summary;"))
