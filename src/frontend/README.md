# React Frontend for ReconHawx

A modern React frontend showcasing the capabilities of the reconnaissance platform.

## Features

- 🌐 **Domain Management** - View and search discovered domains
- 📊 **Dashboard** - Overview of reconnaissance activities
- 🎯 **Findings** - Security findings from Nuclei and other tools
- 📁 **Program Management** - Organize reconnaissance programs
- 📋 **Workflow Management** - Manage automation workflows

## Quick Start

### Development

```bash
# Install dependencies
npm install

# CRA only (listens on :3000). For a working API in the browser, use devenv or nginx below — axios uses /api on the same origin as the page.
npm start
```

With **`devenv up`** (recommended; Kubernetes-like routing), the stack matches Kubernetes dev: **nginx** listens on **port 8080**, proxies **`/api/*`** to the API on **8000** (with the same `/api` prefix strip as [`kubernetes/overlays/dev/frontend/nginx-config.yaml`](../../kubernetes/overlays/dev/frontend/nginx-config.yaml)), and proxies everything else to the CRA dev server on **3000**. The `local_frontend_proxy` process starts **after** `api` and `frontend` are ready.

**Open the app at http://localhost:8080** (not :3000). HMR uses `WDS_SOCKET_PORT=8080` so the websocket goes through nginx.

Without devenv: start **api** and **frontend** first, then from the repo root run `nginx -e stderr -c "$PWD/nginx.local-dev.conf"` (`-e stderr` avoids nixpkgs nginx opening `/var/log/nginx/error.log` before the config loads).

Nginx access and error logs go to **stdout/stderr** so `devenv` records them under `.devenv/run/processes/logs/local_frontend_proxy.*.log`. The pid file remains `/tmp/recon-local-dev-nginx.pid`.

### Production Build

```bash
# Build for production
npm run build

# Build Docker image
./build.sh dev
```

### Kubernetes Deployment

```bash
# Deploy to development environment
kubectl apply -k /path/to/recon/kubernetes/overlays/react-frontend/dev
```

## Environment Variables

The SPA always calls **`/api`** on the same origin as the page. Nginx (local or in-cluster) proxies that to the API and strips the `/api` prefix. Do not set **`REACT_APP_API_URL`** for this app: Create React App inlines it at compile time, and an accidental value (e.g. `http://localhost:8000`) makes the browser talk to the API directly and **bypasses** `/api`.

## Architecture

- **React 18** - Modern React with hooks
- **React Router** - Client-side routing
- **Bootstrap 5** - UI components and styling
- **Axios** - HTTP client for API calls

## API Integration

The frontend uses base URL `/api` and paths such as `/assets/domain/query` (nginx strips the `/api` prefix before the request reaches FastAPI).

## Showcase Features

This is a demonstration frontend that shows:

- Clean, modern UI design
- Responsive layout
- Real-time data fetching
- Search and filtering capabilities
- Professional navigation structure
- Production-ready containerization
