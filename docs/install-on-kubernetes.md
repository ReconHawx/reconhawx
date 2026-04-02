# Installation on Kubernetes

For prerequisites, secrets, Kueue, ingress, and `kubectl apply -k kubernetes/base/`, follow **[`kubernetes/README.md`](../kubernetes/README.md)** first.

You can install with the **[`install-kubernetes.sh`](../install-kubernetes.sh)** helper at the repo root or follow the manual steps below. The script stages manifests (`kubernetes/base`), labels nodes, installs Kueue and ingress-nginx, optionally MetalLB, and can update `/etc/hosts`. **It does not run SQL migrations**—those run in-cluster via the API Deployment’s **`run-migrations`** init container (see [Database migrations (automated)](#database-migrations-automated)).

## Database migrations (automated)

Schema changes are applied **inside the cluster** before the API pod serves traffic:

1. The **`api` Deployment** defines an init container named **`run-migrations`**.
2. That container runs the **`migrations`** image (`ghcr.io/<owner>/reconhawx/migrations`), built from [`src/migrations/`](../src/migrations/).
3. It connects to the **`postgresql`** Service using the same credentials as the API (`postgres-secret` + `database.name` from `service-config`).
4. **By default**, every pending `V*__*.sql` file is **executed** against Postgres. This is required when migrations contain real DDL.

   **Optional:** set init-container env **`MIGRATIONS_BASELINE_AUTOMARK=1`** only if your migration files are bookkeeping for a DB that was already fully created from [`kubernetes/base/postgresql/schema.sql`](../kubernetes/base/postgresql/schema.sql) and you intentionally do **not** want that SQL run (same state as the dump). Leave it **`0`** (default in the Deployment) for normal upgrades.

   If wrong rows were inserted into `schema_migrations` without running SQL, remove them (e.g. `DELETE FROM schema_migrations WHERE version = '<version>';`) and restart the API pod so the init container runs again.

To use a **custom registry or tag**, keep these aligned:

- [`kubernetes/base/config/service-config.yaml`](../kubernetes/base/config/service-config.yaml) — key **`migrations.image`**
- [`kubernetes/base/api/api-deployment.yaml`](../kubernetes/base/api/api-deployment.yaml) — **`initContainers`** → **`run-migrations`** → **`image`**

**Logs and troubleshooting:**

```bash
kubectl logs -n reconhawx deploy/api -c run-migrations
kubectl describe pod -n reconhawx -l app=api
```

If the init container fails, the API container does not start until the migration issue is fixed and the Deployment rolls again.

**Local / CI outside the cluster:** you can still use [`scripts/migrate.sh`](../scripts/migrate.sh) or `python src/migrations/migrate.py` with `DATABASE_URL` (see [`AGENTS.md`](../AGENTS.md)).

There are **two ways** to install ReconHawx on a generic Kubernetes cluster:

1. **Installer script** — run [`install-kubernetes.sh`](../install-kubernetes.sh). It uses `kubectl` (and your current kubeconfig context). **Release path** (no local `kubernetes/base`): downloads the **latest GitHub release source tarball**, uses that tree **in place** for `kubernetes/base`, applies the stack, and **leaves the extract** under `/tmp` for reuse. **Local clone path**: copies only `kubernetes/base` into **`/tmp/reconhawx`** (configurable), and deletes that staging dir after success. In both paths it labels nodes, installs Kueue and ingress-nginx, optionally MetalLB, and can update `/etc/hosts`. Release download needs **`curl`**, **`tar`**, and **`jq`** or **`python3`** for the GitHub API.
2. **Manual installation** — follow the commands below from [Set label on the nodes](#set-label-on-the-nodes) through [Test](#test).

## Installer script

From the repo root (with `kubectl` working against your cluster, e.g. `kubectl get nodes`):

```shell
./install-kubernetes.sh
```

**Without cloning the repo** (script from `main`; pin a tag or SHA in the URL for reproducible installs):

```shell
curl -fsSL https://raw.githubusercontent.com/ReconHawx/reconhawx/main/install-kubernetes.sh | bash
```

Piping into `bash` uses stdin for the script, so prompts are read from your **terminal** (`/dev/tty`). In headless environments, use `bash <(curl -fsSL …/install-kubernetes.sh)` or save the script and run `bash install-kubernetes.sh`.

**Release install** uses the extracted repository (under a `reconhawx-release.*` temp directory): secrets are written into **`kubernetes/base` there**, and the directory is **not** deleted at the end.

**Local clone install** copies `kubernetes/base` to **`/tmp/reconhawx`** (override **`INSTALL_STAGING_DIR`**). If that staging path already exists, you confirm removal first; after a **successful** install it is **deleted** (failed runs leave it for inspection).

The script lists cluster nodes and asks you to choose **runner** and **worker** nodes (by name or by number from the list); a node may be both.

Options / environment:

- **`--from-release`** — always use the latest published release tarball for manifests, even when run from a git tree.
- **`RECONHAWX_FROM_RELEASE`** — `1` forces tarball, `0` forces local `kubernetes/base`, unset selects local when it exists and tarball otherwise.
- **`RECONHAWX_GITHUB_REPO`** — `owner/repo` (default `ReconHawx/reconhawx`) for the releases API and tarball URL.
- **`INSTALL_STAGING_DIR`** — **local installs only**: staging copy (default `/tmp/reconhawx`).

## Uninstall

From the repo root, using the same kubeconfig context as for install:

```shell
./uninstall-kubernetes.sh
```

If you pipe the script (`curl … | bash`), prompts are read from your terminal (`/dev/tty`), same as for install.

At the **start** of the run, the script **detects** whether **Kueue**, **ingress-nginx**, and **MetalLB** (`metallb-system`) appear to be installed and asks **once** for each (detected only) whether to remove them after ReconHawx. A short **summary** confirms your choices so you can leave the script unattended for the rest of the teardown.

You then type **`reconhawx`** to confirm namespace deletion. The script deletes the **`reconhawx`** namespace, then removes the **cluster-scoped Kueue** `ClusterQueue` and `ResourceFlavor` objects that match [`kubernetes/base/kueue`](../kubernetes/base/kueue) defaults.

If you chose **full Kueue** removal (recommended if nothing else on the cluster uses it), that path runs next and deletes **all** `kueue.x-k8s.io` custom resources, the visibility **APIService**, the **`v0.11.1`** release manifests (same URLs as install), namespace **`kueue-system`**, leftover **`*.kueue.x-k8s.io` CRDs**, and can clear namespace **finalizers** (install **`jq`** for that step). Only confirming **`kueue-system`** by itself often **hangs** because webhooks and CRDs remain.

If you chose **full ingress-nginx** removal (recommended when you used the cloud static manifest in install), that path removes **Validating/MutatingWebhookConfiguration** objects first (they commonly block the namespace), runs **`kubectl delete -f`** on the same **`INGRESS_NGINX_DEPLOY_URL`** as install (default **`controller-v1.14.2`** cloud deploy), deletes **IngressClass nginx**, optional **`ingressclassparams.networking.k8s.io`** CRD, matching **ClusterRole(ClusterRoleBinding)**, then namespace **`ingress-nginx`** with **finalizer** cleanup. Override the URL with **`INGRESS_NGINX_DEPLOY_URL`** if your controller version differs.

If you chose **MetalLB** removal, it deletes namespace **`metallb-system`**. You can still opt in at the end to removing **`reconhawx.runner`** / **`reconhawx.worker`** node labels. Remove **`reconhawx.local`** from `/etc/hosts` manually if you no longer need it.

Override the Kueue manifest version with **`KUEUE_VERSION`** (and optionally **`KUEUE_MANIFESTS_URL`** / **`KUEUE_VISIBILITY_URL`**) if your install used a different release.

## Prerequisites

- Worker kubernetes cluster
- Have kubectl installed
- Have a KUBECONFIG file

To test: `kubectl get nodes` should list nodes.

## Manual Installation

The sections below describe the **manual** procedure for reference or troubleshooting.

### Set label on the nodes

Determine which node will be the runner and the workers.

#### Runner

Runner nodes host backend services and run workflows to dispatch jobs to workers:

- Frontend React App
- API
- Ct-Monitor
- Event-Handler
- Postgres
- NATS
- Redis

#### Worker

Worker nodes run recon tasks dispatched by the workflow.

List the cluster nodes:

```shell
kubectl get nodes
```

```
NAME    STATUS   ROLES           AGE   VERSION
k3s-1   Ready    control-plane   48d   v1.34.3+k3s3
k3s-2   Ready    <none>          48d   v1.34.3+k3s3
k3s-3   Ready    <none>          48d   v1.34.3+k3s3
k3s-4   Ready    <none>          48d   v1.34.3+k3s3
k3s-5   Ready    <none>          48d   v1.34.3+k3s3
```

Then apply the proper label on each node. A node can have both roles.

```shell
kubectl label node k3s-2 reconhawx.runner=true
kubectl label node k3s-3 reconhawx.worker=true
kubectl label node k3s-4 reconhawx.worker=true
kubectl label node k3s-5 reconhawx.worker=true
```

```
node/k3s-2 labeled
node/k3s-3 labeled
node/k3s-4 labeled
node/k3s-5 labeled
```

### Create a namespace for the reconhawx application

```shell
kubectl create namespace reconhawx
```

### Install Kueue on the cluster

```shell
kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/manifests.yaml
kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/visibility-apf.yaml
kubectl wait deploy/kueue-controller-manager -nkueue-system --for=condition=available --timeout=5m
```

### Install nginx ingress controller on the cluster

```shell
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.14.2/deploy/static/provider/cloud/deploy.yaml
kubectl wait deploy/ingress-nginx-controller -n ingress-nginx --for=condition=available --timeout=5m
kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=5m
```

Before applying manifests that include an `Ingress`, ensure the validating webhook can be reached (`validate.nginx.ingress.kubernetes.io`). If `kubectl apply` fails with `connection refused` to `ingress-nginx-controller-admission`, wait until that Service has endpoints, then retry after a short pause (or run [`install-kubernetes.sh`](../install-kubernetes.sh), which waits and retries):

```shell
kubectl get endpoints ingress-nginx-controller-admission -n ingress-nginx
```

### Create Secrets Manifests

```shell
# Copy example files
cp kubernetes/base/secrets/jwt-secret.yaml.example kubernetes/base/secrets/jwt-secret.yaml
cp kubernetes/base/secrets/postgres-secret.yaml.example kubernetes/base/secrets/postgres-secret.yaml

# Generate random secrets
sed -i "s/JWT_SECRET_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/jwt-secret.yaml
sed -i "s/REFRESH_SECRET_KEY_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/jwt-secret.yaml
sed -i "s/POSTGRES_PASSWORD_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/postgres-secret.yaml

# Set Postgres Username (Using default "reconhawx")
sed -i "s/POSTGRES_USERNAME_PLACEHOLDER/cmVjb25oYXd4/" kubernetes/base/secrets/postgres-secret.yaml
```

### Install the reconhawx application on the cluster

```shell
kubectl apply -k kubernetes/base/
```

After Postgres is up, the **API** pod’s **`run-migrations`** init container applies pending schema changes before `uvicorn` starts (see [Database migrations (automated)](#database-migrations-automated)).

### Wait for the postgresql pod to be ready and get admin password from the postgresql pod

```shell
kubectl wait deploy/postgresql -n reconhawx --for=condition=available --timeout=5m
kubectl logs deploy/postgresql -n reconhawx | grep -A2 "ADMIN USER CREATED"
```

### Set hosts file

#### Using NodeIP

To reach your ReconHawx instance, the hostname `reconhawx.local` must resolve to the IP of one of the cluster's nodes.

```shell
echo "XX.XX.XX.XX reconhawx.local" | sudo tee -a /etc/hosts
```

#### Using MetalLB (optional)

To set a single IP for your ReconHawx instance, you can use MetalLB.

Install MetalLB:

```shell
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.15.3/config/manifests/metallb-native.yaml
```

Copy the MetalLB example configuration file and set an IP for MetalLB (`192.168.0.66` in this example):

```shell
cp kubernetes/base/metal-lb/metal-lb.yaml.example kubernetes/base/metal-lb/metal-lb.yaml
sed -i 's/LB_IP_PLACEHOLDER/192\.168\.0\.66/g' kubernetes/base/metal-lb/metal-lb.yaml
echo "192.168.0.66 reconhawx.local" | sudo tee -a /etc/hosts
```

### Wait for API and Frontend healthy status

```shell
kubectl wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
```

### Test

- Browse http://reconhawx.local
- Login with `admin` using the password retrieved from the Postgres logs
