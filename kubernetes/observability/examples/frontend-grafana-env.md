# Frontend: Grafana Explore deep links

The workflow run page (`WorkflowStatusDetail`) can show **Runner pod logs** and **Worker pod logs** buttons that open Grafana Explore with a Loki query filtered to the current execution id.

## Build-time variable (Create React App)

Set **`REACT_APP_GRAFANA_URL`** to the Grafana **base URL** used by the browser (no trailing slash):

- **Dedicated host:** `https://grafana.example.com`
- **Proxied under the Reconhawx UI (nginx `/grafana/`):** `https://your.reconhawx.host/grafana` (same host as the app; path required so Explore links resolve correctly)

Example:

```bash
export REACT_APP_GRAFANA_URL=https://reconhawx.local/grafana
npm run build
```

Docker multi-stage build (see `src/frontend/Dockerfile`):

```bash
docker build --build-arg REACT_APP_GRAFANA_URL=https://grafana.example.com -f src/frontend/Dockerfile src/frontend
```

If unset, the buttons are hidden.

## Grafana datasource name

The Explore URL builder assumes the Loki datasource is named **`Loki`**, matching `additionalDataSources` in `kubernetes/observability/values-kube-prometheus-stack.yaml`. Rename either side if you change it.

## CORS / cookies

Opening Grafana in a new tab avoids CORS issues. Users still need to be logged into Grafana (or use anonymous read-only access in dev only).
