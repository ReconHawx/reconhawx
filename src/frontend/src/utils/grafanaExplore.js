/**
 * Build a Grafana Explore URL for a Loki LogQL query (Grafana 9+ JSON "left" model).
 * @param {string} grafanaBaseUrl - Origin only, e.g. https://grafana.example.com
 * @param {string} logql - LogQL expression
 * @returns {string|null}
 */
export function buildGrafanaLokiExploreUrl(grafanaBaseUrl, logql) {
  if (!grafanaBaseUrl || !logql) {
    return null;
  }
  const base = grafanaBaseUrl.replace(/\/$/, '');
  const left = {
    datasource: 'Loki',
    queries: [
      {
        refId: 'A',
        expr: logql,
        queryType: 'range',
      },
    ],
    range: { from: 'now-7d', to: 'now' },
  };
  return `${base}/explore?orgId=1&left=${encodeURIComponent(JSON.stringify(left))}`;
}
