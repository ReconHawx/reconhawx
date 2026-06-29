"""Add discovery source column to core asset tables.

Revision ID: v023_asset_discovery_source
Revises: v021_ct_monitor_logs
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v023_asset_discovery_source"
down_revision: Union[str, Sequence[str], None] = "v021_ct_monitor_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ASSET_TABLES = (
    "apex_domains",
    "subdomains",
    "ips",
    "urls",
    "services",
    "certificates",
)


def upgrade() -> None:
    for table in _ASSET_TABLES:
        op.execute(
            sa.text(
                f"ALTER TABLE public.{table} "
                f"ADD COLUMN IF NOT EXISTS source VARCHAR(255);"
            )
        )
        op.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_prog_source "
                f"ON public.{table} (program_id, source);"
            )
        )


def downgrade() -> None:
    for table in _ASSET_TABLES:
        op.execute(
            sa.text(f"DROP INDEX IF EXISTS public.ix_{table}_prog_source;")
        )
        op.execute(
            sa.text(f"ALTER TABLE public.{table} DROP COLUMN IF EXISTS source;")
        )
