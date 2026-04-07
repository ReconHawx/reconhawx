#!/usr/bin/env bash
#
# Upgrade ReconHawx on Minikube (same manifest strategy as update-kubernetes.sh).
# Uses minikube kubectl; profile defaults to reconhawx (override with MINIKUBE_PROFILE).
#
# Set RECONHAWX_NO_COLOR=1 to disable ANSI styling.
set -eo pipefail

RECONHAWX_NS="${RECONHAWX_NS:-reconhawx}"
MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-reconhawx}"
RUN_TOOL_LONG_HEAD_LINES="${RUN_TOOL_LONG_HEAD_LINES:-10}"
RUN_TOOL_LONG_FAIL_TAIL_LINES="${RUN_TOOL_LONG_FAIL_TAIL_LINES:-25}"
RECONHAWX_GITHUB_REPO="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"

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
  printf 'reconhawx update: missing %s (run from repository root)\n' "$_COMMON" >&2
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
  _ui_box_mid "$_C" "$_B" "ReconHawx - Minikube upgrade" "$_Z"
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
  printf '%s  %s%s\n' "$_D" "$*" "$_Z" >&2
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

read_installer() {
  if [[ -t 0 ]]; then
    read "$@" || die "Unexpected end of input"
  elif [[ -r /dev/tty ]]; then
    read "$@" </dev/tty || die "Cannot read prompts (try saving this script and running bash update-minikube.sh)"
  else
    die "No TTY for prompts. Save the script and run: bash update-minikube.sh"
  fi
}

usage() {
  cat <<EOF
Usage: update-minikube.sh [options]

  --from-release    Use the latest GitHub release tarball for manifests.

  -h, --help        Show this help.

Environment:
  MINIKUBE_PROFILE         minikube profile (default: reconhawx)
  RECONHAWX_FROM_RELEASE   unset = auto (local kubernetes/base if present, else release).
  RECONHAWX_GITHUB_REPO    owner/repo (default: ReconHawx/reconhawx).
  RECONHAWX_NS             Namespace (default: reconhawx).
  INSTALL_STAGING_DIR      Git clones only: copied manifests before apply (default: /tmp/reconhawx); removed after success.
  RECONHAWX_KUEUE_RESYNC_QUOTAS  Set to 1 to re-run reconhawx-kueue-quota-sync.py after apply (e.g. after adding nodes).
EOF
}

mk() {
  minikube -p "$MINIKUBE_PROFILE" kubectl -- "$@"
}

minikube_cluster_ok() {
  mk cluster-info &>/dev/null || die "minikube kubectl cannot reach the cluster (profile ${MINIKUBE_PROFILE})"
  mk get nodes &>/dev/null || die "minikube kubectl get nodes failed"
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
  require_cmd minikube
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
  cluster_ver="$(mk get configmap reconhawx-version -n "$RECONHAWX_NS" -o jsonpath='{.data.APP_VERSION}' 2>/dev/null)"
  set -e
  if [[ -n "${cluster_ver// /}" ]]; then
    ui_note "Cluster reports reconhawx-version ConfigMap: ${cluster_ver}"
  else
    ui_note "Cluster has no reconhawx-version ConfigMap yet (upgrade tracking starts after this release)."
  fi

  local upgrade_staged=0 upgrade_stage_root=""
  if [[ "${RECONHAWX_INSTALL_FROM_RELEASE:-0}" -eq 0 ]] && [[ -e "$REPO_ROOT/.git" ]]; then
    upgrade_stage_root="${INSTALL_STAGING_DIR:-/tmp/reconhawx}"
    BASE_SRC="$(reconhawx_stage_kubernetes_upgrade_manifests "$REPO_ROOT" "$upgrade_stage_root")"
    upgrade_staged=1
  fi

  local base_up
  base_up="$(reconhawx_base_update_dir "$BASE_SRC")"

  minikube_cluster_ok
  ui_note "Using minikube profile ${MINIKUBE_PROFILE}"

  reconhawx_sync_frontend_ingress_manifest_from_cluster "$BASE_SRC" "$RECONHAWX_NS" minikube -p "$MINIKUBE_PROFILE" kubectl --

  ui_step "Kubernetes: pre-apply hooks (if any)"
  reconhawx_run_base_update_pre_apply_hooks "$BASE_SRC" "$RECONHAWX_NS" "${cluster_ver:-}" "${bundle_ver:-}" minikube -p "$MINIKUBE_PROFILE" kubectl --

  local _attempt _max=6
  for _attempt in $(seq 1 "$_max"); do
    ui_step "Kubernetes: apply upgrade bundle (attempt ${_attempt}/${_max})"
    if tool_stream mk apply -k "$base_up"; then
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
    require_cmd python3
    local _qsync="${tree_root}/reconhawx-kueue-quota-sync.py"
    [[ -f "$_qsync" ]] || die "missing ${_qsync} (run from repo root or release tree with reconhawx-kueue-quota-sync.py)"
    run_tool_long "Kubernetes: re-sync Kueue ClusterQueue quotas (RECONHAWX_KUEUE_RESYNC_QUOTAS=1)" \
      python3 "$_qsync" minikube -p "$MINIKUBE_PROFILE" kubectl --
  fi

  run_tool_long "Kubernetes: restart app deployments" \
    mk rollout restart deploy/api deploy/frontend deploy/event-handler deploy/ct-monitor -n "$RECONHAWX_NS"

  ui_step "Kubernetes: waiting for rollouts"
  tool_stream mk rollout status deploy/api -n "$RECONHAWX_NS" --timeout=10m
  tool_stream mk rollout status deploy/frontend -n "$RECONHAWX_NS" --timeout=5m
  tool_stream mk rollout status deploy/event-handler -n "$RECONHAWX_NS" --timeout=5m
  tool_stream mk rollout status deploy/ct-monitor -n "$RECONHAWX_NS" --timeout=5m
  ui_ok "Rollouts complete"

  printf '\n'
  _ui_box_top "$_G" "$_Z"
  _ui_box_mid "$_G" "$_B" "Upgrade complete" "$_Z"
  _ui_box_bot "$_G" "$_Z"
  ui_note "Inspect deployed manifest version: minikube -p ${MINIKUBE_PROFILE} kubectl -- get configmap reconhawx-version -n ${RECONHAWX_NS} -o jsonpath='{.data.APP_VERSION}'"
  if [[ "$upgrade_staged" -eq 1 ]]; then
    reconhawx_update_staging_cleanup_on_success "$upgrade_stage_root"
  fi
}

main
