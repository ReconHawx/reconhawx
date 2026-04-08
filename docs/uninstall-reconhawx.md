# Uninstalling ReconHawx

This guide removes ReconHawx from a **Kubernetes cluster** (including a cluster created by **Minikube**) after a normal install.

For first-time install, see **[`docs/install-on-kubernetes.md`](install-on-kubernetes.md)** or **[`docs/install-on-minikube.md`](install-on-minikube.md)**.

## Kubernetes cluster (recommended)

From the **top-level directory of your extracted release** (where **`uninstall-kubernetes.sh`** lives), with the same kubeconfig context you used for install:

```shell
./uninstall-kubernetes.sh
```

**Only the script** (script from `main`; pin a tag or SHA in the URL for reproducible teardown):

```shell
curl -fsSL https://raw.githubusercontent.com/ReconHawx/reconhawx/main/uninstall-kubernetes.sh | bash
```

Piping into `bash` uses stdin for the script, so prompts are read from your **terminal** (`/dev/tty`). For headless use, save the script and run it with `bash`, or use process substitution as in the install docs.

### What you will be asked

1. **Shared infrastructure** — If **Kueue**, **ingress-nginx**, or **MetalLB** (`metallb-system`) look like they were installed for this setup, the script asks **once per component** whether to remove them after ReconHawx. Choose **no** if other workloads on the cluster still need them.
2. **Namespace** — You type **`reconhawx`** to confirm deleting the **`reconhawx`** namespace and ReconHawx-scoped resources.
3. **Optional cleanup** — You may be offered removal of **`reconhawx.runner`** / **`reconhawx.worker`** node labels if you no longer need them.

Remove **`reconhawx.local`** from **`/etc/hosts`** yourself if you added it during install.

### Overrides (optional)

If your install used non-default URLs or versions, set the same variables the installer respected:

- **`INGRESS_NGINX_DEPLOY_URL`** — Ingress controller manifest URL (must match what you installed) if you remove ingress-nginx.
- **`KUEUE_VERSION`**, and optionally **`KUEUE_MANIFESTS_URL`** / **`KUEUE_VISIBILITY_URL`** — If your Kueue install differed from the default release.

## Minikube-only shortcut

If this Minikube **profile exists only for ReconHawx**, you can delete the whole cluster:

```shell
minikube delete -p reconhawx
```

(Use the profile name you chose at install; default is often `reconhawx`.)

If the profile runs **other** workloads, use **`./uninstall-kubernetes.sh`** with `kubectl` pointed at that profile instead (for example `minikube -p my-profile kubectl` as your `kubectl` wrapper, or the kubeconfig Minikube prints), so you only remove ReconHawx resources.

## Related documentation

- **[`docs/update-reconhawx.md`](update-reconhawx.md)** — upgrades (not uninstall).
