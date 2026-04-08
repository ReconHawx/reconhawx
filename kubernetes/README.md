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

After a manual deploy, **[`reconhawx-kueue-quota-sync.py`](../reconhawx-kueue-quota-sync.py)** at the repo root sets **ClusterQueue** `nominalQuota` from nodes labeled `reconhawx.runner` / `reconhawx.worker` (requires **`python3`**). The **`install-kubernetes.sh`** / **`install-minikube.sh`** helpers run it automatically.

## Upgrading an existing install

Use repo root **`update-kubernetes.sh`** or **`update-minikube.sh`**, or manually `kubectl apply -k kubernetes/base-update/` then restart app Deployments. See **[`docs/update-reconhawx.md`](../docs/update-reconhawx.md)** for prerequisites, versioning (`reconhawx-version` / `APP_VERSION`), why **`base-update`** avoids re-applying Secrets from git, and troubleshooting.

### PostgreSQL: Deployment to StatefulSet (existing clusters)

Manifests run PostgreSQL as a **StatefulSet** with a **headless** Service (`postgresql-headless`) for pod identity and the existing **NodePort** Service `postgresql` for clients. If the cluster still has **`deployment.apps/postgresql`** from an older release, do **not** apply the StatefulSet while that Deployment is running: both select `app=postgresql`, so the Service could send traffic to two Postgres instances.

**Preferred:** run **`./update-kubernetes.sh`** or **`./update-minikube.sh`** from the release you are upgrading to. Pre-apply hooks in [`base-update/pre-apply.d/`](base-update/pre-apply.d/) drop the legacy Deployment and wait for pods to exit before `kubectl apply`. See **[`docs/update-reconhawx.md`](../docs/update-reconhawx.md)** and [`base-update/pre-apply.d/README.md`](base-update/pre-apply.d/README.md).

**Manual:** plan a short database downtime window, then:

1. Remove the old controller and wait until no pod with `app=postgresql` is running so the **ReadWriteOnce** PVC can attach to the new pod:

   ```bash
   kubectl delete deployment postgresql -n reconhawx --ignore-not-found
   ```

   Re-run `kubectl get pods -n reconhawx -l app=postgresql` until it lists no pods (often a few seconds).

2. Apply updated manifests (`kubectl apply -k kubernetes/base-update/` or your overlay), or run pre-apply hooks by hand as described in [`kubernetes/base-update/pre-apply.d/README.md`](base-update/pre-apply.d/README.md).

Clusters that never had the Deployment only need a normal apply.

## Default Admin User

On first deploy (fresh PVC), PostgreSQL automatically creates an `admin` superuser with a random password. Retrieve the credentials from the pod logs:

```bash
kubectl logs statefulset/postgresql -n reconhawx | grep -A4 "ADMIN USER CREATED"
```

Change this password after your first login.

## Database backup and restore (superuser)

The API exposes `/admin/database/status`, `/admin/database/backup`, and **`/admin/database/maintenance/*`** (maintenance, Kueue drain, Job restore). In the UI: **Administration → System maintenance** (`/admin/system-maintenance`; `/admin/database-backup` redirects).

**Who talks to Postgres (steady state):** primarily the **API** (SQLAlchemy). Runner workflow jobs usually call the API over HTTP; the **`dummy_batch`** task is an exception (direct `asyncpg`)—avoid it in production workflows you care about. Workers, event-handler, and ct-monitor should not open the app database directly.

### Maintenance mode (UI + optional env)

- **Normal:** Superusers toggle maintenance in the UI (stored in **`system_settings.maintenance_mode`**). When effective, the API returns **503** for most routes; **`/status`**, **`/admin/database/*`**, and the internal restore pull path stay available.
- **Break-glass:** Set **`MAINTENANCE_MODE`** (and optionally **`MAINTENANCE_MESSAGE`**) on the API Deployment if you must force a gate when the DB setting is unavailable.

### Kueue drain before restore

Patch all four **ClusterQueue** resources to **`spec.stopPolicy: Hold`** (via admin API or `kubectl`) so **new** workloads are not admitted while **admitted** jobs **run to completion**. Use **`Hold`**, not **`HoldAndDrain`**: in Kueue, **HoldAndDrain evicts** admitted workloads (they tend to restart when you clear the policy). Reserving workloads cancel reservation under either policy. Clear `stopPolicy` when done. The API **`api-sa`** needs **ClusterRole** permission to **patch** `clusterqueues` (see `kubernetes/base/kueue/core/api-kueue-clusterqueue-rbac.yaml`).

### Job-based restore (recommended in cluster)

Restore by **staging** a dump on the API pod (**`POST /admin/database/maintenance/restore/stage`**), then **`POST .../restore/job`** which creates a **Batch Job**: initContainer **curl** fetches the dump from the API using **`internal-service-secret`**, then **`pg_restore`** runs in a **`postgres:15`** container. The Job removes the dump file on exit (`trap`); the API clears staging metadata when the Job reaches a terminal phase. **`DATABASE_RESTORE_MAX_BYTES`** caps uploads (default 5 GiB). Use **Secrets** only for tiny metadata—**not** multi‑GiB dumps (~1 MiB object limit).

### Redis and NATS after restore

The database may be **older or newer** than **Redis** caches and **NATS JetStream** streams. After a restore, you may see **stuck workflows**, duplicate processing, or stale UI until you **restart runner** (and optionally **flush Redis** or adjust streams). This is **not** solved by queuing maintenance alone—document your post-restore checklist.

