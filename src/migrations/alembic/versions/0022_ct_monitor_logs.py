"""Durable CT monitor logs.

Revision ID: v021_ct_monitor_logs
Revises: v020_ct_asset_monitoring
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v021_ct_monitor_logs"
down_revision: Union[str, Sequence[str], None] = "v020_ct_asset_monitoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS public.ct_monitor_logs (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                program_id uuid NOT NULL REFERENCES public.programs(id) ON DELETE CASCADE,
                program_name varchar(255),
                event_type varchar(64) NOT NULL,
                outcome varchar(64) NOT NULL,
                occurred_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
                domain text,
                protected_domain text,
                match_type varchar(128),
                similarity_score double precision,
                priority varchar(32),
                cert_fingerprint varchar(255),
                cert_issuer text,
                cert_source varchar(255),
                details jsonb NOT NULL DEFAULT '{}'::jsonb,
                created_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_ct_monitor_logs_program_occurred
            ON public.ct_monitor_logs (program_id, occurred_at DESC);
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_ct_monitor_logs_program_name
            ON public.ct_monitor_logs (program_name);
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_ct_monitor_logs_event_outcome
            ON public.ct_monitor_logs (event_type, outcome);
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_ct_monitor_logs_domain
            ON public.ct_monitor_logs (domain);
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_ct_monitor_logs_cert_fingerprint
            ON public.ct_monitor_logs (cert_fingerprint);
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_ct_monitor_logs_match_type
            ON public.ct_monitor_logs (match_type);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS public.ct_monitor_logs CASCADE;"))
