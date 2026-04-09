"""Baseline: full schema created by kubernetes/base/postgresql/schema.sql on first boot.

Empty upgrade: the bundled pg_dump defines the database. Later revisions apply deltas
for older installs or non-bundled DBs; fresh installs use `alembic stamp head`.

Revision ID: base_baseline
Revises:
Create Date: 2026-04-09

"""

from typing import Sequence, Union

from alembic import op

revision: str = "base_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
