"""event_handler_configs: event_type -> event_types TEXT[].

Revision ID: v006_ehc_event_types_array (must fit alembic_version.version_num VARCHAR(32))
Revises: v005_program_scope_domains_jsonb
Create Date: 2026-04-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v006_ehc_event_types_array"
down_revision: Union[str, Sequence[str], None] = "v005_program_scope_domains_jsonb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE event_handler_configs
                ADD COLUMN IF NOT EXISTS event_types text[] NOT NULL DEFAULT '{}'::text[];
            """
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'event_handler_configs'
                  AND column_name = 'event_type'
              ) THEN
                UPDATE event_handler_configs
                SET event_types = ARRAY[event_type::text]
                WHERE event_type IS NOT NULL
                  AND COALESCE(array_length(event_types, 1), 0) = 0;
                DROP INDEX IF EXISTS idx_ehc_event_type;
                ALTER TABLE event_handler_configs DROP COLUMN event_type;
              END IF;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_ehc_event_types_gin
            ON event_handler_configs USING gin (event_types);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_ehc_event_types_gin;"))
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'event_handler_configs'
                  AND column_name = 'event_types'
              )
                 AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'event_handler_configs'
                  AND column_name = 'event_type'
              ) THEN
                ALTER TABLE event_handler_configs
                  ADD COLUMN event_type character varying(100);
                UPDATE event_handler_configs
                SET event_type = event_types[1]::character varying(100)
                WHERE event_types IS NOT NULL AND COALESCE(array_length(event_types, 1), 0) > 0;
                UPDATE event_handler_configs
                SET event_type = ''::character varying(100)
                WHERE event_type IS NULL;
                ALTER TABLE event_handler_configs
                  ALTER COLUMN event_type SET NOT NULL;
                ALTER TABLE event_handler_configs DROP COLUMN event_types;
                CREATE INDEX IF NOT EXISTS idx_ehc_event_type
                  ON event_handler_configs USING btree (event_type);
              END IF;
            END $$;
            """
        )
    )
