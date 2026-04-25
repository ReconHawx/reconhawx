# Upgrader image

One-shot Kubernetes **Job** image that applies `kubernetes/base-update/`, restarts app Deployments, then runs the observability Helm stack (same as [`reconhawx-observability-helm.sh`](../../reconhawx-observability-helm.sh) in **strict** mode), matching [`update-kubernetes.sh`](../../update-kubernetes.sh).

## Environment (Job pod)

| Variable | Required | Meaning |
|----------|----------|---------|
| `RECONHAWX_NS` | yes | Namespace (e.g. `reconhawx`). |
| `RECONHAWX_VERSION` | yes | `latest`, or semver `x.y.z` (GitHub release tag `vx.y.z`). |
| `RECONHAWX_GITHUB_REPO` | no | `owner/repo` (default `ReconHawx/reconhawx`). |
| `PULL_TOKEN` | no | If set with `API_INTERNAL_URL`, pull staged tarball from API `/internal/upgrade/pull` (air-gapped). |
| `API_INTERNAL_URL` | with `PULL_TOKEN` | Base URL of API (e.g. `http://api:8000`). |
| `INTERNAL_SERVICE_API_KEY` | with `PULL_TOKEN` | Bearer for internal pull. |
| `RECONHAWX_KUEUE_RESYNC_QUOTAS` | no | Set to `1` to run `reconhawx-kueue-quota-sync.py` after apply. |
| `RECONHAWX_OBSERVABILITY` | no | The API sets `1` for diagnostics; `upgrade.sh` always runs Helm after rollouts regardless. |

## Build

From repo root:

```bash
chmod +x src/upgrader/build.sh
cd src/upgrader && ./build.sh ghcr.io/yourorg/reconhawx linux/amd64 0.20.0
```

`build.sh` copies `reconhawx-k8s-common.sh` and `reconhawx-kueue-quota-sync.py` from the repository root into this directory before `docker build`.
