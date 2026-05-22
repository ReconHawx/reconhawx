const SEVERITY_COLORS = {
  critical: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'info',
  info: 'secondary',
  unknown: 'secondary',
};

export function getSeverityBadgeVariant(severity) {
  if (!severity) return 'secondary';
  return SEVERITY_COLORS[String(severity).toLowerCase()] || 'secondary';
}
