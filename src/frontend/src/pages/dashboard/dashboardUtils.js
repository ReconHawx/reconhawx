/** Dashboard helpers: formatting and date-window helpers. */

export const NF = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

export function formatInt(n) {
  if (n == null || Number.isNaN(n)) return '0';
  return NF.format(n);
}

/** ISO UTC calendar day (API trend buckets) → readable label */
export function formatTrendTooltipDate(iso) {
  if (!iso || typeof iso !== 'string') return '—';
  const day = iso.length >= 10 ? iso.slice(0, 10) : iso;
  const d = new Date(`${day}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/**
 * Deep-link to list pages with program + filter query params (sorted for stable URLs).
 * programName: optional global program filter name.
 */
export function buildDashboardListHref(path, programName, query = {}) {
  const p = new URLSearchParams();
  if (programName) p.set('program', programName);
  Object.keys(query)
    .sort()
    .forEach((k) => {
      const v = query[k];
      if (v !== undefined && v !== null && String(v) !== '') p.set(k, String(v));
    });
  const s = p.toString();
  return s ? `${path}?${s}` : path;
}

export function getAgeFromDate(createdAt) {
  if (!createdAt) return '—';
  const now = new Date();
  const created = new Date(createdAt);
  const diffMs = now - created;
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffWeeks = Math.floor(diffDays / 7);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  if (diffSeconds < 60) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffWeeks < 4) return `${diffWeeks}w ago`;
  if (diffMonths < 12) return `${diffMonths}mo ago`;
  return `${diffYears}y ago`;
}

export function truncateText(text, maxLength = 50) {
  if (!text) return '—';
  const s = String(text);
  return s.length > maxLength ? `${s.substring(0, maxLength)}…` : s;
}

const PRESET_DAYS = { '7d': 7, '30d': 30, '90d': 90 };

/** Calendar days for trend + latest window (preset or custom span). */
export function dashboardTrendDays(prefs) {
  if (prefs.datePreset === 'custom' && prefs.customFrom && prefs.customTo) {
    const a = new Date(`${prefs.customFrom}T00:00:00Z`);
    const b = new Date(`${prefs.customTo}T00:00:00Z`);
    const span = Math.ceil((b.getTime() - a.getTime()) / 86400000) + 1;
    return Math.min(366, Math.max(1, span));
  }
  return PRESET_DAYS[prefs.datePreset] || 30;
}

/** Query params for `/assets/common/trends` and `/findings/common/trends`. */
export function buildTrendApiParams(programName, prefs) {
  const days = dashboardTrendDays(prefs);
  const base = {
    days,
    programName: programName || undefined,
  };
  if (prefs.datePreset === 'custom' && prefs.customFrom && prefs.customTo) {
    return {
      ...base,
      startDate: prefs.customFrom,
      endDate: prefs.customTo,
    };
  }
  return base;
}

/** `days_ago` for `/common/latest` — approximate window from preset or custom start. */
export function latestDaysAgo(prefs) {
  if (prefs.datePreset === 'custom' && prefs.customFrom) {
    const from = new Date(`${prefs.customFrom}T00:00:00Z`);
    if (!Number.isNaN(from.getTime())) {
      return Math.min(366, Math.max(1, Math.ceil((Date.now() - from.getTime()) / 86400000)));
    }
  }
  return dashboardTrendDays(prefs);
}

export function itemInCustomRange(createdAt, prefs) {
  if (prefs.datePreset !== 'custom' || !prefs.customFrom || !prefs.customTo || !createdAt) {
    return true;
  }
  const t = new Date(createdAt).getTime();
  const from = new Date(`${prefs.customFrom}T00:00:00Z`).getTime();
  const to = new Date(`${prefs.customTo}T23:59:59Z`).getTime();
  return t >= from && t <= to;
}

export function averageRiskScore(typosquatRows) {
  if (!typosquatRows?.length) return null;
  const nums = typosquatRows
    .map((r) => (typeof r.risk_score === 'number' ? r.risk_score : parseFloat(String(r.risk_score))))
    .filter((n) => !Number.isNaN(n));
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}
