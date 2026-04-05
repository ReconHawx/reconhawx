import { useEffect, useState } from 'react';

/**
 * Public /status for environments where the SPA handles the URL (CRA dev, or
 * reverse proxies that send all paths to index.html). Fetches static status.json.
 * Kubernetes/nginx should prefer serving GET /status as JSON before the SPA.
 */
function PublicHealthStatus() {
  const [body, setBody] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const url = `${process.env.PUBLIC_URL || ''}/status.json`;
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(res.statusText || String(res.status));
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setBody(data);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || 'fetch failed');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <pre style={{ margin: '1rem', whiteSpace: 'pre-wrap' }}>
        {JSON.stringify(
          { status: 'error', service: 'frontend', detail: error },
          null,
          2,
        )}
      </pre>
    );
  }
  if (body === null) {
    return <pre style={{ margin: '1rem' }}>Loading…</pre>;
  }
  return (
    <pre style={{ margin: '1rem', whiteSpace: 'pre-wrap' }}>
      {JSON.stringify(body, null, 2)}
    </pre>
  );
}

export default PublicHealthStatus;
