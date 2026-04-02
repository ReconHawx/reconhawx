#!/usr/bin/env bash
#
# Upgrade an existing ReconHawx Kubernetes install to the latest (or local) manifests.
#
# Applies kubernetes/base-update/ so jwt/postgres Secrets in the repo are NOT reapplied
# (avoids overwriting cluster credentials on a fresh clone).
#
# Then restarts API, frontend, event-handler, and ct-monitor so new image tags roll out
# (API init re-runs migrations for the new migrations image).
#
# Manifest source: same as install-kubernetes.sh (local kubernetes/base vs GitHub release tarball).
# See also: RECONHAWX_FROM_RELEASE, RECONHAWX_GITHUB_REPO, --from-release.
#
# Requires kubectl and a working kubeconfig. Sources reconhawx-k8s-common.sh at the repo root
# (run from a git clone or use a full release tarball directory).
#
# Set RECONHAWX_NO_COLOR=1 to disable ANSI styling.
set -eo pipefail

RECONHAWX_NS="${RECONHAWX_NS:-reconhawx}"
RUN_TOOL_LONG_HEAD_LINES="${RUN_TOOL_LONG_HEAD_LINES:-10}"
RUN_TOOL_LONG_FAIL_TAIL_LINES="${RUN_TOOL_LONG_FAIL_TAIL_LINES:-25}"
RECONHAWX_GITHUB_REPO="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"
RECONHAWX_RELEASE_TMPDIR=""

_install_script_path="${BASH_SOURCE[0]-}"
if [[ -n "$_install_script_path" ]]; then
  SCRIPT_DIR="$(cd "$(dirname -- "${_install_script_path}")" && pwd)"
else
  SCRIPT_DIR="$(cd -- "${PWD:-.}" && pwd)"
fi
if [[ "$SCRIPT_DIR" == */scripts ]]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  REPO_ROOT="$SCRIPT_DIR"
fi
BASE_SRC="$REPO_ROOT/kubernetes/base"

set -u

_COMMON="$REPO_ROOT/reconhawx-k8s-common.sh"
[[ -f "$_COMMON" ]] || {
  printf 'reconhawx update: missing %s\n' "$_COMMON" >&2
  printf 'Run from the repository root (clone or extracted release) alongside update-kubernetes.sh.\n' >&2
  exit 1
}
# shellcheck source=/dev/null
source "$_COMMON"

if [[ -t 1 ]] && [[ -z "${RECONHAWX_NO_COLOR:-}" ]]; then
  _B=$'\e[1m'
  _D=$'\e[2m\e[38;2;142;173;191m'
  _C=$'\e[38;2;0;242;255m'
  _G=$'\e[38;2;51;240;255m'
  _R=$'\e[31m'
  _Y=$'\e[38;2;176;38;255m'
  _Z=$'\e[0m'
else
  _B= _D= _C= _G= _R= _Y= _Z=
fi

die() {
  printf '%s✗ %s%s\n' "$_R" "$*" "$_Z" >&2
  exit 1
}

_ui_box_inner=64
_ui_box_top() {
  local clr="$1" z="$2" i
  printf '%s┌' "$clr"
  for ((i = 0; i < _ui_box_inner; i++)); do printf '─'; done
  printf '┐%s\n' "$z"
}
_ui_box_bot() {
  local clr="$1" z="$2" i
  printf '%s└' "$clr"
  for ((i = 0; i < _ui_box_inner; i++)); do printf '─'; done
  printf '┘%s\n' "$z"
}
_ui_box_mid() {
  printf '%s│%s  %-*s  %s│%s\n' "$1" "$2" 60 "$3" "$1" "$4"
}

ui_banner() {
  _ui_box_top "$_C" "$_Z"
  _ui_box_mid "$_C" "$_B" "ReconHawx - Kubernetes upgrade" "$_Z"
  _ui_box_bot "$_C" "$_Z"
  printf '\n'
}

ui_step() {
  printf '\n%s▶ %s%s%s\n' "$_B$_C" "$_Z$_B" "$*" "$_Z"
}

ui_ok() {
  printf '%s  %s✓ %s%s\n' "$_D" "$_G" "$*" "$_Z"
}

ui_note() {
  printf '%s  %s%s\n' "$_D" "$*" "$_Z"
}

tool_stream() {
  if [[ -t 1 ]]; then
    "$@" 2>&1 | while IFS= read -r line || [[ -n "${line:-}" ]]; do
      printf '%s%s│%s %s\n' "$_D" "$_Y" "$_Z" "$line"
    done
    return "${PIPESTATUS[0]}"
  else
    "$@"
  fi
}

_format_tool_log_lines() {
  while IFS= read -r line || [[ -n "${line:-}" ]]; do
    printf '%s%s│%s %s\n' "$_D" "$_Y" "$_Z" "$line"
  done
}

