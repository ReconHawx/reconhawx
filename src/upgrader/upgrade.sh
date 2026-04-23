#!/usr/bin/env bash
# In-cluster upgrade entrypoint: mirrors update-kubernetes.sh (release tarball path).
set -euo pipefail

UPGRADER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$UPGRADER_ROOT"

die() {
  printf 'upgrader: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" &>/dev/null || die "missing required command: $1"
}

ui_step() { printf '▶ %s\n' "$*"; }
ui_ok() { printf '  ✓ %s\n' "$*"; }
ui_note() { printf '  %s\n' "$*" >&2; }

read_installer() {
  die "read_installer invoked unexpectedly in upgrader"
}

# shellcheck source=/dev/null
source "${UPGRADER_ROOT}/reconhawx-k8s-common.sh"

require_cmd kubectl
require_cmd curl
require_cmd tar
require_cmd jq

: "${RECONHAWX_NS:?RECONHAWX_NS is required}"
: "${RECONHAWX_VERSION:?RECONHAWX_VERSION is required}"

# In-cluster: after `unset KUBECONFIG`, kubectl still loads ~/.kube/config if present; Alpine's kubectl
# package often ships a default cluster at http://localhost:8080, which breaks discovery (memcache)
# while some direct /api/v1 GETs can still succeed. Force a kubeconfig that only points at this pod's apiserver.
reconhawx_write_in_cluster_kubeconfig() {
  local out="$1"
  [[ -n "${KUBERNETES_SERVICE_HOST:-}" ]] || die "missing KUBERNETES_SERVICE_HOST (not running inside a Kubernetes pod?)"
  [[ -n "${KUBERNETES_SERVICE_PORT:-}" ]] || die "missing KUBERNETES_SERVICE_PORT"
  local tls server host="${KUBERNETES_SERVICE_HOST}"
  if [[ "$host" == *:* && "$host" != \[*\]* ]]; then
    server="https://[${host}]:${KUBERNETES_SERVICE_PORT}"
  else
    server="https://${host}:${KUBERNETES_SERVICE_PORT}"
  fi
  if [[ -r /var/run/secrets/kubernetes.io/serviceaccount/ca.crt ]]; then
    tls="certificate-authority: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
  else
    tls="insecure-skip-tls-verify: true"
  fi
  cat >"$out" <<EOF
apiVersion: v1
kind: Config
clusters:
- cluster:
    ${tls}
    server: ${server}
  name: reconhawx-in-cluster
contexts:
- context:
    cluster: reconhawx-in-cluster
    user: reconhawx-in-cluster
  name: reconhawx-in-cluster
current-context: reconhawx-in-cluster
users:
- name: reconhawx-in-cluster
  user:
    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
EOF
}

if [[ -r /var/run/secrets/kubernetes.io/serviceaccount/token ]]; then
  unset -v KUBECONFIG 2>/dev/null || unset KUBECONFIG || true
  _rh_kcfg="$(mktemp "${TMPDIR:-/tmp}/reconhawx-incluster-kubeconfig.XXXXXX")"
  trap 'rm -f "${_rh_kcfg:-}"' EXIT
  reconhawx_write_in_cluster_kubeconfig "$_rh_kcfg"
  export KUBECONFIG="$_rh_kcfg"
fi

RECONHAWX_GITHUB_REPO="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"

# Do not use `kubectl cluster-info` / `kubectl get nodes` here: the upgrader Job runs as
# upgrader-sa with namespaced RBAC only (no cluster node/list or discovery parity with a human kube-admin).
kubectl_cluster_ok() {
  local err rc=0
  # List deployments.apps (same RBAC as get). Avoid probing only deploy/api: NotFound (404) when the
  # api workload was renamed or is not a Deployment looks like an auth/connectivity failure if stderr is hidden.
  err="$(kubectl -n "$RECONHAWX_NS" get --request-timeout=15s deployments.apps -o name 2>&1)" || rc=$?
  if [[ "$rc" -ne 0 ]]; then
    die "kubectl preflight failed in namespace ${RECONHAWX_NS}: ${err}"
  fi
}

