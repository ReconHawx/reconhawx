-- Migration: Append-only closure history (resolved/dismissed) on typosquat_domains
-- Version: 0.0.2

-- UP MIGRATION
ALTER TABLE typosquat_domains
    ADD COLUMN IF NOT EXISTS closure_events jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN typosquat_domains.closure_events IS 'Ordered array of closure events: to_status, closed_at, closed_by_user_id, optional source_action_log_id';

-- Backfill from action_logs (idempotent: only rows still empty)
UPDATE typosquat_domains td
SET closure_events = s.arr
FROM (
    SELECT
        x.entity_id,
        jsonb_agg(x.elem ORDER BY x.sort_ts) AS arr
    FROM (
        SELECT
            al.entity_id,
            al.created_at AS sort_ts,
            jsonb_build_object(
                'to_status', al.new_value->>'status',
                'closed_at', to_char((al.created_at AT TIME ZONE 'UTC'), 'YYYY-MM-DD"T"HH24:MI:SS.MS') || 'Z',
                'closed_by_user_id',
                CASE
                    WHEN (al.metadata->>'assigned_to') ~ '^[0-9a-fA-F-]{36}$'
                    THEN al.metadata->>'assigned_to'
                    ELSE al.user_id::text
                END,
                'source_action_log_id', al.id::text
            ) AS elem
        FROM action_logs al
        WHERE al.entity_type = 'typosquat_finding'
          AND al.action_type = 'status_change'
          AND COALESCE(al.new_value->>'status', '') IN ('resolved', 'dismissed')
          AND al.old_value->>'status' IS DISTINCT FROM al.new_value->>'status'
    ) x
    GROUP BY x.entity_id
) s
WHERE td.id::text = s.entity_id
  AND jsonb_array_length(td.closure_events) = 0;

-- DOWN MIGRATION
-- ALTER TABLE typosquat_domains DROP COLUMN IF EXISTS closure_events;
