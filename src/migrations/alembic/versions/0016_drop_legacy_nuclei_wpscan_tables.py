"""Drop legacy nuclei_findings and wpscan_findings tables.

Revision ID: v015_drop_nuclei_wpscan
Revises: v014_unified_findings

Rows were migrated to ``findings`` in v014. Recreate ``security_summary`` to
aggregate Nuclei severities from ``findings`` (source = nuclei) instead of the
old table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v015_drop_nuclei_wpscan"
down_revision: Union[str, Sequence[str], None] = "v014_unified_findings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("DROP VIEW IF EXISTS public.security_summary;"))
    op.execute(sa.text("DROP TABLE IF EXISTS public.nuclei_findings CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS public.wpscan_findings CASCADE;"))
    op.execute(
        sa.text(
            """
            CREATE VIEW public.security_summary AS
             SELECT p.name AS program_name,
                p.id AS program_id,
                count(DISTINCT f.id) AS nuclei_findings_count,
                count(DISTINCT
                    CASE
                        WHEN ((f.severity)::text = 'critical'::text) THEN f.id
                        ELSE NULL::uuid
                    END) AS critical_findings,
                count(DISTINCT
                    CASE
                        WHEN ((f.severity)::text = 'high'::text) THEN f.id
                        ELSE NULL::uuid
                    END) AS high_findings,
                count(DISTINCT
                    CASE
                        WHEN ((f.severity)::text = 'medium'::text) THEN f.id
                        ELSE NULL::uuid
                    END) AS medium_findings,
                count(DISTINCT
                    CASE
                        WHEN ((f.severity)::text = 'low'::text) THEN f.id
                        ELSE NULL::uuid
                    END) AS low_findings,
                count(DISTINCT td.id) AS typosquat_domains_count,
                count(DISTINCT
                    CASE
                        WHEN (td.fixed_at IS NULL) THEN td.id
                        ELSE NULL::uuid
                    END) AS active_typosquats
               FROM ((public.programs p
                 LEFT JOIN public.findings f ON (((p.id = f.program_id)
                   AND ((f.source)::text = 'nuclei'::text))))
                 LEFT JOIN public.typosquat_domains td ON ((p.id = td.program_id)))
              GROUP BY p.id, p.name
              ORDER BY p.name;
            """
        )
    )


def downgrade() -> None:
    pass
