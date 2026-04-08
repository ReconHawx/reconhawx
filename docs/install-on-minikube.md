# Installation on Minikube

## What you need

- **Minikube** installed.
- The **source code archive** for a ReconHawx release from [GitHub Releases](https://github.com/ReconHawx/reconhawx/releases), extracted on the machine where you run the installer (preferred). The top-level folder must contain **`kubernetes/base`** and **`install-minikube.sh`**.
- A machine where you can run shell scripts and edit **`/etc/hosts`** (the installer can set up your UI hostname; default **`reconhawx.local`**, or a **custom hostname** if you enter one).

Manifest and secret layout matches the generic install; see **[`kubernetes/README.md`](../kubernetes/README.md)** for reference.

## Recommended install

**Preferred:** download the **Source code** archive for the release you want from [GitHub Releases](https://github.com/ReconHawx/reconhawx/releases), extract it, `cd` into that top-level directory, and run:

```shell
./install-minikube.sh
```

You are prompted for a **Minikube profile** (default often **`reconhawx`**) and secrets. The script uses **`minikube … kubectl`** only (no separate **`kubectl`** binary required). It starts or reuses the profile, installs dependencies, applies manifests, syncs Kueue quotas (needs **`python3`**), and updates **`/etc/hosts`** as needed.

**Alternative:** run the installer script from GitHub (pin a **tag or SHA** for reproducibility). It can fetch the **latest release** tarball when you do not already have `kubernetes/base` locally.

```shell
curl -fsSL https://raw.githubusercontent.com/ReconHawx/reconhawx/main/install-minikube.sh | bash
```

Piped installs read prompts from **`/dev/tty`**; for headless use, save the script and run `bash install-minikube.sh`.

### Installer options

| Input | Meaning |
|--------|---------|
| **`--from-release`** | Always use the **latest** published release tarball for manifests, even if you already have a local `kubernetes/base` directory. |
| **`--help`** | Show script usage. |
| **`RECONHAWX_FROM_RELEASE`** | `1` = fetch release tarball; `0` = use the **`kubernetes/base`** next to the script; **unset** = use that directory when present, otherwise fetch a release. |
| **`RECONHAWX_GITHUB_REPO`** | `owner/repo` for releases (default `ReconHawx/reconhawx`). |

## After install

1. **Hostname** — The default UI hostname is **`reconhawx.local`**; the installer may prompt for a **custom hostname**. Ensure that name resolves (often via **`minikube ip`**); the script may have updated **`/etc/hosts`**.
2. Wait for the API and frontend:

   ```shell
   minikube -p reconhawx kubectl -- wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
   ```

   Use your profile name in place of **`reconhawx`** if different.

3. **Admin password**:

   ```shell
   minikube -p reconhawx kubectl -- logs statefulset/postgresql -n reconhawx | grep -A2 "ADMIN USER CREATED"
   ```

4. In a browser, open **`http://reconhawx.local`** or the **custom hostname** you set during install, and sign in as **`admin`**.

## Database migrations (automated)

Same as on a full cluster: the API **`run-migrations`** init container applies schema before traffic. If the API stays not Ready:

```shell
minikube -p reconhawx kubectl -- logs -n reconhawx deploy/api -c run-migrations
```

See **[Database migrations (automated)](install-on-kubernetes.md#database-migrations-automated)** on the cluster install page.

## Upgrades

See **[`docs/update-reconhawx.md`](update-reconhawx.md)**. From the repo root:

```shell
./update-minikube.sh
```

Default profile is **`reconhawx`**. Override with **`MINIKUBE_PROFILE=my-profile`**.

## Uninstall

See **[`docs/uninstall-reconhawx.md`](uninstall-reconhawx.md)** (script or **`minikube delete -p …`**).

## Manual install (advanced)

Use this only if you are not using **`install-minikube.sh`**, typically from an **extracted release** directory so `kubernetes/base` paths match this documentation. Replace **`reconhawx`** with your Minikube profile name if different. After the steps below, run **[`reconhawx-kueue-quota-sync.py`](../reconhawx-kueue-quota-sync.py)** with **`python3`** unless you set ClusterQueues manually. For manifest context, see **[`kubernetes/README.md`](../kubernetes/README.md)**.

### Install and start minikube

```shell
minikube -p reconhawx start --driver=docker --ports=80:80 --ports=443:443
```

### Set label on the minikube node

```shell
minikube -p reconhawx kubectl -- label node reconhawx reconhawx.runner=true
minikube -p reconhawx kubectl -- label node reconhawx reconhawx.worker=true
```

If your node name is not **`reconhawx`**, use the name from `minikube -p reconhawx kubectl -- get nodes`.

### Create a namespace for the reconhawx application

```shell
minikube -p reconhawx kubectl -- create namespace reconhawx
```

### Install Kueue on the minikube cluster

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

Before applying manifests that include an `Ingress`, ensure the validating webhook can be reached. If `kubectl apply` fails with `connection refused` to `ingress-nginx-controller-admission`, wait until that Service has endpoints, then retry (or run [`install-minikube.sh`](../install-minikube.sh), which waits and retries):

```shell
minikube -p reconhawx kubectl -- get endpoints ingress-nginx-controller-admission -n ingress-nginx
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

### Install the reconhawx application on the minikube cluster

```shell
minikube -p reconhawx kubectl -- apply -k kubernetes/base/
```

### Wait for PostgreSQL and read the admin password

```shell
minikube -p reconhawx kubectl -- rollout status statefulset/postgresql -n reconhawx --timeout=5m
minikube -p reconhawx kubectl -- logs statefulset/postgresql -n reconhawx | grep -A2 "ADMIN USER CREATED"
```

### Get ingress IP and set hosts file

```shell
echo "$(minikube -p reconhawx ip) reconhawx.local" | sudo tee -a /etc/hosts
```

Use your **custom hostname** in place of **`reconhawx.local`** if you configured one in Ingress.

### Wait for API and frontend

```shell
minikube -p reconhawx kubectl -- wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
```

### Test

- Open **`http://reconhawx.local`** (or your custom hostname) in a browser.
- Log in as **`admin`** using the password from the PostgreSQL logs.
