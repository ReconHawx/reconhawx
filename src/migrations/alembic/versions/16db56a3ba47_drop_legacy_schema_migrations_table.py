"""drop legacy schema_migrations table

Revision ID: 16db56a3ba47
Revises: v004_scheduled_jobs_program_ids
Create Date: 2026-04-09 11:41:21.007341

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16db56a3ba47'
down_revision: Union[str, Sequence[str], None] = 'v004_scheduled_jobs_program_ids'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS schema_migrations CASCADE"))


def downgrade() -> None:
    pass
