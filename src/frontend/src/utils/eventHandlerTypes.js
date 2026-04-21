/**
 * Event handler configs use `event_type` as a string[] (API + event-handler service).
 * Coerce legacy single-string payloads from older API responses.
 */

export function coerceHandlerEventTypesList(handler) {
  if (!handler || typeof handler !== 'object') {
    return handler;
  }
  const et = handler.event_type;
  if (Array.isArray(et)) {
    return {
      ...handler,
      event_type: et.filter((x) => typeof x === 'string' && x.trim()).map((x) => x.trim()),
    };
  }
  if (typeof et === 'string' && et.trim()) {
    return { ...handler, event_type: [et.trim()] };
  }
  return { ...handler, event_type: [] };
}

export function coerceHandlersList(handlers) {
  return (handlers || []).map((h) => {
    const et = coerceHandlerEventTypesList(h);
    return {
      ...et,
      conditions_by_event_type: coerceConditionsByEventType(
        h?.conditions_by_event_type,
        et.event_type || []
      ),
    };
  });
}

/**
 * Per-event-type condition lists: only keys present in selectedTypes are kept.
 * Values must be arrays of plain objects (condition dicts).
 */
export function coerceConditionsByEventType(value, selectedTypes) {
  const types = new Set(
    (selectedTypes || [])
      .filter((t) => typeof t === 'string' && t.trim())
      .map((t) => t.trim())
  );
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  const out = {};
  for (const [k, v] of Object.entries(value)) {
    if (typeof k !== 'string' || !k.trim()) continue;
    const key = k.trim();
    if (!types.has(key)) continue;
    if (!Array.isArray(v)) continue;
    const conds = v.filter((c) => c && typeof c === 'object' && !Array.isArray(c));
    if (conds.length) out[key] = conds;
  }
  return out;
}

/** Remove per-type entries whose keys are no longer selected. */
export function pruneConditionsByEventType(byType, selectedTypes) {
  return coerceConditionsByEventType(byType || {}, selectedTypes || []);
}

/** Strip empty per-type lists; omit field when map is empty (save payload). */
export function sanitizeHandlerForSave(handler) {
  const h = coerceHandlerEventTypesList(handler || {});
  const pruned = pruneConditionsByEventType(h.conditions_by_event_type, h.event_type || []);
  const out = { ...h, conditions_by_event_type: pruned };
  const cleaned = {};
  for (const [k, v] of Object.entries(out.conditions_by_event_type || {})) {
    if (Array.isArray(v) && v.length > 0) cleaned[k] = v;
  }
  if (Object.keys(cleaned).length > 0) {
    out.conditions_by_event_type = cleaned;
  } else {
    delete out.conditions_by_event_type;
  }
  return out;
}

export function sanitizeHandlersList(handlers) {
  return (handlers || []).map((h) => sanitizeHandlerForSave(h));
}

/** First type for workflow defaults / embedded builder when a handler matches multiple. */
export function primaryEventTypeFromHandler(handler) {
  const h = coerceHandlerEventTypesList(handler || {});
  const arr = h.event_type;
  return Array.isArray(arr) && arr.length ? arr[0] : '';
}

/** Display string for tables (comma-separated). */
export function formatEventTypesCell(handler) {
  const h = coerceHandlerEventTypesList(handler || {});
  const arr = h.event_type;
  if (!Array.isArray(arr) || !arr.length) return '-';
  return arr.join(', ');
}
