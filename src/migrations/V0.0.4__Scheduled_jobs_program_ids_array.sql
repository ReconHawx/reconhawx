-- Migration: scheduled_jobs.program_id -> program_ids uuid[]
-- Version: 0.0.4
-- Created: 2026-04-07

-- UP MIGRATION
ALTER TABLE scheduled_jobs ADD COLUMN program_ids uuid[];

UPDATE scheduled_jobs SET program_ids = ARRAY[program_id]::uuid[] WHERE program_id IS NOT NULL;

DELETE FROM scheduled_jobs WHERE program_ids IS NULL OR cardinality(program_ids) < 1;

ALTER TABLE scheduled_jobs ALTER COLUMN program_ids SET NOT NULL;

ALTER TABLE scheduled_jobs ADD CONSTRAINT scheduled_jobs_program_ids_nonempty CHECK (cardinality(program_ids) >= 1);

ALTER TABLE scheduled_jobs DROP CONSTRAINT IF EXISTS scheduled_jobs_program_id_fkey;

DROP INDEX IF EXISTS ix_scheduled_jobs_program_id;

DROP INDEX IF EXISTS ix_scheduled_jobs_program_id_fkey;

ALTER TABLE scheduled_jobs DROP COLUMN program_id;

CREATE INDEX ix_scheduled_jobs_program_ids ON scheduled_jobs USING gin (program_ids);

-- DOWN MIGRATION
-- ALTER TABLE scheduled_jobs DROP CONSTRAINT IF EXISTS scheduled_jobs_program_ids_nonempty;
-- DROP INDEX IF EXISTS ix_scheduled_jobs_program_ids;
-- ALTER TABLE scheduled_jobs ADD COLUMN program_id uuid;
-- UPDATE scheduled_jobs SET program_id = program_ids[1];
-- ALTER TABLE scheduled_jobs ALTER COLUMN program_id SET NOT NULL;
-- ALTER TABLE scheduled_jobs ADD CONSTRAINT scheduled_jobs_program_id_fkey FOREIGN KEY (program_id) REFERENCES programs(id);
-- CREATE INDEX ix_scheduled_jobs_program_id ON scheduled_jobs USING btree (program_id);
-- ALTER TABLE scheduled_jobs DROP COLUMN program_ids;
