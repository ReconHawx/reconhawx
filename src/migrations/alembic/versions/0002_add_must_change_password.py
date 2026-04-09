"""Add must_change_password to users (V0.0.1).

Revision ID: v001_must_change_password
Revises: base_baseline
Create Date: 2026-04-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v001_must_change_password"
down_revision: Union[str, Sequence[str], None] = "base_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE users
                ADD COLUMN IF NOT EXISTS must_change_password boolean NOT NULL DEFAULT false;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS must_change_password;"))
