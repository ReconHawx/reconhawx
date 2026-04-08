/**
 * Shared theme tokens for React Flow / workflow nodes (inline styles).
 * Prefer these over hex + isDark branches so light/dark track index.css variables.
 */

/** Box shadow when a node is not selected */
export const workflowNodeShadowIdle = '0 2px 12px var(--rh-shadow-color)';

/** Box shadow when a node is selected */
export const workflowNodeShadowSelected =
  '0 4px 20px rgba(var(--bs-primary-rgb), 0.22)';

/** Subtle gradients that work in both themes (step bands on the canvas) */
export const WORKFLOW_STEP_BACKGROUND_PATTERNS = [
  'linear-gradient(145deg, var(--bs-tertiary-bg) 0%, var(--bs-card-bg) 100%)',
  'linear-gradient(145deg, rgba(var(--bs-primary-rgb), 0.08) 0%, var(--bs-card-bg) 100%)',
  'linear-gradient(145deg, rgba(var(--bs-success-rgb), 0.08) 0%, var(--bs-card-bg) 100%)',
  'linear-gradient(145deg, rgba(var(--bs-secondary-rgb), 0.08) 0%, var(--bs-card-bg) 100%)',
  'linear-gradient(145deg, var(--bs-secondary-bg) 0%, var(--bs-tertiary-bg) 100%)',
  'linear-gradient(145deg, rgba(var(--bs-info-rgb), 0.1) 0%, var(--bs-card-bg) 100%)',
  'linear-gradient(145deg, rgba(var(--bs-danger-rgb), 0.07) 0%, var(--bs-card-bg) 100%)',
  'linear-gradient(145deg, rgba(var(--bs-warning-rgb), 0.1) 0%, var(--bs-card-bg) 100%)',
  'linear-gradient(145deg, var(--bs-card-bg) 0%, var(--bs-pre-bg) 100%)',
];
