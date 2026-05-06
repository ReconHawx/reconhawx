import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Card } from 'react-bootstrap';
import { Link } from 'react-router-dom';
import { chartTheme } from '../../../utils/chartTheme';
import { formatInt, formatTrendTooltipDate } from '../dashboardUtils';

function MiniSparkline({ values, stroke, pointLabels, seriesLabel }) {
  const [hover, setHover] = useState(null);

  if (!values || values.length < 2) return <div style={{ height: 32 }} className="text-muted small" />;

  const w = 100;
  const h = 32;
  const pad = 2;
  const n = values.length;
  const xDen = Math.max(n - 1, 1);
  const plotW = w - 2 * pad;
  const plotH = h - 2 * pad;
  const max = Math.max(1, ...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const labels = Array.isArray(pointLabels) && pointLabels.length === n ? pointLabels : null;

  const xAt = (i) => pad + (i / xDen) * plotW;
  const yAt = (v) => pad + (1 - (v - min) / span) * plotH;

  const pts = values.map((v, i) => `${xAt(i)},${yAt(v)}`).join(' ');

  const resolveHoverIdx = (clientX, svgEl) => {
    const bb = svgEl.getBoundingClientRect();
    if (!(bb.width > 0)) return null;
    const xSvg = ((clientX - bb.left) / bb.width) * w;
    const relX = xSvg - pad;
    if (relX < -2 || relX > plotW + 2) return null;
    const clamped = Math.max(0, Math.min(plotW, relX));
    const idx = Math.round((clamped / plotW) * xDen);
    return Math.max(0, Math.min(n - 1, idx));
  };

  const handleSvgMouseMove = (e) => {
    const svgEl = e.currentTarget;
    if (!svgEl || svgEl.nodeName !== 'svg') return;
    const idx = resolveHoverIdx(e.clientX, svgEl);
    if (idx == null) {
      setHover(null);
      return;
    }
    setHover({ idx, clientX: e.clientX, clientY: e.clientY });
  };

  const tooltipPos =
    hover != null && typeof window !== 'undefined'
      ? (() => {
          const padPx = 8;
          const estW = 160;
          const estH = 72;
          let left = hover.clientX + 12;
          let top = hover.clientY + 12;
          if (left + estW > window.innerWidth - padPx) {
            left = Math.max(padPx, hover.clientX - estW - 12);
          }
          if (top + estH > window.innerHeight - padPx) {
            top = Math.max(padPx, hover.clientY - estH - 12);
          }
          return { left, top };
        })()
      : hover != null
        ? { left: hover.clientX + 12, top: hover.clientY + 12 }
        : null;

  const tooltip =
    hover != null && tooltipPos ? (
      <div
        className="rounded border shadow-sm px-2 py-1 bg-body small"
        style={{
          position: 'fixed',
          left: tooltipPos.left,
          top: tooltipPos.top,
          zIndex: 1100,
          pointerEvents: 'none',
          minWidth: 120,
        }}
        aria-hidden="true"
      >
        {seriesLabel && <div className="text-muted text-uppercase fw-semibold mb-1" style={{ fontSize: '0.65rem' }}>{seriesLabel}</div>}
        <div className="fw-semibold text-body">
          {labels?.[hover.idx] != null ? formatTrendTooltipDate(labels[hover.idx]) : `Day ${hover.idx + 1} / ${n}`}
        </div>
        <div className="text-body">{formatInt(values[hover.idx])}</div>
      </div>
    ) : null;

  const hx = hover != null ? xAt(hover.idx) : null;
  const hy = hover != null ? yAt(values[hover.idx]) : null;

  return (
    <div className="position-relative" onMouseLeave={() => setHover(null)}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        width="100%"
        height={h}
        className="d-block opacity-75"
        style={{ width: '100%', cursor: 'crosshair', touchAction: 'none' }}
        onMouseMove={handleSvgMouseMove}
      >
        <polyline
          fill="none"
          stroke={stroke || 'var(--bs-primary)'}
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
          points={pts}
          style={{ pointerEvents: 'none' }}
        />
        <rect
          x={pad}
          y={pad}
          width={plotW}
          height={plotH}
          fill="#fff"
          fillOpacity={0}
          pointerEvents="all"
          style={{ cursor: 'crosshair' }}
        />
        {hx != null && hy != null && (
          <circle cx={hx} cy={hy} r={3.5} fill={chartTheme.pointRingStroke} stroke={stroke || 'var(--bs-primary)'} strokeWidth={1.5} style={{ pointerEvents: 'none' }} />
        )}
      </svg>
      {tooltip && typeof document !== 'undefined' ? createPortal(tooltip, document.body) : null}
    </div>
  );
}

/**
 * KPI tile with optional link, breakdown chips, sparkline.
 */
export default function KPICard({
  label,
  value,
  linkTo,
  breakdown = [],
  sparklineValues,
  sparklineColor,
  sparklinePointLabels,
}) {
  const valueEl =
    linkTo != null && linkTo !== '' ? (
      <Link to={linkTo} className="text-decoration-none text-body hover-link h4 mb-1 mt-1 d-inline-block">
        {value}
      </Link>
    ) : (
      <div className="h4 mb-1 mt-1">{value}</div>
    );

  const inner = (
    <>
      <div className="text-muted text-uppercase small fw-semibold" style={{ fontSize: '0.7rem', letterSpacing: '0.04em' }}>
        {label}
      </div>
      {valueEl}
      {breakdown?.length > 0 && (
        <div className="d-flex flex-wrap gap-1 mb-2">
          {breakdown.map((b) =>
            b.to ? (
              <Link key={b.key} to={b.to} className="text-decoration-none">
                <span className={`badge bg-${b.variant || 'secondary'} bg-opacity-25 text-${b.variant || 'secondary'}`}>{b.text}</span>
              </Link>
            ) : (
              <span key={b.key} className={`badge bg-${b.variant || 'secondary'} bg-opacity-25 text-${b.variant || 'secondary'}`}>
                {b.text}
              </span>
            )
          )}
        </div>
      )}
      <MiniSparkline
        values={sparklineValues}
        stroke={sparklineColor || 'var(--bs-primary)'}
        pointLabels={sparklinePointLabels}
        seriesLabel={label}
      />
    </>
  );

  return (
    <Card className="rh-elevated-card h-100">
      <Card.Body className="py-3">{inner}</Card.Body>
    </Card>
  );
}
