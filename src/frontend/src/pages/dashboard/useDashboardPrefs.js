import { useCallback, useEffect, useMemo, useState } from 'react';

export const DASHBOARD_PREFS_KEY = 'rh.dashboardPrefs.v1';

export const DASHBOARD_WIDGET_IDS = [
  'kpiStrip',
  'securityPosture',
  'operations',
  'trends',
  'latestActivity',
  'insights',
];

export const WIDGET_LABELS = {
  kpiStrip: 'Key metrics',
  securityPosture: 'Security posture',
  operations: 'Operations',
  trends: 'Trends',
  latestActivity: 'Recent activity',
  insights: 'Top technologies',
};

const DEFAULT_ORDER = [...DASHBOARD_WIDGET_IDS];

const DEFAULT_VISIBLE = DASHBOARD_WIDGET_IDS.reduce((acc, id) => {
  acc[id] = true;
  return acc;
}, {});

function loadRaw() {
  try {
    const raw = localStorage.getItem(DASHBOARD_PREFS_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function useDashboardPrefs() {
  const raw = typeof window !== 'undefined' ? loadRaw() : null;

  const [order, setOrder] = useState(() => {
    const o = raw?.order;
    if (Array.isArray(o) && o.length) {
      const merged = [...new Set([...o, ...DEFAULT_ORDER])];
      return merged.filter((id) => DEFAULT_ORDER.includes(id));
    }
    return [...DEFAULT_ORDER];
  });

  const [visible, setVisible] = useState(() => ({
    ...DEFAULT_VISIBLE,
    ...(raw?.visible && typeof raw.visible === 'object' ? raw.visible : {}),
  }));

  const [datePreset, setDatePreset] = useState(() =>
    ['7d', '30d', '90d', 'custom'].includes(raw?.datePreset) ? raw.datePreset : '30d'
  );
  const [customFrom, setCustomFrom] = useState(() => raw?.customFrom || '');
  const [customTo, setCustomTo] = useState(() => raw?.customTo || '');

  useEffect(() => {
    const payload = {
      order,
      visible,
      datePreset,
      customFrom,
      customTo,
    };
    try {
      localStorage.setItem(DASHBOARD_PREFS_KEY, JSON.stringify(payload));
    } catch {
      /* ignore quota */
    }
  }, [order, visible, datePreset, customFrom, customTo]);

  const prefs = useMemo(
    () => ({ datePreset, customFrom, customTo }),
    [datePreset, customFrom, customTo]
  );

  const toggleWidget = useCallback((id) => {
    setVisible((v) => ({ ...v, [id]: !v[id] }));
  }, []);

  const moveWidget = useCallback((id, direction) => {
    setOrder((prev) => {
      const idx = prev.indexOf(id);
      if (idx < 0) return prev;
      const next = [...prev];
      const j = direction === 'up' ? idx - 1 : idx + 1;
      if (j < 0 || j >= next.length) return prev;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  }, []);

  const resetDefaults = useCallback(() => {
    setOrder([...DEFAULT_ORDER]);
    setVisible({ ...DEFAULT_VISIBLE });
    setDatePreset('30d');
    setCustomFrom('');
    setCustomTo('');
  }, []);

  return {
    order,
    visible,
    prefs,
    datePreset,
    setDatePreset,
    customFrom,
    setCustomFrom,
    customTo,
    setCustomTo,
    toggleWidget,
    moveWidget,
    resetDefaults,
  };
}
