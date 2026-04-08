# Upgrading ReconHawx on Kubernetes

This guide describes how to move an **existing** cluster to newer **manifests** and **container images** after you already completed a first-time install ([`install-kubernetes.sh`](../install-kubernetes.sh) or [`install-minikube.sh`](../install-minikube.sh), or a manual `kubectl apply -k kubernetes/base/`).

Upgrades are different from install: they do **not** reinstall Kueue, ingress-nginx, MetalLB, or relabel nodes. They **apply** the current ReconHawx kustomize bundle and **restart** application Deployments so new image tags take effect.

## What you need

| Requirement | Notes |
|-------------|--------|
| **Release tree on disk** | **Preferred:** extract the **Source code** archive from [GitHub Releases](https://github.com/ReconHawx/reconhawx/releases). You need `kubernetes/base`, `kubernetes/base-update`, and the update scripts at the **top level** (e.g. `update-kubernetes.sh`, `reconhawx-k8s-common.sh`). Running `curl \| bash` on the install script alone is **not** enough for updates—you need that tree on disk (or let the update script fetch a tarball—see flags below). |
| **`kubectl`** (generic cluster) | Same kubeconfig / context you used for install. |
| **`minikube`** (Minikube) | Update script uses `minikube … kubectl`; no standalone `kubectl` required. |
| **`curl`** | Used to query GitHub `releases/latest` and to download release tarballs when you opt into the release path. |
| **`jq` or `python3`** | Needed when resolving manifests from GitHub (API JSON and tarball URL). |

Optional: set `RECONHAWX_NO_COLOR=1` for plain log output.

## How versions work

- **Manifest / app version** is recorded in the cluster as ConfigMap **`reconhawx-version`** (key **`APP_VERSION`**), defined in [`kubernetes/base/config/reconhawx-version.yaml`](../kubernetes/base/config/reconhawx-version.yaml). It is bumped with **`version.txt`** on each release (release-please).
- **Application images** (api, migrations, frontend, event-handler, ct-monitor, and runner/worker images referenced in `service-config`) are pinned to that **same semver** in the rendered manifests via Kustomize—see [`kubernetes/base/components/pinned-releases`](../kubernetes/base/components/pinned-releases/kustomization.yaml).
- Published images on GHCR include tags matching that semver (for example `ghcr.io/.../api:0.7.0`) when CI builds the release.

Check what the cluster is tracking:

```bash
kubectl get configmap reconhawx-version -n reconhawx -o jsonpath='{.data.APP_VERSION}{"\n"}'
```

If that ConfigMap does not exist yet, the cluster predates this mechanism; running an upgrade once will create it.

## Recommended: helper scripts

Run from the **top-level directory of your extracted release** (where `reconhawx-k8s-common.sh` and the update script live).

### Generic Kubernetes

```bash
./update-kubernetes.sh
```

### Minikube

```bash
./update-minikube.sh
```

Default Minikube profile is **`reconhawx`**. Override with:

```bash
MINIKUBE_PROFILE=my-profile ./update-minikube.sh
```

### What the scripts do

1. **Resolve manifests** — Use **`kubernetes/base`** next to the script when that directory exists, or download the **latest GitHub release** source tarball (same logic as install: see flags below).
2. **Print version context** — Manifest **`APP_VERSION`**, GitHub **latest release tag**, and in-cluster **`reconhawx-version`** when present.
3. **Pre-apply hooks** — Run shell scripts in **[`kubernetes/base-update/pre-apply.d/`](../kubernetes/base-update/pre-apply.d/)** (if any) **before** applying manifests. They perform idempotent cluster fixups—for example removing a workload replaced by a different controller kind. Authors: see [`kubernetes/base-update/pre-apply.d/README.md`](../kubernetes/base-update/pre-apply.d/README.md).
4. **Apply** — `kubectl apply -k` on **[`kubernetes/base-update/`](../kubernetes/base-update/kustomization.yaml)** (not full `kubernetes/base/`). The **update** overlay applies the same workloads and config as `base` but **omits** `jwt-secret` and `postgres-secret` from the bundle so applying an **unpacked release** does **not** overwrite live database or signing secrets with example files. It includes **[`kubernetes/base/kueue/core`](../kubernetes/base/kueue/core/kustomization.yaml)** (flavors, local queues, RBAC) but **not** the **ClusterQueue** manifests under [`kubernetes/base/kueue/cluster-queues/`](../kubernetes/base/kueue/cluster-queues/kustomization.yaml), so upgrades **do not reset** cluster-sized `nominalQuota` values. To recompute quotas after scaling nodes, run **`RECONHAWX_KUEUE_RESYNC_QUOTAS=1 ./update-kubernetes.sh`** (or **`update-minikube.sh`**) from a directory that contains [`reconhawx-kueue-quota-sync.py`](../reconhawx-kueue-quota-sync.py), or invoke that script manually.
5. **Roll out** — `kubectl rollout restart` for **api**, **frontend**, **event-handler**, and **ct-monitor**, then wait for rollouts to finish.

Restarting **api** creates a new Pod: the **`run-migrations`** init container runs again with the **migrations** image for the target release, then the API container starts. If migrations fail, the API Pod will not become Ready until the issue is fixed—see [Database migrations (automated)](install-on-kubernetes.md#database-migrations-automated).

### Flags and environment

| Input | Meaning |
|--------|---------|
| **`--from-release`** | Always use the latest published release tarball for manifests, even if you have a local `kubernetes/base`. |
| **`RECONHAWX_FROM_RELEASE`** | `1` = force release tarball; `0` = force local `kubernetes/base`; **unset** = use the directory next to the script when `kubernetes/base` exists, otherwise download release. |
| **`RECONHAWX_GITHUB_REPO`** | `owner/repo` for releases API and tarball (default `ReconHawx/reconhawx`). Use your fork if images and releases live there. |
| **`RECONHAWX_NS`** | Namespace (default `reconhawx`). |
| **`RECONHAWX_KUEUE_RESYNC_QUOTAS`** | Set to **`1`** to run [`reconhawx-kueue-quota-sync.py`](../reconhawx-kueue-quota-sync.py) after a successful apply (needs **`python3`**). |

Script help:

```bash
./update-kubernetes.sh --help
./update-minikube.sh --help
```

## Manual upgrade (without scripts)

Equivalent high-level steps:

1. Obtain an unpacked release whose **`kubernetes/base`** matches the version you want (download the **Source code** archive for that release from GitHub and extract it).
2. Run **pre-apply hooks** (if present) in lexicographic order—see [`kubernetes/base-update/pre-apply.d/README.md`](../kubernetes/base-update/pre-apply.d/README.md).
3. Apply the safe overlay (does not re-apply Secret manifests from the bundle):

   ```bash
   kubectl apply -k kubernetes/base-update/
   ```

4. Restart workloads and wait:

   ```bash
   kubectl rollout restart deploy/api deploy/frontend deploy/event-handler deploy/ct-monitor -n reconhawx
   kubectl rollout status deploy/api -n reconhawx --timeout=10m
   # … repeat for other deployments as needed
   ```

You still need **`curl` / GitHub** only if you choose to fetch a tarball yourself; the scripts automate that path (including pre-apply hooks).

## Why `base-update` instead of `base`?

[`kubernetes/base/`](../kubernetes/base/kustomization.yaml) includes Secret manifests under **`kubernetes/base/secrets/`**. Those files ship as **examples** in the release tree. Running `kubectl apply -k kubernetes/base/` from a **fresh** unpacked release can **replace** cluster Secrets and break login or database access.

[`kubernetes/base-update/`](../kubernetes/base-update/kustomization.yaml) applies the same ConfigMaps, Deployments, RBAC, Kueue flavors/local queues/RBAC, etc., but **does not** apply those Secret objects. Existing cluster Secrets are left unchanged. **ClusterQueue** objects are also **not** part of the update bundle (see step 4 above), so their quotas stay as last set by install or [`reconhawx-kueue-quota-sync.py`](../reconhawx-kueue-quota-sync.py).

If you intentionally need to rotate Secrets from files, do that with a controlled process (e.g. `kubectl apply` specific Secret YAMLs you generated securely), not by blindly applying full `base` from an unmodified release extract.

## Troubleshooting

**Apply fails (webhook, timeout)**  
The script retries a few times. Ingress admission webhooks sometimes need a short wait—see messages in the installer docs. Confirm context: `kubectl config current-context`.

**API stuck / CrashLoop after upgrade**  
Inspect migration logs:

```bash
kubectl logs -n reconhawx deploy/api -c run-migrations
kubectl describe pod -n reconhawx -l app=api
```

**Image pull errors**  
Tags are semver pins (e.g. `:0.7.0`). Ensure the release was built and pushed for that version (GitHub Actions after release-please). For a fork, set **`RECONHAWX_GITHUB_REPO`** and ensure your registry paths in manifests match what you push.

**Wrong cluster / namespace**  
Set `KUBECONFIG` and context; use `RECONHAWX_NS` if you deploy to a non-default namespace (advanced).

## Related documentation

- [Installation on Kubernetes](install-on-kubernetes.md) — first-time install.
- [Installation on Minikube](install-on-minikube.md) — Minikube install.
- [Uninstalling ReconHawx](uninstall-reconhawx.md) — remove from cluster or Minikube.
- [`kubernetes/README.md`](../kubernetes/README.md) — base layout, images, Kueue overview.
- [`AGENTS.md`](../AGENTS.md) — repo map and operational pointers.