# Download and extract a GitHub release tarball into RECONHAWX_SOURCE_TREE_ROOT / BASE_SRC.
_reconhawx_extract_tarball_to_base() {
  local tarpath="$1"
  RECONHAWX_RELEASE_TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/reconhawx-release.XXXXXX")"
  tar -xzf "$tarpath" -C "${RECONHAWX_RELEASE_TMPDIR}" || die "failed to extract tarball"
  rm -f "$tarpath"

  local -a dirs=()
  shopt -s nullglob
  for d in "${RECONHAWX_RELEASE_TMPDIR}"/*/; do
    dirs+=("$d")
  done
  shopt -u nullglob
  ((${#dirs[@]} == 1)) || die "expected one top-level directory in tarball, found ${#dirs[@]}"

  local root="${dirs[0]%/}"
  local base="$root/kubernetes/base"
  [[ -d "$base" ]] || die "kubernetes/base missing in tree: $root"
  BASE_SRC="$base"
  RECONHAWX_INSTALL_FROM_RELEASE=1
  RECONHAWX_SOURCE_TREE_ROOT="$root"
  ui_ok "Release tree at ${root}"
}

reconhawx_download_release_by_semver() {
  local ver="$1"
  local repo="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"
  local tag="${ver#v}"
  tag="v${tag}"
  local api="https://api.github.com/repos/${repo}/releases/tags/${tag}"
  ui_step "Fetching release tarball (${tag})"
  local json url tarpath
  json="$(curl -sSf \
    -H 'Accept: application/vnd.github+json' \
    -H 'User-Agent: reconhawx-upgrader' \
    "$api")" || die "curl failed: ${api}"
  url="$(reconhawx_json_tarball_url_from_api "$json")"
  tarpath="$(mktemp "${TMPDIR:-/tmp}/reconhawx-src.XXXXXX.tar.gz")"
  curl -sSfL "$url" -o "$tarpath" || die "failed to download release tarball"
  _reconhawx_extract_tarball_to_base "$tarpath"
}

reconhawx_download_staged_tarball() {
  local base="${API_INTERNAL_URL:?}"
  local tok="${PULL_TOKEN:?}"
  ui_step "Fetching staged upgrade tarball from API"
  local tarpath
  tarpath="$(mktemp "${TMPDIR:-/tmp}/reconhawx-staged.XXXXXX.tar.gz")"
  curl -sSfL \
    -H "Authorization: Bearer ${INTERNAL_SERVICE_API_KEY:-}" \
    -G --data-urlencode "token=${tok}" \
    "${base%/}/internal/upgrade/pull" \
    -o "$tarpath" || die "failed to download staged tarball"
  _reconhawx_extract_tarball_to_base "$tarpath"
}

resolve_manifests() {
  if [[ -n "${PULL_TOKEN:-}" ]]; then
    reconhawx_download_staged_tarball
  elif [[ "${RECONHAWX_VERSION}" == "latest" ]]; then
    reconhawx_download_release_kubernetes_base_set_BASE_SRC
  else
    reconhawx_download_release_by_semver "${RECONHAWX_VERSION}"
  fi
}

tool_stream() {
  "$@"
}

main() {
  ui_step "ReconHawx in-cluster upgrade"
  resolve_manifests

  local tree_root bundle_ver cluster_ver
  tree_root="${RECONHAWX_SOURCE_TREE_ROOT:-}"
  bundle_ver="$(reconhawx_manifest_bundle_version "$tree_root")"
  ui_note "Bundle APP_VERSION: ${bundle_ver:-unknown}"

  set +e
  cluster_ver="$(kubectl get configmap reconhawx-version -n "$RECONHAWX_NS" -o jsonpath='{.data.APP_VERSION}' 2>/dev/null)"
  set -e
  if [[ -n "${cluster_ver// /}" ]]; then
    ui_note "Cluster reconhawx-version: ${cluster_ver}"
  else
    ui_note "No reconhawx-version ConfigMap yet"
  fi

  local base_up
  base_up="$(reconhawx_base_update_dir "$BASE_SRC")"

  kubectl_cluster_ok

  reconhawx_sync_frontend_ingress_manifest_from_cluster "$BASE_SRC" "$RECONHAWX_NS" kubectl

  ui_step "Pre-apply hooks"
  reconhawx_run_base_update_pre_apply_hooks "$BASE_SRC" "$RECONHAWX_NS" "${cluster_ver:-}" "${bundle_ver:-}" kubectl

  local _attempt _max=6
  for _attempt in $(seq 1 "$_max"); do
    ui_step "kubectl apply -k base-update (attempt ${_attempt}/${_max})"
    if tool_stream kubectl apply -k "$base_up"; then
      ui_ok "Manifests applied"
      break
    fi
    if [[ "$_attempt" -eq "$_max" ]]; then
      die "kubectl apply -k failed after ${_max} attempts"
    fi
    ui_note "Apply failed; waiting 15s …"
    sleep 15
  done

  if [[ "${RECONHAWX_KUEUE_RESYNC_QUOTAS:-0}" == "1" ]]; then
    ui_step "Kueue quota sync"
    python3 "${UPGRADER_ROOT}/reconhawx-kueue-quota-sync.py" kubectl || die "quota sync failed"
  fi

  ui_step "Rollout restart"
  kubectl rollout restart deploy/api deploy/frontend deploy/event-handler deploy/ct-monitor -n "$RECONHAWX_NS"

  ui_step "Waiting for rollouts"
  kubectl rollout status deploy/api -n "$RECONHAWX_NS" --timeout=10m
  kubectl rollout status deploy/frontend -n "$RECONHAWX_NS" --timeout=5m
  kubectl rollout status deploy/event-handler -n "$RECONHAWX_NS" --timeout=5m
  kubectl rollout status deploy/ct-monitor -n "$RECONHAWX_NS" --timeout=5m
  ui_ok "Upgrade complete"

  if [[ "${RECONHAWX_OBSERVABILITY:-0}" == "1" ]]; then
    require_cmd helm
    # shellcheck source=/dev/null
    source "${UPGRADER_ROOT}/reconhawx-observability-helm.sh"
    reconhawx_observability_helm_apply strict
  fi
}

main "$@"
