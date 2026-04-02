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
| Role/RoleBinding | `kueue-workload-manager` | Grants the API service account permission to manage Kueue workloads |

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
