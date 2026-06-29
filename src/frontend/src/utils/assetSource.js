export function formatAssetSource(source) {
  if (!source) return '—';
  const labels = {
    ct_monitor: 'CT Monitor',
    manual_import: 'Manual import',
    finding_ingest: 'Finding ingest',
    subdomain_finder: 'Subdomain Finder',
    test_http: 'Test HTTP',
    resolve_domain: 'Resolve Domain',
    subdomain_permutations: 'Subdomain Permutations',
  };
  if (labels[source]) return labels[source];
  return source.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
}

export function parseSourceFilterParam(value) {
  if (!value) return [];
  return value.split(',').map((s) => s.trim()).filter(Boolean);
}

export function serializeSourceFilterParam(values) {
  if (!values || values.length === 0) return '';
  return [...values].sort().join(',');
}

export function sourceFiltersEqual(a, b) {
  return serializeSourceFilterParam(a) === serializeSourceFilterParam(b);
}
