import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { chartTheme } from '../../../utils/chartTheme';
import { formatInt, formatTrendTooltipDate } from '../dashboardUtils';

/** Map viewport coordinates to SVG user space (matches width={cw} height={ch} scaled by CSS). */
function clientToUserSpace(clientX, clientY, svgEl, cw, ch) {
  const bb = svgEl.getBoundingClientRect();
  if (!(bb.width > 0) || !(bb.height > 0)) return null;
  try {
    const ctm = svgEl.getScreenCTM();
    if (ctm?.inverse) {
      if (!svgEl.createSVGPoint) return fallbackMap(clientX, clientY, bb, cw, ch);
      const pt = svgEl.createSVGPoint();
      pt.x = clientX;
      pt.y = clientY;
      const p = pt.matrixTransform(ctm.inverse());
      return { x: p.x, y: p.y };
    }
  } catch {
    /* singular matrix, etc. */
  }
  return fallbackMap(clientX, clientY, bb, cw, ch);
}

function fallbackMap(clientX, clientY, bb, cw, ch) {
  return {
    x: ((clientX - bb.left) / bb.width) * cw,
    y: ((clientY - bb.top) / bb.height) * ch,
  };
}

/**
 * Multi-series line chart (SVG) for dashboard trends.
 * series: [{ key, label, color, values: number[] }]
 * pointLabels: optional ISO date per bucket (same length as values); used in hover tooltip
 */
