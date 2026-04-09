"""scheduled_jobs.program_id -> program_ids uuid[] (V0.0.4).

Revision ID: v004_scheduled_jobs_program_ids
Revises: v003_typosquat_last_closure_at
Create Date: 2026-04-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v004_scheduled_jobs_program_ids"
down_revision: Union[str, Sequence[str], None] = "v003_typosquat_last_closure_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE scheduled_jobs ADD COLUMN IF NOT EXISTS program_ids uuid[];"
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'scheduled_jobs'
                      AND column_name = 'program_id'
                ) THEN
                    EXECUTE $u$
                        UPDATE scheduled_jobs
                        SET program_ids = ARRAY[program_id]::uuid[]
                        WHERE program_id IS NOT NULL
                          AND (program_ids IS NULL OR cardinality(program_ids) < 1)
                    $u$;
                END IF;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM scheduled_jobs WHERE program_ids IS NULL OR cardinality(program_ids) < 1;"
        )
    )
    op.execute(
        sa.text("ALTER TABLE scheduled_jobs ALTER COLUMN program_ids SET NOT NULL;")
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                ALTER TABLE scheduled_jobs
                    ADD CONSTRAINT scheduled_jobs_program_ids_nonempty CHECK (cardinality(program_ids) >= 1);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE scheduled_jobs DROP CONSTRAINT IF EXISTS scheduled_jobs_program_id_fkey;"
        )
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_scheduled_jobs_program_id;"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_scheduled_jobs_program_id_fkey;"))
    op.execute(sa.text("ALTER TABLE scheduled_jobs DROP COLUMN IF EXISTS program_id;"))
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_scheduled_jobs_program_ids
                ON scheduled_jobs USING gin (program_ids);
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE scheduled_jobs DROP CONSTRAINT IF EXISTS scheduled_jobs_program_ids_nonempty;"
        )
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_scheduled_jobs_program_ids;"))
    op.execute(sa.text("ALTER TABLE scheduled_jobs ADD COLUMN program_id uuid;"))
    op.execute(
        sa.text(
            "UPDATE scheduled_jobs SET program_id = program_ids[1] WHERE cardinality(program_ids) >= 1;"
        )
    )
    op.execute(sa.text("ALTER TABLE scheduled_jobs ALTER COLUMN program_id SET NOT NULL;"))
    op.execute(
        sa.text(
            """
            ALTER TABLE scheduled_jobs
                ADD CONSTRAINT scheduled_jobs_program_id_fkey
                FOREIGN KEY (program_id) REFERENCES programs(id);
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_scheduled_jobs_program_id ON scheduled_jobs USING btree (program_id);"
        )
    )
    op.execute(sa.text("ALTER TABLE scheduled_jobs DROP COLUMN IF EXISTS program_ids;"))
