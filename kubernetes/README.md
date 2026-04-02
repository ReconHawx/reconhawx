# Kubernetes Deployment

Deploy ReconHawx to a Kubernetes cluster using the base manifests.

## Prerequisites

1. **Kubernetes cluster** with `kubectl` configured.
2. **[Kueue](https://kueue.sigs.k8s.io/)** installed in the cluster (workflow job scheduling). See [Kueue Setup](#kueue-setup) below.
3. **nginx ingress controller** — the frontend ingress uses `ingressClassName: nginx`. Install one if your cluster doesn't have it, or adjust the ingress to match your setup.
4. **Node label** — most workloads use `nodeSelector: reconhawx.runner: "true"`. Label at least one node:

   ```bash
   kubectl label node <node-name> reconhawx.runner=true --overwrite
   ```

## Quick Start

```bash
# 1. Create the namespace
kubectl apply -f kubernetes/base/namespaces.yaml

# 2. Create secrets (see kubernetes/base/secrets/README.md)
cd kubernetes/base/secrets/
cp jwt-secret.yaml.example jwt-secret.yaml
cp postgres-secret.yaml.example postgres-secret.yaml
# Edit both files — replace placeholder values with real base64-encoded credentials
kubectl apply -f jwt-secret.yaml -n reconhawx
kubectl apply -f postgres-secret.yaml -n reconhawx
cd ../../..

# 3. Deploy everything
kubectl apply -k kubernetes/base/
```

## Upgrading an existing install

Use repo root **`update-kubernetes.sh`** or **`update-minikube.sh`**, or manually `kubectl apply -k kubernetes/base-update/` then restart app Deployments. See **[`docs/update-reconhawx.md`](../docs/update-reconhawx.md)** for prerequisites, versioning (`reconhawx-version` / `APP_VERSION`), why **`base-update`** avoids re-applying Secrets from git, and troubleshooting.

## Default Admin User

On first deploy (fresh PVC), PostgreSQL automatically creates an `admin` superuser with a random password. Retrieve the credentials from the pod logs:

```bash
kubectl logs deploy/postgresql -n reconhawx | grep -A4 "ADMIN USER CREATED"
```

Change this password after your first login.

## Database backup and restore (superuser)

The API exposes `/admin/database/status`, `/admin/database/backup`, and **`/admin/database/maintenance/*`** (maintenance, Kueue drain, Job restore). In the UI: **Administration → System maintenance** (`/admin/system-maintenance`; `/admin/database-backup` redirects).

**Who talks to Postgres (steady state):** primarily the **API** (SQLAlchemy). Runner workflow jobs usually call the API over HTTP; the **`dummy_batch`** task is an exception (direct `asyncpg`)—avoid it in production workflows you care about. Workers, event-handler, and ct-monitor should not open the app database directly.

### Maintenance mode (UI + optional env)

- **Normal:** Superusers toggle maintenance in the UI (stored in **`system_settings.maintenance_mode`**). When effective, the API returns **503** for most routes; **`/status`**, **`/admin/database/*`**, and the internal restore pull path stay available.
- **Break-glass:** Set **`MAINTENANCE_MODE`** (and optionally **`MAINTENANCE_MESSAGE`**) on the API Deployment if you must force a gate when the DB setting is unavailable.

### Kueue drain before restore

Patch all four **ClusterQueue** resources to **`spec.stopPolicy: Hold`** (via admin API or `kubectl`) so **new** workloads are not admitted while **admitted** jobs **run to completion**. Use **`Hold`**, not **`HoldAndDrain`**: in Kueue, **HoldAndDrain evicts** admitted workloads (they tend to restart when you clear the policy). Reserving workloads cancel reservation under either policy. Clear `stopPolicy` when done. The API **`api-sa`** needs **ClusterRole** permission to **patch** `clusterqueues` (see `kubernetes/base/kueue/api-kueue-clusterqueue-rbac.yaml`).

### Job-based restore (recommended in cluster)

Restore by **staging** a dump on the API pod (**`POST /admin/database/maintenance/restore/stage`**), then **`POST .../restore/job`** which creates a **Batch Job**: initContainer **curl** fetches the dump from the API using **`internal-service-secret`**, then **`pg_restore`** runs in a **`postgres:15`** container. The Job removes the dump file on exit (`trap`); the API clears staging metadata when the Job reaches a terminal phase. **`DATABASE_RESTORE_MAX_BYTES`** caps uploads (default 5 GiB). Use **Secrets** only for tiny metadata—**not** multi‑GiB dumps (~1 MiB object limit).

### Redis and NATS after restore

The database may be **older or newer** than **Redis** caches and **NATS JetStream** streams. After a restore, you may see **stuck workflows**, duplicate processing, or stale UI until you **restart runner** (and optionally **flush Redis** or adjust streams). This is **not** solved by queuing maintenance alone—document your post-restore checklist.

The API image ships **PostgreSQL 15 client tools** (`postgresql-client-15`). The **frontend nginx** ConfigMap and **Ingress** allow request bodies up to **6g** so large stages/restores are not rejected with **413**.

## What Gets Deployed

| Component | Description |
|-----------|-------------|
| **PostgreSQL** | Database (PVC-backed) |
| **NATS** | Message broker with JetStream (streams created on startup) |
| **Redis** | Cache / pub-sub |
| **Kueue** | Job queue CRDs, cluster queues, and resource flavors |
| **API** | FastAPI backend (init container runs DB migrations before the app starts) |
| **Frontend** | React UI behind nginx |
| **Event Handler** | NATS event consumer |
| **CT Monitor** | Certificate Transparency log watcher |
| **Runner** | RBAC for workflow runner jobs (pods created dynamically by the API) |
| **Config** | `recon-config` ConfigMap shared by all services |

## Kueue Setup

[Kueue](https://kueue.sigs.k8s.io/) is a Kubernetes-native job queueing system that ReconHawx uses to schedule and manage workflow runner/worker jobs. It must be installed **before** deploying the application.

### 1. Install Kueue CRDs and controller

Install the latest stable release (check [releases](https://github.com/kubernetes-sigs/kueue/releases) for the current version):

```bash
VERSION=v0.10.1
kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/$VERSION/manifests.yaml
```

Verify the controller is running:

```bash
kubectl get pods -n kueue-system
```

Wait until the `kueue-controller-manager` pod is `Running` before proceeding.

### 2. What `base/kueue/` provides

The base manifests create the following Kueue resources in the `recon` namespace:

| Resource | Name | Purpose |
|----------|------|---------|
| ResourceFlavor | `default-flavor` | Generic resource flavor (no node constraints) |
| ResourceFlavor | `runner-flavor` | Targets nodes with label `type: runner` |
| ResourceFlavor | `worker-flavor` | Targets nodes with label `type: worker` |
| ClusterQueue | `cluster-queue` | General queue — 10 CPU, 4Gi memory (default-flavor) |
| ClusterQueue | `runner-cluster-queue` | Runner jobs — 2 CPU, 4Gi memory (runner-flavor) |
| ClusterQueue | `worker-cluster-queue` | Worker jobs — 4 CPU, 8Gi memory (worker-flavor) |
| ClusterQueue | `ai-analysis-cluster-queue` | AI analysis — 500m CPU, 512Mi memory (runner-flavor) |
| LocalQueue | `recon-user-queue` | Namespace queue bound to `cluster-queue` |
| LocalQueue | `recon-runner-queue` | Namespace queue bound to `runner-cluster-queue` |
| LocalQueue | `recon-worker-queue` | Namespace queue bound to `worker-cluster-queue` |
| LocalQueue | `recon-ai-analysis-queue` | Namespace queue bound to `ai-analysis-cluster-queue` |
| Role/RoleBinding | `kueue-workload-manager` | Grants the API service account permission to manage namespaced Kueue workloads |
| ClusterRole/ClusterRoleBinding | `reconhawx-api-kueue-clusterqueues` | **`clusterqueues`** get/list/patch/update for maintenance **stopPolicy** |

These are all applied automatically as part of `kubectl apply -k kubernetes/base/`.

### 3. Node labels for flavors

The `runner-flavor` and `worker-flavor` target specific node labels. If your cluster does not have dedicated runner/worker nodes, you can label any node:

```bash
kubectl label node <node-name> type=runner --overwrite
kubectl label node <node-name> type=worker --overwrite
```

On a single-node cluster, apply both labels to the same node.

### 4. Tuning quotas

The default quotas are conservative. Adjust them to match your cluster capacity by patching the ClusterQueue resources. For example, to increase the runner queue:

```yaml
# my-overlay/patches/runner-cluster-queue-patch.yaml
apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: runner-cluster-queue
spec:
  resourceGroups:
  - coveredResources: ["cpu", "memory"]
    flavors:
    - name: "runner-flavor"
      resources:
      - name: "cpu"
        nominalQuota: 16
      - name: "memory"
        nominalQuota: 24Gi
```

Or edit the files under `base/kueue/` directly if you are not using overlays.

## Customization

### Images

Base manifests pin internal images to the **release semver** (same tag GHCR gets from release-please, e.g. `0.7.0`). Source files still use a `:latest` suffix for readability; Kustomize (**[`base/components/pinned-releases`](base/components/pinned-releases/kustomization.yaml)**) rewrites those images (and **`runner.image`** / **`worker.image`** in **`service-config`**) from **`reconhawx-version`** ConfigMap **`data.APP_VERSION`**, defined in **`base/config/reconhawx-version.yaml`** (bumped with **`version.txt`**).

Check what version the cluster is tracking:

```bash
kubectl get configmap reconhawx-version -n reconhawx -o jsonpath='{.data.APP_VERSION}{"\n"}'
```

**Upgrades** without re-applying secrets from git: `kubectl apply -k kubernetes/base-update/` (see **[`base-update/kustomization.yaml`](base-update/kustomization.yaml)** and repo root **`update-kubernetes.sh`**).

To use a **custom registry or tag**, create a kustomize overlay on top of `base` (or `base-update`) and patch images / ConfigMap data as needed—for example, extend **`images:`** if you replace `components/pinned-releases` in your overlay.

Runner and worker job images are set via **`service-config`** keys **`runner.image`** and **`worker.image`** (rewritten by the pinned-releases component to match **`APP_VERSION`**).

### Ingress

The base frontend ingress uses host `recon.example.local`. Override it with a patch:

```yaml
# my-overlay/patches/ingress-patch.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: frontend-ingress
spec:
  rules:
  - host: my.domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend
            port:
              number: 80
```

### Kueue Quotas

See [Tuning quotas](#4-tuning-quotas) in the Kueue section above.

### Node Selector

All workloads target nodes with label `reconhawx.runner=true`. To remove this constraint, patch the deployments in your overlay to clear the `nodeSelector`.

## Secrets Reference

| Secret | Keys | Used By |
|--------|------|---------|
| `postgres-secret` | `postgres-root-username`, `postgres-root-password` | API, PostgreSQL |
| `jwt-secret` | `jwt-secret-key`, `refresh-secret-key` | API |
| `internal-service-secret` | `token` | API, CT Monitor, Event Handler (optional) |

See [`base/secrets/README.md`](base/secrets/README.md) for setup instructions.
