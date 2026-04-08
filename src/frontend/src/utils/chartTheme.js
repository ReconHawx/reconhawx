/**
 * SVG / canvas chart tokens aligned with global CSS variables in `src/frontend/src/index.css`.
 * Use these in Recharts, raw SVG, or inline legend swatches so charts track light/dark.
 */
export const chartTheme = {
  gridStroke: 'var(--bs-border-color)',
  axisStroke: 'var(--bs-text-muted)',
  axisLabelFill: 'var(--bs-text-muted)',
  /** Ring around line-chart points (contrast against the series stroke) */
  pointRingStroke: 'var(--bs-card-bg)',
  typosquatSeries: {
    created: 'var(--bs-primary)',
    resolved: 'var(--bs-success)',
    dismissed: 'var(--bs-warning)',
  },
};
