#!/usr/bin/env bash
#
# reconhawx-observability-helm.sh — Helm apply for Loki, Grafana Alloy, Grafana (standalone).
#
# Sourced by install/update scripts and the in-cluster upgrader. Callers must define:
#   die() require_cmd() ui_step() ui_ok() ui_note()
# Optional: run_tool_long() — if unset, helm/kubectl run directly.
#
# Environment:
#   RECONHAWX_OBSERVABILITY   unset / 1 / yes / true = attempt install (skip quietly if helm or tree missing).
#                             0 / false / no = skip.
#   RECONHAWX_OBSERVABILITY_ROOT  Optional override for repo root (must contain kubernetes/observability).
#   RECONHAWX_SOURCE_TREE_ROOT    Checked after override (release extract / repo).
#   REPO_ROOT                     Checked last (git clone / cwd layout).
#
# shellcheck shell=bash

reconhawx_observability_resolve_dir() {
  local -a candidates=()
  local d obs
  [[ -n "${RECONHAWX_OBSERVABILITY_ROOT:-}" ]] && candidates+=("${RECONHAWX_OBSERVABILITY_ROOT}")
  [[ -n "${RECONHAWX_SOURCE_TREE_ROOT:-}" ]] && candidates+=("${RECONHAWX_SOURCE_TREE_ROOT}")
  [[ -n "${REPO_ROOT:-}" ]] && candidates+=("${REPO_ROOT}")
  for d in "${candidates[@]}"; do
    [[ -z "$d" ]] && continue
    obs="${d%/}/kubernetes/observability"
    if [[ -d "$obs" && -f "$obs/values-loki.yaml" && -f "$obs/values-grafana.yaml" ]]; then
      printf '%s' "$obs"
      return 0
    fi
  done
  return 1
}

reconhawx__stream_or_run() {
  if declare -F tool_stream &>/dev/null; then
    tool_stream "$@"
  else
    "$@"
  fi
}

reconhawx__helm_run() {
  if declare -F run_tool_long &>/dev/null; then
    run_tool_long "$1" "${@:2}"
  else
    ui_step "$1"
    "${@:2}" || die "${1} failed"
    ui_ok "Finished"
  fi
}

reconhawx__helm_release_exists() {
  local release="$1"
  helm status "$release" -n monitoring &>/dev/null
}

# Namespace manifest lives under kubernetes/base/ (kustomize load restrictor); optional legacy path in observability/.
reconhawx_observability_namespace_manifest() {
  local obs_dir="$1"
  if [[ -f "${obs_dir}/namespace.yaml" ]]; then
    printf '%s' "${obs_dir}/namespace.yaml"
    return 0
  fi
  local base_ns
  base_ns="$(cd "${obs_dir}/.." && pwd)/base/monitoring-namespace.yaml"
  if [[ -f "$base_ns" ]]; then
    printf '%s' "$base_ns"
    return 0
  fi
  return 1
}

# Optional first argument: word "strict" — fail if helm or observability dir is missing (in-cluster Job).
reconhawx_observability_helm_apply() {
  local strict="${1:-}"
  local ob="${RECONHAWX_OBSERVABILITY-}"
  case "${ob,,}" in
    0 | false | no)
      ui_note "RECONHAWX_OBSERVABILITY disabled; skipping observability Helm stack."
      return 0
      ;;
  esac

  if ! command -v helm &>/dev/null; then
    if [[ "$strict" == "strict" ]]; then
      die "helm is required for RECONHAWX_OBSERVABILITY=1 (in-cluster observability upgrade)"
    fi
    ui_note "helm not found; skipping observability stack (install Helm v3 or set RECONHAWX_OBSERVABILITY=0)."
    return 0
  fi
  require_cmd kubectl

  local obs_dir
  if ! obs_dir="$(reconhawx_observability_resolve_dir)"; then
    if [[ "$strict" == "strict" ]]; then
      die "kubernetes/observability not found in release tree (RECONHAWX_OBSERVABILITY=1)"
    fi
    ui_note "kubernetes/observability not found in source tree; skipping observability Helm stack."
    return 0
  fi

  ui_step "Observability: Helm repos (grafana)"
  helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
  if declare -F run_tool_long &>/dev/null; then
    run_tool_long "Observability: helm repo update" helm repo update
  else
    ui_step "Observability: helm repo update"
    helm repo update || die "helm repo update failed"
    ui_ok "Finished"
  fi
  ui_ok "Helm repos ready"

  ui_step "Observability: namespace monitoring"
  local _ns_manifest
  _ns_manifest="$(reconhawx_observability_namespace_manifest "$obs_dir")" || die "monitoring Namespace manifest not found (expected kubernetes/base/monitoring-namespace.yaml)"
  reconhawx__stream_or_run kubectl apply -f "$_ns_manifest"
  ui_ok "Namespace applied"

  reconhawx__helm_run "Observability: Helm upgrade — loki" \
    helm upgrade --install loki grafana/loki -n monitoring -f "${obs_dir}/values-loki.yaml"

  reconhawx__helm_run "Observability: Helm upgrade — alloy" \
    helm upgrade --install alloy grafana/alloy -n monitoring \
      -f "${obs_dir}/values-alloy.yaml" \
      --set-file "alloy.configMap.content=${obs_dir}/alloy-config.river"

  if reconhawx__helm_release_exists kps; then
    ui_note "Observability: legacy Helm release kps (kube-prometheus-stack) is still installed. Uninstall it before standalone Grafana (same Service name kps-grafana): helm uninstall kps -n monitoring — see kubernetes/observability/README.md (Migrating from kube-prometheus-stack)."
  fi

  if reconhawx__helm_release_exists grafana; then
    reconhawx__helm_run "Observability: Helm upgrade — grafana" \
      helm upgrade --install grafana grafana/grafana -n monitoring \
        -f "${obs_dir}/values-grafana.yaml"
  else
    require_cmd openssl
    local gpw pwf
    gpw="$(openssl rand -base64 24)"
    pwf="$(mktemp "${TMPDIR:-/tmp}/rh-grafana-pw.XXXXXX")"
    printf '%s' "$gpw" >"$pwf"
    chmod 600 "$pwf" || true
    ui_note "Grafana (release grafana, Service kps-grafana): initial admin password — save this value: ${gpw}"
    reconhawx__helm_run "Observability: Helm install — grafana" \
      helm upgrade --install grafana grafana/grafana -n monitoring \
        -f "${obs_dir}/values-grafana.yaml" \
        --set-file "adminPassword=${pwf}"
    rm -f "$pwf"
  fi

  local _dash_k="${obs_dir}/dashboards"
  if [[ -f "${_dash_k}/kustomization.yaml" ]]; then
    ui_step "Observability: Grafana dashboards (ConfigMaps)"
    reconhawx__stream_or_run kubectl apply -k "$_dash_k"
    ui_ok "Dashboard ConfigMaps applied (sidecar loads into Grafana)"
  fi

  ui_ok "Observability Helm stack applied (monitoring namespace)"
}
