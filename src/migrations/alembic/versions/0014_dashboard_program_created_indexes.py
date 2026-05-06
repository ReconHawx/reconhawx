"""Composite indexes (program_id, created_at DESC) for dashboard queries.

Revision ID: v013_dash_prog_created
Revises: v012_lowercase_hostnames

Uses CREATE INDEX CONCURRENTLY outside a transaction via autocommit_block.
DOWN uses DROP INDEX IF EXISTS (non-concurrent, transactional).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v013_dash_prog_created"
down_revision: Union[str, Sequence[str], None] = "v012_lowercase_hostnames"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Names must match Index(...) in models.postgres.py
_UPGRADE_STMTS = [
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_apex_domains_prog_created ON apex_domains (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_subdomains_prog_created ON subdomains (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ips_prog_created ON ips (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_urls_prog_created ON urls (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_services_prog_created ON services (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_certificates_prog_created ON certificates (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_nuclei_findings_prog_created ON nuclei_findings (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_typosquat_domains_prog_created ON typosquat_domains (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_broken_links_prog_created ON broken_links (program_id, created_at DESC)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_workflow_logs_prog_created ON workflow_logs (program_id, created_at DESC)",
]


def upgrade() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        for stmt in _UPGRADE_STMTS:
            op.execute(sa.text(stmt))


def downgrade() -> None:
    names = [
        "ix_workflow_logs_prog_created",
        "ix_broken_links_prog_created",
        "ix_typosquat_domains_prog_created",
        "ix_nuclei_findings_prog_created",
        "ix_certificates_prog_created",
        "ix_services_prog_created",
        "ix_urls_prog_created",
        "ix_ips_prog_created",
        "ix_subdomains_prog_created",
        "ix_apex_domains_prog_created",
    ]
    for name in names:
        op.execute(sa.text(f'DROP INDEX IF EXISTS "{name}"'))
