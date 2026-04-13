"""programs.scope_domains / out_of_scope_domains JSONB (structured scope).

Revision ID: v005_program_scope_domains_jsonb
Revises: 16db56a3ba47
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v005_program_scope_domains_jsonb"
down_revision: Union[str, Sequence[str], None] = "16db56a3ba47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE programs
                ADD COLUMN IF NOT EXISTS scope_domains jsonb DEFAULT '[]'::jsonb NOT NULL;
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE programs
                ADD COLUMN IF NOT EXISTS out_of_scope_domains jsonb DEFAULT '[]'::jsonb NOT NULL;
            """
        )
    )
    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN programs.scope_domains IS
                'Structured in-scope domain patterns: [{"pattern": "example.com|*.example.com", "wildcard": true}]. Legacy domain_regex still applies when non-empty.';
            """
        )
    )
    op.execute(
        sa.text(
            """
            COMMENT ON COLUMN programs.out_of_scope_domains IS
                'Structured out-of-scope patterns (same shape as scope_domains). Legacy out_of_scope_regex still applies when non-empty.';
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE programs DROP COLUMN IF EXISTS out_of_scope_domains;"))
    op.execute(sa.text("ALTER TABLE programs DROP COLUMN IF EXISTS scope_domains;"))