export default function TrendsAreaChart({ series = [], title, xLabels = [], pointLabels = null }) {
  const containerRef = useRef(null);
  const [chartWidth, setChartWidth] = useState(640);
  const [hover, setHover] = useState(null);
  const gridPatternId = React.useId().replace(/:/g, '');

  useEffect(() => {
    const update = () => {
      if (containerRef.current) setChartWidth(containerRef.current.offsetWidth);
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  const n = series[0]?.values?.length || 0;
  if (!n) {
    return (
      <div className="text-muted small p-3 border rounded">No data for this range.</div>
    );
  }

  const labels =
    Array.isArray(pointLabels) && pointLabels.length === n ? pointLabels : null;

  const allVals = series.flatMap((s) => s.values || []);
  const maxVal = Math.max(1, ...allVals);
  const chartHeight = 240;
  const pad = { top: 16, right: 16, bottom: 28, left: 36 };
  const plotW = chartWidth - pad.left - pad.right;
  const plotH = chartHeight - pad.top - pad.bottom;
  const xDen = Math.max(n - 1, 1);

  const bucketX = (i) => pad.left + (i / xDen) * plotW;
  const valueY = (v) => pad.top + plotH - (v / maxVal) * plotH;

  const linePath = (values) =>
    values
      .map((v, i) => {
        const x = bucketX(i);
        const y = valueY(v);
        return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
      })
      .join(' ');

  const resolveHoverIdx = (clientX, clientY, svgEl) => {
    const p = clientToUserSpace(clientX, clientY, svgEl, chartWidth, chartHeight);
    if (!p) return null;
    const relX = p.x - pad.left;
    if (relX < -2 || relX > plotW + 2 || p.y < pad.top - 2 || p.y > pad.top + plotH + 2) {
      return null;
    }
    const clamped = Math.max(0, Math.min(plotW, relX));
    const idx = Math.round((clamped / plotW) * xDen);
    return Math.max(0, Math.min(n - 1, idx));
  };

  const handleSvgMouseMove = (e) => {
    const svgEl = e.currentTarget;
    if (!svgEl || svgEl.nodeName !== 'svg') return;
    const idx = resolveHoverIdx(e.clientX, e.clientY, svgEl);
    if (idx == null) {
      setHover(null);
      return;
    }
    setHover({ idx, clientX: e.clientX, clientY: e.clientY });
  };

  const crossX = hover != null ? bucketX(hover.idx) : null;

  const tooltipPos =
    hover != null && typeof window !== 'undefined'
      ? (() => {
          const padPx = 10;
          const estW = 200;
          const estH = 110;
          let left = hover.clientX + 14;
          let top = hover.clientY + 14;
          if (left + estW > window.innerWidth - padPx) {
            left = Math.max(padPx, hover.clientX - estW - 14);
          }
          if (top + estH > window.innerHeight - padPx) {
            top = Math.max(padPx, hover.clientY - estH - 14);
          }
          return { left, top };
        })()
      : hover != null
        ? { left: hover.clientX + 14, top: hover.clientY + 14 }
        : null;

  const tooltip =
    hover != null && tooltipPos ? (
      <div
        className="dashboard-trend-chart-tooltip rounded border shadow-sm px-2 py-1 bg-body small"
        style={{
          position: 'fixed',
          left: tooltipPos.left,
          top: tooltipPos.top,
          zIndex: 1100,
          pointerEvents: 'none',
          minWidth: 140,
        }}
        aria-hidden="true"
      >
        <div className="fw-semibold mb-1 text-body">
          {labels?.[hover.idx] != null
            ? formatTrendTooltipDate(labels[hover.idx])
            : `Day ${hover.idx + 1} / ${n}`}
        </div>
        {series.map((s) => {
          const v = s.values?.[hover.idx] ?? 0;
          return (
            <div key={s.key} className="d-flex align-items-center gap-2 text-body-secondary lh-sm">
              <span
                className="rounded-circle flex-shrink-0"
                style={{
                  width: 8,
                  height: 8,
                  background: s.color || 'var(--bs-primary)',
                }}
              />
              <span>{s.label}</span>
              <span className="ms-auto fw-medium text-body">{formatInt(v)}</span>
            </div>
          );
        })}
      </div>
    ) : null;

  return (
    <div
      ref={containerRef}
      className="position-relative"
      onMouseLeave={() => setHover(null)}
    >
      {title && <h6 className="mb-2">{title}</h6>}
      <svg
        role="img"
        aria-label={title ? `${title} trends` : 'Trend chart'}
        width={chartWidth}
        height={chartHeight}
        style={{ width: '100%', height: 'auto', cursor: 'crosshair', touchAction: 'none' }}
        onMouseMove={handleSvgMouseMove}
      >
        <defs>
          <pattern id={gridPatternId} width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke={chartTheme.gridStroke} strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect
          x="0"
          y="0"
          width={chartWidth}
          height={chartHeight}
          fill={`url(#${gridPatternId})`}
          opacity="0.35"
          style={{ pointerEvents: 'none' }}
        />

        {series.map((s) => (
          <path
            key={s.key}
            d={linePath(s.values)}
            fill="none"
            stroke={s.color || 'var(--bs-primary)'}
            strokeWidth="2"
            style={{ pointerEvents: 'none' }}
          />
        ))}

        {crossX != null && (
          <g style={{ pointerEvents: 'none' }}>
            <line
              x1={crossX}
              x2={crossX}
              y1={pad.top}
              y2={pad.top + plotH}
              stroke={chartTheme.axisStroke}
              strokeWidth="1"
              strokeDasharray="4 3"
              opacity={0.9}
            />
            {series.map((s) => {
              const v = s.values?.[hover.idx] ?? 0;
              const cx = bucketX(hover.idx);
              const cy = valueY(v);
              return (
                <circle
                  key={s.key}
                  cx={cx}
                  cy={cy}
                  r={5}
                  fill={chartTheme.pointRingStroke}
                  stroke={s.color || 'var(--bs-primary)'}
                  strokeWidth={2}
                />
              );
            })}
          </g>
        )}

        {xLabels.length > 0 && (
          <text
            x={pad.left}
            y={chartHeight - 6}
            fill="var(--bs-secondary-color)"
            fontSize="10"
            style={{ pointerEvents: 'none' }}
          >
            {xLabels[0]} — {xLabels[xLabels.length - 1]}
          </text>
        )}

        {/* Topmost invisible layer: reliably receives hover (fills can miss hits in some UAs) */}
        <rect
          x={pad.left}
          y={pad.top}
          width={plotW}
          height={plotH}
          fill="#fff"
          fillOpacity={0}
          pointerEvents="all"
          style={{ cursor: 'crosshair' }}
        />
      </svg>

      {tooltip && typeof document !== 'undefined' ? createPortal(tooltip, document.body) : null}

      <div className="d-flex flex-wrap gap-3 mt-2 small">
        {series.map((s) => (
          <span key={s.key}>
            <span
              className="d-inline-block rounded-circle me-1 align-middle"
              style={{ width: 8, height: 8, background: s.color || 'var(--bs-primary)' }}
            />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
