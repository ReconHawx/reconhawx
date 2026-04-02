# Installation on minikube

There are **two ways** to install ReconHawx on Minikube:

1. **Installer script** — run [`install-minikube.sh`](../install-minikube.sh) from the repo root. With **`kubernetes/base` and a `.git` directory** (git clone), it copies that tree to **`/tmp/reconhawx`** (**`INSTALL_STAGING_DIR`**) and removes it after a successful install. With **`kubernetes/base` but no `.git`** (typical unpacked release archive) or **without** a local tree, it uses manifests **in place** (your unpack dir or a downloaded extract under `/tmp/reconhawx-release.*`) — same rules as cluster [`install-kubernetes.sh`](../install-on-kubernetes.md). It generates secrets, starts or uses Minikube, applies the stack, and updates **`/etc/hosts`**. **It does not run SQL migrations**—the API Deployment’s **`run-migrations`** init container applies schema after Postgres is up (see [Database migrations (automated)](install-on-kubernetes.md#database-migrations-automated)). Piped installs (`curl … | bash`) read prompts from **`/dev/tty`**. Options: **`--from-release`**, **`--help`**, env **`RECONHAWX_FROM_RELEASE`**, **`RECONHAWX_GITHUB_REPO`**.
2. **Manual installation** — run the commands yourself in order, starting at [Manual Installation](#manual-installation). You typically edit and apply `kubernetes/base` in your checkout (as in the snippets below).

## Installer script

From the repo root:

```shell
./install-minikube.sh
```

You are prompted for a **Minikube profile** name and secrets (JWT/refresh/Postgres). There is **no** separate “install root” prompt: **in-place** installs use the unpacked tree or `/tmp/reconhawx-release.*`; **git clone** installs stage under **`/tmp/reconhawx`** if needed, and you confirm before an existing staging path is replaced.

The script uses **`minikube … kubectl` only** (no separate `kubectl` binary required). For troubleshooting migrations, use [`docs/install-on-kubernetes.md`](install-on-kubernetes.md#database-migrations-automated) or run [`scripts/migrate.sh`](../scripts/migrate.sh) locally with `DATABASE_URL` if you need to apply SQL outside the cluster.

## Upgrade

See **[`docs/update-reconhawx.md`](update-reconhawx.md)** for the full procedure (versions, `base-update`, flags, troubleshooting).

Quick path from the repo root: [`update-minikube.sh`](../update-minikube.sh) — applies **`kubernetes/base-update/`**, restarts app deployments, **`MINIKUBE_PROFILE`** default **`reconhawx`**. Options match [`update-kubernetes.sh`](../update-kubernetes.sh) / install (**`--from-release`**, **`RECONHAWX_FROM_RELEASE`**, etc.); overview: [Upgrade (existing cluster)](install-on-kubernetes.md#upgrade-existing-cluster).

## Manual Installation

The sections below describe the **manual** procedure for reference or troubleshooting.

### Install and start minikube

```shell
minikube -p reconhawx start --driver=docker --ports=80:80 --ports=443:443
```
```shell
😄  [reconhawx] minikube v1.38.1 on Nixos 26.05
    ▪ MINIKUBE_WANTUPDATENOTIFICATION=false
✨  Automatically selected the docker driver. Other choices: kvm2, ssh
❗  Starting v1.39.0, minikube will default to "containerd" container runtime. See #21973 for more info.
📌  Using Docker driver with root privileges
👍  Starting "reconhawx" primary control-plane node in "reconhawx" cluster
🚜  Pulling base image v0.0.50 ...
🔥  Creating docker container (CPUs=2, Memory=7900MB) ...
🐳  Preparing Kubernetes v1.35.1 on Docker 29.2.1 ...
🔗  Configuring bridge CNI (Container Networking Interface) ...
🔎  Verifying Kubernetes components...
    ▪ Using image gcr.io/k8s-minikube/storage-provisioner:v5
🌟  Enabled addons: storage-provisioner, default-storageclass
🏄  Done! kubectl is now configured to use "reconhawx" cluster and "default" namespace by default
```

### Set label on the minikube node

```shell
minikube -p reconhawx kubectl -- label node reconhawx reconhawx.runner=true
minikube -p reconhawx kubectl -- label node reconhawx reconhawx.worker=true
```

### Create a namespace for the reconhawx application

```shell
minikube -p reconhawx kubectl -- create namespace reconhawx
```

### Install kueue on the minikube cluster

```shell
minikube -p reconhawx kubectl -- apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/manifests.yaml
minikube -p reconhawx kubectl -- apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/visibility-apf.yaml
minikube -p reconhawx kubectl -- wait deploy/kueue-controller-manager -nkueue-system --for=condition=available --timeout=5m
```

### Install nginx ingress controller on the minikube cluster

```shell
minikube -p reconhawx addons enable ingress
minikube -p reconhawx kubectl -- wait deploy/ingress-nginx-controller -n ingress-nginx --for=condition=available --timeout=5m
minikube -p reconhawx kubectl -- rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=5m
```

Before applying manifests that include an `Ingress`, ensure the validating webhook can be reached (`validate.nginx.ingress.kubernetes.io`). If `kubectl apply` fails with `connection refused` to `ingress-nginx-controller-admission`, wait until that Service has endpoints, then retry after a short pause (or run [`install-minikube.sh`](../install-minikube.sh), which waits and retries):

```shell
minikube -p reconhawx kubectl -- get endpoints ingress-nginx-controller-admission -n ingress-nginx
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

### Install the reconhawx application on the minikube cluster

```shell
minikube -p reconhawx kubectl -- apply -k kubernetes/base/
```

### Wait for the postgresql pod to be ready and get admin password from the postgresql pod

```shell
minikube -p reconhawx kubectl -- wait deploy/postgresql -n reconhawx --for=condition=available --timeout=5m
minikube -p reconhawx kubectl -- logs deploy/postgresql -n reconhawx | grep -A2 "ADMIN USER CREATED"
```

### Get Ingress IP and set hosts file

```shell
echo "$(minikube -p reconhawx ip) reconhawx.local" | sudo tee -a /etc/hosts
```

### Wait for API and Frontend healty status

```shell
minikube -p reconhawx kubectl -- wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5
```

### Test

- Browse http://reconhawx.local
- Login with "admin" using the password retrieved from the Postgres logs
