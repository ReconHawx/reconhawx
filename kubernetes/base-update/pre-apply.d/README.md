# Pre-apply upgrade hooks

Shell hooks in this directory run **automatically** when using **`./update-kubernetes.sh`** or **`./update-minikube.sh`**, immediately **before** `kubectl apply -k kubernetes/base-update/`. They are **not** Kubernetes manifests and are **not** referenced from `kustomization.yaml`.

## Why

`kubectl apply` does not remove resources that were dropped from git. Hooks perform idempotent cluster fixups (for example dropping a legacy `Deployment` before replacing it with a `StatefulSet`).

## Ordering

Run only scripts matching `[0-9]*.sh` in **lexicographic** order (`10-…`, then `20-…`).

## Environment (set by the update scripts)

| Variable | Meaning |
|----------|---------|
| `RECONHAWX_NS` | Namespace (default `reconhawx`). |
| `RECONHAWX_CLUSTER_VERSION` | `reconhawx-version` ConfigMap `APP_VERSION` if present; otherwise **empty** (cluster predates that mechanism). |
| `RECONHAWX_BUNDLE_VERSION` | Semver from the manifest bundle being applied (`APP_VERSION` in `kubernetes/base/config/reconhawx-version.yaml`). |
| `RECONHAWX_PRE_APPLY_LIB` | Path to a generated shell snippet defining **`reconhawx_kubectl`** (wraps `kubectl` vs `minikube … kubectl --`). Hooks should `source` it when set. |

## `reconhawx_kubectl`

After sourcing `RECONHAWX_PRE_APPLY_LIB`, call `reconhawx_kubectl get …` instead of raw `kubectl`. The wrapper adds `-n "$RECONHAWX_NS"`. If you run hooks **manually** without the dispatcher, define:

```bash
reconhawx_kubectl() { kubectl -n "${RECONHAWX_NS:?}" "$@"; }
```

(or prefix with `minikube -p PROFILE kubectl --` as appropriate).

## Semver-gated hooks

Use plain `x.y.z` strings (no `v` prefix), matching `APP_VERSION`. Example: run only when the cluster version is **strictly before** `0.10.0`:

```bash
if [[ -n "${RECONHAWX_CLUSTER_VERSION:-}" ]]; then
  low="$(printf '%s\n' "$RECONHAWX_CLUSTER_VERSION" "0.10.0" | sort -V | head -1)"
  [[ "$low" == "$RECONHAWX_CLUSTER_VERSION" && "$RECONHAWX_CLUSTER_VERSION" != "0.10.0" ]] || exit 0
fi
```

If `RECONHAWX_CLUSTER_VERSION` is empty, decide per hook whether to treat the cluster as “unknown old” (run) or skip.

## Manual upgrades

If you apply manifests without the update scripts, run hooks **in order** before `kubectl apply -k kubernetes/base-update/`, with `RECONHAWX_NS` and (when needed for gating) `RECONHAWX_CLUSTER_VERSION` / `RECONHAWX_BUNDLE_VERSION` exported. Example:

```bash
export RECONHAWX_NS=reconhawx
export RECONHAWX_CLUSTER_VERSION="$(kubectl get configmap reconhawx-version -n reconhawx -o jsonpath='{.data.APP_VERSION}' 2>/dev/null || true)"
export RECONHAWX_BUNDLE_VERSION="0.9.0"   # from the bundle you are about to apply
for h in kubernetes/base-update/pre-apply.d/[0-9]*.sh; do [[ -f "$h" ]] && bash "$h"; done
```
