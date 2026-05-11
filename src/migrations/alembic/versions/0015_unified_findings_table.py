"""Unified scanner findings table (Nuclei, WPScan, Broken Links).

Revision ID: v014_unified_findings
Revises: v013_dash_prog_created

Fingerprints must match ``utils.finding_fingerprint`` (SHA-256 hex of pipe-joined parts, UTF-8).

Scanner-specific fields (tags, references, CVE ids, broken-link status, etc.) live only in ``details`` JSONB.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v014_unified_findings"
down_revision: Union[str, Sequence[str], None] = "v013_dash_prog_created"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS findings (
                id UUID PRIMARY KEY,
                program_id UUID NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
                source VARCHAR(64) NOT NULL,
                fingerprint VARCHAR(64) NOT NULL,
                title VARCHAR(2000),
                description TEXT,
                severity VARCHAR(50),
                url TEXT,
                hostname VARCHAR(255),
                port INTEGER,
                scheme VARCHAR(10),
                ip_id UUID REFERENCES ips(id) ON DELETE SET NULL,
                observed_at TIMESTAMP WITHOUT TIME ZONE,
                notes TEXT,
                details JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                CONSTRAINT uq_findings_prog_source_fingerprint
                    UNIQUE (program_id, source, fingerprint)
            );
            """
        )
    )
    # Partial / older ``findings`` table: drop columns no longer in the canonical model.
    op.execute(
        sa.text(
            """
            ALTER TABLE findings DROP COLUMN IF EXISTS status;
            ALTER TABLE findings DROP COLUMN IF EXISTS tags;
            ALTER TABLE findings DROP COLUMN IF EXISTS external_ids;
            ALTER TABLE findings DROP COLUMN IF EXISTS "references";
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_findings_prog_source_created
                ON findings (program_id, source, created_at);
            CREATE INDEX IF NOT EXISTS ix_findings_prog_source_updated
                ON findings (program_id, source, updated_at);
            CREATE INDEX IF NOT EXISTS ix_findings_prog_source_severity
                ON findings (program_id, source, severity);
            CREATE INDEX IF NOT EXISTS ix_findings_prog_source_hostname
                ON findings (program_id, source, hostname);
            CREATE INDEX IF NOT EXISTS ix_findings_prog_source_observed_at
                ON findings (program_id, source, observed_at);
            CREATE INDEX IF NOT EXISTS ix_findings_details_gin ON findings USING GIN (details);
            """
        )
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_findings_prog_source_status;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_findings_tags_gin;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_findings_external_ids_gin;"))

    # Backfill: preserve legacy row UUIDs as findings.id for stable API URLs
    op.execute(
        sa.text(
            """
            INSERT INTO findings (
                id, program_id, source, fingerprint, title, description, severity,
                url, hostname, port, scheme, ip_id,
                observed_at, notes, details, created_at, updated_at
            )
            SELECT
                n.id,
                n.program_id,
                'nuclei',
                encode(
                    digest(
                        convert_to(
                            coalesce(n.url, '') || '|'
                            || coalesce(n.template_id, '') || '|'
                            || coalesce(n.matcher_name, '') || '|'
                            || n.program_id::text || '|'
                            || coalesce(n.matched_at, ''),
                            'UTF8'
                        ),
                        'sha256'
                    ),
                    'hex'
                ),
                n.name,
                n.description,
                n.severity,
                n.url,
                n.hostname,
                n.port,
                n.scheme,
                n.ip_id,
                n.created_at,
                n.notes,
                jsonb_build_object(
                    'template_id', n.template_id,
                    'template_url', n.template_url,
                    'template_path', n.template_path,
                    'type', n.finding_type,
                    'matched_at', n.matched_at,
                    'matcher_name', n.matcher_name,
                    'matched_line', n.matched_line,
                    'extracted_results', coalesce(to_jsonb(n.extracted_results), '[]'::jsonb),
                    'info', coalesce(n.info_data, '{}'::jsonb),
                    'protocol', n.protocol,
                    'tags', coalesce(to_jsonb(n.tags), '[]'::jsonb)
                ),
                n.created_at,
                n.updated_at
            FROM nuclei_findings n
            WHERE NOT EXISTS (SELECT 1 FROM findings f WHERE f.id = n.id);
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO findings (
                id, program_id, source, fingerprint, title, description, severity,
                url, hostname, port, scheme, ip_id,
                observed_at, notes, details, created_at, updated_at
            )
            SELECT
                w.id,
                w.program_id,
                'wpscan',
                encode(
                    digest(
                        convert_to(
                            coalesce(w.url, '') || '|'
                            || coalesce(w.item_name, '') || '|'
                            || w.program_id::text,
                            'UTF8'
                        ),
                        'sha256'
                    ),
                    'hex'
                ),
                coalesce(w.title, w.item_name),
                w.description,
                w.severity,
                w.url,
                w.hostname,
                w.port,
                w.scheme,
                NULL::uuid,
                w.created_at,
                w.notes,
                jsonb_build_object(
                    'item_name', w.item_name,
                    'item_type', w.item_type,
                    'vulnerability_type', w.vulnerability_type,
                    'fixed_in', w.fixed_in,
                    'enumeration_data', coalesce(w.enumeration_data, '{}'::jsonb),
                    'status', w.status,
                    'references', coalesce(to_jsonb(w."references"), '[]'::jsonb),
                    'cve_ids', coalesce(to_jsonb(w.cve_ids), '[]'::jsonb)
                ),
                w.created_at,
                w.updated_at
            FROM wpscan_findings w
            WHERE NOT EXISTS (SELECT 1 FROM findings f WHERE f.id = w.id);
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO findings (
                id, program_id, source, fingerprint, title, description, severity,
                url, hostname, port, scheme, ip_id,
                observed_at, notes, details, created_at, updated_at
            )
            SELECT
                b.id,
                b.program_id,
                'broken_link',
                encode(
                    digest(
                        convert_to(
                            b.program_id::text || '|' || coalesce(b.url, ''),
                            'UTF8'
                        ),
                        'sha256'
                    ),
                    'hex'
                ),
                coalesce(nullif(trim(b.url), ''), b.domain),
                b.reason,
                NULL::varchar,
                b.url,
                NULL::varchar,
                NULL::int,
                NULL::varchar,
                NULL::uuid,
                b.checked_at,
                b.notes,
                jsonb_build_object(
                    'link_type', b.link_type,
                    'media_type', b.media_type,
                    'domain', b.domain,
                    'reason', b.reason,
                    'error_code', b.error_code,
                    'response_data', coalesce(b.response_data, '{}'::jsonb),
                    'checked_at', b.checked_at,
                    'status', b.status
                ),
                b.created_at,
                b.updated_at
            FROM broken_links b
            WHERE NOT EXISTS (SELECT 1 FROM findings f WHERE f.id = b.id);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS findings CASCADE;"))