The API image ships **PostgreSQL 15 client tools** (`postgresql-client-15`). The **frontend nginx** ConfigMap and **Ingress** allow request bodies up to **6g** so large stages/restores are not rejected with **413**.

## What Gets Deployed

| Component | Description |
|-----------|-------------|
| **PostgreSQL** | StatefulSet, PVC-backed (`postgresql-headless` + `postgresql` Service) |
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

The base manifests create the following Kueue resources in the **`reconhawx`** namespace:

| Resource | Name | Purpose |
|----------|------|---------|
| ResourceFlavor | `runner-flavor` | Targets nodes with label `reconhawx.runner: "true"` |
| ResourceFlavor | `worker-flavor` | Targets nodes with label `reconhawx.worker: "true"` |
| ClusterQueue | `runner-cluster-queue` | Runner workflow jobs (runner-flavor); placeholder in git — run [`reconhawx-kueue-quota-sync.py`](../reconhawx-kueue-quota-sync.py) or the install helpers to size from the cluster |
| ClusterQueue | `worker-cluster-queue` | Worker jobs (worker-flavor); same as above |
| ClusterQueue | `ai-analysis-cluster-queue` | AI batch jobs — fixed **500m CPU, 512Mi** (one concurrent job); keep aligned with Job **requests** in `src/api/app/services/job_submission.py` |
| LocalQueue | `recon-runner-queue` | Namespace queue bound to `runner-cluster-queue` |
| LocalQueue | `recon-worker-queue` | Namespace queue bound to `worker-cluster-queue` |
| LocalQueue | `recon-ai-analysis-queue` | Namespace queue bound to `ai-analysis-cluster-queue` |
| Role/RoleBinding | `kueue-workload-manager` | Grants the API service account permission to manage namespaced Kueue workloads |
| ClusterRole/ClusterRoleBinding | `reconhawx-api-kueue-clusterqueues` | **`clusterqueues`** get/list/patch/update for maintenance **stopPolicy** |

These are all applied automatically as part of `kubectl apply -k kubernetes/base/`. **[`kubernetes/base-update/`](../base-update/kustomization.yaml)** includes **`kueue/core`** only (flavors, local queues, RBAC), not **ClusterQueue** YAMLs under [`kueue/cluster-queues/`](base/kueue/cluster-queues/kustomization.yaml), so updates do not overwrite cluster-sized quotas. Use **`RECONHAWX_KUEUE_RESYNC_QUOTAS=1`** on an update run, or run **`reconhawx-kueue-quota-sync.py`** manually after adding nodes.

### 3. Node labels for flavors

The `runner-flavor` and `worker-flavor` target **`reconhawx.runner`** and **`reconhawx.worker`**. If your cluster does not have dedicated runner/worker nodes, you can label any node:

```bash
kubectl label node <node-name> reconhawx.runner=true --overwrite
kubectl label node <node-name> reconhawx.worker=true --overwrite
```

On a single-node cluster, apply both labels to the same node.

### 4. Tuning quotas

Default **ClusterQueue** quotas in git are placeholders. Prefer **`reconhawx-kueue-quota-sync.py`** (or the install scripts) so **`runner-cluster-queue`** and **`worker-cluster-queue`** match allocatable resources after a small reserve. **`ai-analysis-cluster-queue`** stays at one-job capacity (500m / 512Mi by default) so only one AI analysis batch runs at a time.

You can still patch or overlay **ClusterQueue** resources manually. For example, to increase the runner queue:

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

Or edit the files under `base/kueue/cluster-queues/` directly if you are not using overlays.

## Customization

### Images

Base manifests pin internal images to the **release semver** (same tag GHCR gets from release-please, e.g. `0.7.0`). Source files still use a `:latest` suffix for readability; Kustomize (**[`base/components/pinned-releases`](base/components/pinned-releases/kustomization.yaml)**) rewrites those images (and **`runner.image`** / **`worker.image`** in **`service-config`**) from **`reconhawx-version`** ConfigMap **`data.APP_VERSION`**, defined in **`base/config/reconhawx-version.yaml`** (bumped with **`version.txt`**).

Check what version the cluster is tracking:

```bash
kubectl get configmap reconhawx-version -n reconhawx -o jsonpath='{.data.APP_VERSION}{"\n"}'
```

**Upgrades** without re-applying secrets from git: `kubectl apply -k kubernetes/base-update/` (see **[`base-update/kustomization.yaml`](base-update/kustomization.yaml)** and repo root **`update-kubernetes.sh`**).

To use a **custom registry or tag**, create a kustomize overlay on top of `base` (or `base-update`) and patch images / ConfigMap data as needed—for example, extend **`images:`** if you replace `components/pinned-releases` in your overlay.

The API chooses runner and worker images when it creates jobs from **`system_settings`** (`workflow_kubernetes`), exposed to superusers under **Admin → System settings → Workflow settings**. With no stored overrides, defaults use **`APP_VERSION`** on the API pod (`ghcr.io/reconhawx/reconhawx/runner:<version>` and `.../worker:<version>`, pull policy **`IfNotPresent`**); base deploys set **`APP_VERSION`** from the **`reconhawx-version`** ConfigMap. In the UI you set an **image repository** (no tag) and either **Match deployment (APP_VERSION)** or a **custom tag**, so upgrading the API pod’s version updates runner/worker tags automatically unless you pin a custom tag. Older installs may still store a **legacy** full image reference (single string), which behaves like a full override until you save in the new shape or use **Reset to version defaults**. The **`service-config`** keys **`runner.image`**, **`worker.image`**, and **`image.pull.policy`** remain for Kustomize pinned-releases / gitops consistency but are **not** injected into the API as environment variables.

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
