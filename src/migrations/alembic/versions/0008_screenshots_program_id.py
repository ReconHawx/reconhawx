"""screenshots / typosquat_screenshots: program_id FK to programs.

Revision ID: v007_screenshots_prog_id
Revises: v006_ehc_event_types_array
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v007_screenshots_prog_id"
down_revision: Union[str, Sequence[str], None] = "v006_ehc_event_types_array"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE screenshots
                ADD COLUMN IF NOT EXISTS program_id uuid REFERENCES programs(id) ON DELETE SET NULL;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_screenshots_program_id ON screenshots (program_id);
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE screenshots s
            SET program_id = p.id
            FROM programs p
            WHERE s.program_id IS NULL
              AND s.program_name IS NOT NULL
              AND s.program_name = p.name;
            """
        )
    )

    op.execute(
        sa.text(
            """
            ALTER TABLE typosquat_screenshots
                ADD COLUMN IF NOT EXISTS program_id uuid REFERENCES programs(id) ON DELETE SET NULL;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_typosquat_screenshots_program_id ON typosquat_screenshots (program_id);
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE typosquat_screenshots ts
            SET program_id = p.id
            FROM programs p
            WHERE ts.program_id IS NULL
              AND ts.program_name IS NOT NULL
              AND ts.program_name = p.name;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_typosquat_screenshots_program_id;"))
    op.execute(sa.text("ALTER TABLE typosquat_screenshots DROP COLUMN IF EXISTS program_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_screenshots_program_id;"))
    op.execute(sa.text("ALTER TABLE screenshots DROP COLUMN IF EXISTS program_id;"))
