-- Migration: Denormalized last closure timestamp on typosquat_domains
-- Version: 0.0.3

-- UP MIGRATION
ALTER TABLE typosquat_domains
    ADD COLUMN IF NOT EXISTS last_closure_at timestamp without time zone;

COMMENT ON COLUMN typosquat_domains.last_closure_at IS 'UTC time of the most recent resolved/dismissed closure (matches last closure_events[].closed_at)';

CREATE INDEX IF NOT EXISTS ix_typosquat_domains_last_closure_at
    ON typosquat_domains (last_closure_at);

-- Backfill from last closure_events element (if any)
UPDATE typosquat_domains
SET last_closure_at = (
    ((closure_events #>> '{-1,closed_at}'))::timestamptz AT TIME ZONE 'UTC'
)
WHERE jsonb_array_length(closure_events) > 0
  AND (closure_events->-1) ? 'closed_at'
  AND (closure_events #>> '{-1,closed_at}') IS NOT NULL
  AND trim(closure_events #>> '{-1,closed_at}') <> ''
  AND last_closure_at IS NULL;

-- DOWN MIGRATION
-- DROP INDEX IF EXISTS ix_typosquat_domains_last_closure_at;
-- ALTER TABLE typosquat_domains DROP COLUMN IF EXISTS last_closure_at;
