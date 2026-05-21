"""Add optional asset FKs on unified findings (subdomain, url, service).

Revision ID: v017_finding_asset_fks
Revises: v016_task_target_events

Nuclei findings may link to subdomain (domain), url, ip, and service.
WPScan findings link to url only. All FKs nullable; ON DELETE SET NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v017_finding_asset_fks"
down_revision: Union[str, Sequence[str], None] = "v016_task_target_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE findings
                ADD COLUMN IF NOT EXISTS subdomain_id UUID
                    REFERENCES subdomains(id) ON DELETE SET NULL;
            ALTER TABLE findings
                ADD COLUMN IF NOT EXISTS url_id UUID
                    REFERENCES urls(id) ON DELETE SET NULL;
            ALTER TABLE findings
                ADD COLUMN IF NOT EXISTS service_id UUID
                    REFERENCES services(id) ON DELETE SET NULL;
            CREATE INDEX IF NOT EXISTS ix_findings_subdomain_id
                ON findings (subdomain_id);
            CREATE INDEX IF NOT EXISTS ix_findings_url_id
                ON findings (url_id);
            CREATE INDEX IF NOT EXISTS ix_findings_service_id
                ON findings (service_id);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_findings_service_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_findings_url_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_findings_subdomain_id;"))
    op.execute(sa.text("ALTER TABLE findings DROP COLUMN IF EXISTS service_id;"))
    op.execute(sa.text("ALTER TABLE findings DROP COLUMN IF EXISTS url_id;"))
    op.execute(sa.text("ALTER TABLE findings DROP COLUMN IF EXISTS subdomain_id;"))
