"""Typosquat closure_events JSONB column (V0.0.2).

Revision ID: v002_typosquat_closure_events
Revises: v001_must_change_password
Create Date: 2026-04-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v002_typosquat_closure_events"
down_revision: Union[str, Sequence[str], None] = "v001_must_change_password"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE typosquat_domains
                ADD COLUMN IF NOT EXISTS closure_events jsonb NOT NULL DEFAULT '[]'::jsonb;
            """
        )
    )
    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN typosquat_domains.closure_events IS
                'Ordered array of closure events: to_status, closed_at, closed_by_user_id, optional source_action_log_id';
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE typosquat_domains td
            SET closure_events = s.arr
            FROM (
                SELECT
                    x.entity_id,
                    jsonb_agg(x.elem ORDER BY x.sort_ts) AS arr
                FROM (
                    SELECT
                        al.entity_id,
                        al.created_at AS sort_ts,
                        jsonb_build_object(
                            'to_status', al.new_value->>'status',
                            'closed_at', to_char((al.created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD"T"HH24:MI:SS.MS') || 'Z',
                            'closed_by_user_id',
                            CASE
                                WHEN (al.metadata->>'assigned_to') ~ '^[0-9a-fA-F-]{36}$'
                                THEN al.metadata->>'assigned_to'
                                ELSE al.user_id::text
                            END,
                            'source_action_log_id', al.id::text
                        ) AS elem
                    FROM action_logs al
                    WHERE al.entity_type = 'typosquat_finding'
                      AND al.action_type = 'status_change'
                      AND COALESCE(al.new_value->>'status', '') IN ('resolved', 'dismissed')
                      AND al.old_value->>'status' IS DISTINCT FROM al.new_value->>'status'
                ) x
                GROUP BY x.entity_id
            ) s
            WHERE td.id::text = s.entity_id
              AND jsonb_array_length(td.closure_events) = 0;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE typosquat_domains DROP COLUMN IF EXISTS closure_events;"))
