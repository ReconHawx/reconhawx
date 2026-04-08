# Installation on Kubernetes

## What you need

- A **Kubernetes cluster** and **`kubectl`** configured (`kubectl get nodes` works).
- The **source code archive** for a ReconHawx release from [GitHub Releases](https://github.com/ReconHawx/reconhawx/releases), extracted on the machine where you run the installer (preferred). The top-level folder must contain **`kubernetes/base`** and **`install-kubernetes.sh`**.
- **Nodes** you can label for **runner** and **worker** roles (one node can be both). The installer walks you through choosing them.
- A way for your browser to resolve the **UI hostname** (default **`reconhawx.local`**; the installer can prompt for a **custom hostname** instead—then use that in **`/etc/hosts`** or DNS as usual).

Full prerequisite detail (secrets layout, Kueue, ingress, manifest tree) is in **[`kubernetes/README.md`](../kubernetes/README.md)**.

## Recommended install

**Preferred:** on a machine with `kubectl` access to your cluster, download the **Source code** archive for the release you want from [GitHub Releases](https://github.com/ReconHawx/reconhawx/releases), extract it, `cd` into that top-level directory, and run:

```shell
./install-kubernetes.sh
```

The installer expects **`kubernetes/base`** next to the script. It installs **Kueue**, **ingress-nginx**, optionally **MetalLB**, labels nodes, writes secrets under **`kubernetes/base`**, applies manifests, syncs **ClusterQueue** quotas (needs **`python3`**), and can update **`/etc/hosts`**.

**Alternative:** run the installer script straight from GitHub (pin a **tag or SHA** in the URL for reproducibility). It can fetch the **latest release** tarball for you when you do not already have `kubernetes/base` locally. That path needs **`curl`**, **`tar`**, and **`jq`** or **`python3`** for the GitHub API.

```shell
curl -fsSL https://raw.githubusercontent.com/ReconHawx/reconhawx/main/install-kubernetes.sh | bash
```

Piping into `bash` uses stdin for the script, so prompts are read from your **terminal** (`/dev/tty`). In headless environments, use `bash <(curl -fsSL …/install-kubernetes.sh)` or save the script and run `bash install-kubernetes.sh`.

### Installer options

| Input | Meaning |
|--------|---------|
| **`--from-release`** | Always use the **latest** published release tarball for manifests, even if you already have a local `kubernetes/base` directory. |
| **`RECONHAWX_FROM_RELEASE`** | `1` = fetch release tarball; `0` = use the **`kubernetes/base`** next to the script; **unset** = use that directory when present, otherwise fetch a release. |
| **`RECONHAWX_GITHUB_REPO`** | `owner/repo` for releases (default `ReconHawx/reconhawx`). |

## After install

1. **Hostname** — The default UI hostname is **`reconhawx.local`**. The installer can prompt for a **custom hostname**; use whatever you entered. Ensure that name resolves (the script may have appended **`/etc/hosts`**). Otherwise point it at a node IP or load-balancer IP as in **[`kubernetes/README.md`](../kubernetes/README.md)**.
2. Wait for core workloads:

   ```bash
   kubectl wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
   ```

3. **Admin password** (first boot):

   ```bash
   kubectl logs statefulset/postgresql -n reconhawx | grep -A2 "ADMIN USER CREATED"
   ```

4. In a browser, open **`http://reconhawx.local`** or the **custom hostname** you set during install, and sign in as **`admin`** with that password.

## Database migrations (automated)

Schema updates run **inside the cluster** in the API Deployment’s **`run-migrations`** init container **before** the API serves traffic. You do not run SQL migrations manually for a normal install.

If the API never becomes Ready after install or upgrade:

```bash
kubectl logs -n reconhawx deploy/api -c run-migrations
kubectl describe pod -n reconhawx -l app=api
```

## Upgrades

Use **[`docs/update-reconhawx.md`](update-reconhawx.md)** (`./update-kubernetes.sh` from an extracted release tree).

## Uninstall

See **[`docs/uninstall-reconhawx.md`](uninstall-reconhawx.md)**.

## Manual install (advanced)

Use this only if you are not using **`install-kubernetes.sh`**, typically from an **extracted release** directory so `kubernetes/base` paths match this documentation. For more context (Quick Start, image pins, Kueue overview), see **[`kubernetes/README.md`](../kubernetes/README.md)**. After the steps below, run **[`reconhawx-kueue-quota-sync.py`](../reconhawx-kueue-quota-sync.py)** so **ClusterQueue** quotas match labeled nodes (requires **`python3`**), unless you set quotas yourself.

### Set label on the nodes

**Runner** nodes run the control plane services (frontend, API, Postgres, NATS, Redis, event-handler, ct-monitor) and dispatch workflows. **Worker** nodes run recon tasks. A node may have both labels.

List nodes, then label (replace names with your nodes):

```shell
kubectl get nodes
```

```shell
kubectl label node k3s-2 reconhawx.runner=true
kubectl label node k3s-3 reconhawx.worker=true
kubectl label node k3s-4 reconhawx.worker=true
kubectl label node k3s-5 reconhawx.worker=true
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

### Create Secrets manifests

```shell
# Copy example files
cp kubernetes/base/secrets/jwt-secret.yaml.example kubernetes/base/secrets/jwt-secret.yaml
cp kubernetes/base/secrets/postgres-secret.yaml.example kubernetes/base/secrets/postgres-secret.yaml

# Generate random secrets
sed -i "s/JWT_SECRET_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/jwt-secret.yaml
sed -i "s/REFRESH_SECRET_KEY_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/jwt-secret.yaml
sed -i "s/POSTGRES_PASSWORD_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/postgres-secret.yaml

# Set Postgres username (default "reconhawx")
sed -i "s/POSTGRES_USERNAME_PLACEHOLDER/cmVjb25oYXd4/" kubernetes/base/secrets/postgres-secret.yaml
```

### Install the reconhawx application on the cluster

```shell
kubectl apply -k kubernetes/base/
```

After Postgres is up, the API pod’s **`run-migrations`** init container applies pending schema before `uvicorn` starts (see [Database migrations (automated)](#database-migrations-automated)).

### Wait for PostgreSQL and read the admin password

```shell
kubectl rollout status statefulset/postgresql -n reconhawx --timeout=5m
kubectl logs statefulset/postgresql -n reconhawx | grep -A2 "ADMIN USER CREATED"
```

### Set hosts file

#### Using node IP

The UI hostname defaults to **`reconhawx.local`** (or whatever you configured in Ingress). It must resolve to a node IP (or LB IP) that reaches the ingress controller.

```shell
echo "XX.XX.XX.XX reconhawx.local" | sudo tee -a /etc/hosts
```

#### Using MetalLB (optional)

```shell
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.15.3/config/manifests/metallb-native.yaml
```

```shell
cp kubernetes/base/metal-lb/metal-lb.yaml.example kubernetes/base/metal-lb/metal-lb.yaml
sed -i 's/LB_IP_PLACEHOLDER/192\.168\.0\.66/g' kubernetes/base/metal-lb/metal-lb.yaml
echo "192.168.0.66 reconhawx.local" | sudo tee -a /etc/hosts
```

Apply the edited MetalLB manifests as described in **[`kubernetes/README.md`](../kubernetes/README.md)** if they are not already part of your `kubectl apply -k kubernetes/base/` run.

### Wait for API and frontend

```shell
kubectl wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
```

### Test

- Open **`http://reconhawx.local`** (or your custom hostname) in a browser.
- Log in as **`admin`** using the password from the PostgreSQL logs.
