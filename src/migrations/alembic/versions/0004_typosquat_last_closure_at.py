"""Denormalized last_closure_at on typosquat_domains (V0.0.3).

Revision ID: v003_typosquat_last_closure_at
Revises: v002_typosquat_closure_events
Create Date: 2026-04-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v003_typosquat_last_closure_at"
down_revision: Union[str, Sequence[str], None] = "v002_typosquat_closure_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE typosquat_domains
                ADD COLUMN IF NOT EXISTS last_closure_at timestamp without time zone;
            """
        )
    )
    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN typosquat_domains.last_closure_at IS
                'UTC time of the most recent resolved/dismissed closure (matches last closure_events[].closed_at)';
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_typosquat_domains_last_closure_at
                ON typosquat_domains (last_closure_at);
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE typosquat_domains
            SET last_closure_at = (
                ((closure_events #>> '{-1,closed_at}'))::timestamptz AT TIME ZONE 'UTC'
            )
            WHERE jsonb_array_length(closure_events) > 0
              AND (closure_events->-1) ? 'closed_at'
              AND (closure_events #>> '{-1,closed_at}') IS NOT NULL
              AND trim(closure_events #>> '{-1,closed_at}') <> ''
              AND last_closure_at IS NULL;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_typosquat_domains_last_closure_at;"))
    op.execute(sa.text("ALTER TABLE typosquat_domains DROP COLUMN IF EXISTS last_closure_at;"))