run_tool_long() {
  local title=$1
  shift
  ui_step "$title"
  local log _ec lines
  log="$(mktemp)"
  set +e
  "$@" >"$log" 2>&1
  _ec=$?
  set -e
  lines=$(wc -l <"$log" | tr -d ' ')
  if [[ "$_ec" -eq 0 ]]; then
    if [[ ! -t 1 ]]; then
      cat "$log"
    elif [[ "$lines" -le "$RUN_TOOL_LONG_HEAD_LINES" ]]; then
      _format_tool_log_lines <"$log"
    else
      ui_note "Showing first ${RUN_TOOL_LONG_HEAD_LINES} of ${lines} output lines."
      head -n "$RUN_TOOL_LONG_HEAD_LINES" "$log" | _format_tool_log_lines
    fi
  else
    if [[ ! -t 1 ]]; then
      cat "$log" >&2
    else
      printf '%s  %sCommand failed (exit %s). Last %s lines:%s\n' "$_D" "$_R" "$_ec" "$RUN_TOOL_LONG_FAIL_TAIL_LINES" "$_Z"
      tail -n "$RUN_TOOL_LONG_FAIL_TAIL_LINES" "$log" | _format_tool_log_lines
    fi
  fi
  rm -f "$log"
  if [[ "$_ec" -ne 0 ]]; then
    die "Step failed (exit ${_ec}): $*"
  fi
  ui_ok "Finished"
}

require_cmd() {
  command -v "$1" &>/dev/null || die "missing required command: $1"
}

usage() {
  cat <<'EOF'
Usage: update-kubernetes.sh [options]

  --from-release    Use the latest GitHub release tarball for manifests (same semantics as install).

  -h, --help        Show this help.

Environment:
  RECONHAWX_FROM_RELEASE   unset = auto (local kubernetes/base if present, else release).
  RECONHAWX_GITHUB_REPO    owner/repo (default: ReconHawx/reconhawx).
  RECONHAWX_NS             Namespace (default: reconhawx).

Inspect deployed manifest version:
  kubectl get configmap reconhawx-version -n reconhawx -o jsonpath='{.data.APP_VERSION}{"\n"}'
EOF
}

kubectl_cluster_ok() {
  kubectl cluster-info &>/dev/null || die "kubectl cannot reach the cluster (check KUBECONFIG and context)"
  kubectl get nodes &>/dev/null || die "kubectl get nodes failed"
}

FORCE_FROM_RELEASE_ARG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-release)
      FORCE_FROM_RELEASE_ARG=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1 (try --help)"
      ;;
  esac
done

main() {
  require_cmd kubectl
  require_cmd curl

  ui_banner

  reconhawx_resolve_kubernetes_base_src

  local tree_root bundle_ver latest_ver cluster_ver
  tree_root="${RECONHAWX_SOURCE_TREE_ROOT:-$REPO_ROOT}"
  bundle_ver="$(reconhawx_manifest_bundle_version "$tree_root")"
  latest_ver="$(reconhawx_latest_release_version_from_github "$(reconhawx_latest_release_json "$RECONHAWX_GITHUB_REPO")")"

  ui_step "Version check"
  ui_note "Manifest bundle APP_VERSION (this tree): ${bundle_ver:-unknown}"
  ui_note "GitHub latest release: ${latest_ver}"
  set +e
  cluster_ver="$(kubectl get configmap reconhawx-version -n "$RECONHAWX_NS" -o jsonpath='{.data.APP_VERSION}' 2>/dev/null)"
  set -e
  if [[ -n "${cluster_ver// /}" ]]; then
    ui_note "Cluster reports reconhawx-version ConfigMap: ${cluster_ver}"
  else
    ui_note "Cluster has no reconhawx-version ConfigMap yet (upgrade tracking starts after this release)."
  fi

  local base_up
  base_up="$(reconhawx_base_update_dir "$BASE_SRC")"

  kubectl_cluster_ok
  if [[ -n "${KUBECONFIG:-}" ]]; then
    ui_note "Using KUBECONFIG=${KUBECONFIG}"
  fi

  local _attempt _max=6
  for _attempt in $(seq 1 "$_max"); do
    ui_step "Kubernetes: apply upgrade bundle (attempt ${_attempt}/${_max})"
    if tool_stream kubectl apply -k "$base_up"; then
      ui_ok "Manifests applied"
      break
    fi
    if [[ "$_attempt" -eq "$_max" ]]; then
      die "kubectl apply -k failed after ${_max} attempts"
    fi
    ui_note "Apply failed; waiting 15s (ingress/webhook flakiness) …"
    sleep 15
  done

  run_tool_long "Kubernetes: restart app deployments (pull new images if needed)" \
    kubectl rollout restart deploy/api deploy/frontend deploy/event-handler deploy/ct-monitor -n "$RECONHAWX_NS"

  ui_step "Kubernetes: waiting for rollouts"
  tool_stream kubectl rollout status deploy/api -n "$RECONHAWX_NS" --timeout=10m
  tool_stream kubectl rollout status deploy/frontend -n "$RECONHAWX_NS" --timeout=5m
  tool_stream kubectl rollout status deploy/event-handler -n "$RECONHAWX_NS" --timeout=5m
  tool_stream kubectl rollout status deploy/ct-monitor -n "$RECONHAWX_NS" --timeout=5m
  ui_ok "Rollouts complete"

  printf '\n'
  _ui_box_top "$_G" "$_Z"
  _ui_box_mid "$_G" "$_B" "Upgrade complete" "$_Z"
  _ui_box_bot "$_G" "$_Z"
  ui_note "Inspect deployed manifest version: kubectl get configmap reconhawx-version -n ${RECONHAWX_NS} -o jsonpath='{.data.APP_VERSION}'"
  if [[ "${RECONHAWX_INSTALL_FROM_RELEASE:-0}" -eq 1 ]] && [[ -n "${RECONHAWX_SOURCE_TREE_ROOT:-}" ]]; then
    ui_note "Release source tree left at ${RECONHAWX_SOURCE_TREE_ROOT}"
  fi
}

main
