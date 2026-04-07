#!/usr/bin/env bash
#
# Remove ReconHawx from a Kubernetes cluster (see docs/install-on-kubernetes.md).
# Deletes namespace reconhawx and cluster-scoped Kueue objects defined in kubernetes/base/kueue.
# Optionally removes kueue-system, ingress-nginx, and metallb-system if you confirm (shared cluster).
#
# Set RECONHAWX_NO_COLOR=1 to disable ANSI styling.
#
set -euo pipefail

RECONHAWX_NS="${RECONHAWX_NS:-reconhawx}"
KUEUE_VERSION="${KUEUE_VERSION:-v0.11.1}"
KUEUE_MANIFESTS_URL="${KUEUE_MANIFESTS_URL:-https://github.com/kubernetes-sigs/kueue/releases/download/${KUEUE_VERSION}/manifests.yaml}"
KUEUE_VISIBILITY_URL="${KUEUE_VISIBILITY_URL:-https://github.com/kubernetes-sigs/kueue/releases/download/${KUEUE_VERSION}/visibility-apf.yaml}"

# Same default as install-kubernetes.sh (cloud / static provider manifest).
INGRESS_NGINX_DEPLOY_URL="${INGRESS_NGINX_DEPLOY_URL:-https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.14.2/deploy/static/provider/cloud/deploy.yaml}"

# Names must match kubernetes/base/kueue/core/* and cluster-queues/* (ClusterQueue and ResourceFlavor).
KUEUE_CLUSTER_QUEUES=(
  runner-cluster-queue
  worker-cluster-queue
  ai-analysis-cluster-queue
)
KUEUE_RESOURCE_FLAVORS=(
  runner-flavor
  worker-flavor
)

# ANSI colors align with [data-theme="dark"] in src/frontend/src/index.css (--bs-primary, --bs-info, --bs-secondary, --bs-text-muted).
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

_UI_BOX_INNER=64

_ui_box_top() {
  local clr="$1" z="$2" i
  printf '%s┌' "$clr"
  for ((i = 0; i < _UI_BOX_INNER; i++)); do printf '─'; done
  printf '┐%s\n' "$z"
}

_ui_box_bot() {
  local clr="$1" z="$2" i
  printf '%s└' "$clr"
  for ((i = 0; i < _UI_BOX_INNER; i++)); do printf '─'; done
  printf '┘%s\n' "$z"
}

_ui_box_mid() {
  printf '%s│%s  %-*s  %s│%s\n' "$1" "$2" 60 "$3" "$1" "$4"
}

ui_banner() {
  _ui_box_top "$_C" "$_Z"
  _ui_box_mid "$_C" "$_B" "ReconHawx - Kubernetes cluster uninstall" "$_Z"
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

# Pass the full command (e.g. tool_stream kubectl delete …). Same pattern as install-minikube.sh tool_stream.
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

require_cmd() {
  command -v "$1" &>/dev/null || die "missing required command: $1"
}

# curl … | bash: stdin is the script; prompts must read from /dev/tty.
read_uninstaller() {
  if [[ -t 0 ]]; then
    read "$@" || die "Unexpected end of input"
  elif [[ -r /dev/tty ]]; then
    read "$@" </dev/tty || die "Cannot read prompts (try: bash <(curl -fsSL URL) or curl … -o uninstall-kubernetes.sh && bash uninstall-kubernetes.sh)"
  else
    die "No TTY for prompts. Save the script and run: bash uninstall-kubernetes.sh"
  fi
}

kubectl_cluster_ok() {
  kubectl cluster-info &>/dev/null || die "kubectl cannot reach the cluster (check KUBECONFIG and context)"
}

ns_exists() {
  kubectl get namespace "$1" &>/dev/null
}

confirm_reconhawx_removal() {
  local confirm
  ui_note "This will delete namespace ${RECONHAWX_NS} and ReconHawx Kueue cluster resources (${KUEUE_CLUSTER_QUEUES[*]} / ${KUEUE_RESOURCE_FLAVORS[*]})."
  read_uninstaller -r -p "$(printf '%sinstaller · %s' "$_B" "Type ${RECONHAWX_NS} to confirm: ")" confirm
  [[ "$confirm" == "$RECONHAWX_NS" ]] || die "Aborted."
}

delete_reconhawx_workloads_and_jobs() {
  if ! ns_exists "$RECONHAWX_NS"; then
    ui_note "Namespace ${RECONHAWX_NS} is not present; skipping workload and namespace deletion."
    return 1
  fi
  ui_step "Deleting Kueue Workloads and Jobs in ${RECONHAWX_NS}"
  if kubectl get crd workloads.kueue.x-k8s.io &>/dev/null; then
    tool_stream kubectl delete workload --all -n "$RECONHAWX_NS" --ignore-not-found --wait=true --timeout=5m || true
  else
    ui_note "Kueue Workload CRD not found; skipping Kueue workload objects."
  fi
  tool_stream kubectl delete job --all -n "$RECONHAWX_NS" --ignore-not-found --wait=true --timeout=5m || true
  ui_ok "Workloads and Jobs cleared (or none were present)"
}

delete_reconhawx_namespace() {
  if ! ns_exists "$RECONHAWX_NS"; then
    return 0
  fi
  ui_step "Deleting namespace ${RECONHAWX_NS}"
  tool_stream kubectl delete namespace "$RECONHAWX_NS" --wait=true --timeout=15m
  ui_ok "Namespace ${RECONHAWX_NS} is gone"
}

delete_cluster_kueue_reconhawx() {
  local cq rf
  if ! kubectl get crd clusterqueues.kueue.x-k8s.io &>/dev/null; then
    ui_note "Kueue ClusterQueue CRD not found; skipping ClusterQueue / ResourceFlavor cleanup."
    return 0
  fi
  ui_step "Deleting cluster-scoped Kueue ClusterQueues (ReconHawx defaults)"
  for cq in "${KUEUE_CLUSTER_QUEUES[@]}"; do
    tool_stream kubectl delete clusterqueue "$cq" --ignore-not-found --wait=true --timeout=5m || true
  done
  ui_ok "ClusterQueues removed (or were absent)"

  if kubectl get crd resourceflavors.kueue.x-k8s.io &>/dev/null; then
    ui_step "Deleting cluster-scoped Kueue ResourceFlavors (ReconHawx defaults)"
    for rf in "${KUEUE_RESOURCE_FLAVORS[@]}"; do
      tool_stream kubectl delete resourceflavor "$rf" --ignore-not-found --wait=true --timeout=5m || true
    done
    ui_ok "ResourceFlavors removed (or were absent)"
  fi
}

# Remove all custom resources for CRDs in group kueue.x-k8s.io (do not delete CRDs yet).
delete_all_kueue_custom_resources() {
  local crd name plural scope
  if ! kubectl get crd -o jsonpath='{range .items[?(@.spec.group=="kueue.x-k8s.io")]}{.metadata.name}{"\n"}{end}' 2>/dev/null | grep -q .; then
    return 0
  fi
  ui_step "Deleting all Kueue API objects (all namespaces / cluster-scoped)"
  while read -r crd; do
    [[ -z "$crd" ]] && continue
    name="${crd##*/}"
    plural="$(kubectl get crd "$name" -o jsonpath='{.spec.names.plural}' 2>/dev/null || true)"
    scope="$(kubectl get crd "$name" -o jsonpath='{.spec.scope}' 2>/dev/null || true)"
    [[ -n "$plural" ]] || continue
    if [[ "$scope" == "Cluster" ]]; then
      tool_stream kubectl delete "$plural" --all --ignore-not-found --wait=false 2>/dev/null || true
    else
      # --all-namespaces alone does not delete; kubectl then errors "no name was specified".
      tool_stream kubectl delete "$plural" --all -A --ignore-not-found --wait=false 2>/dev/null || true
    fi
  done < <(kubectl get crd -o name 2>/dev/null | grep '\.kueue\.x-k8s\.io$' || true)
}

# Delete visibility aggregation layer (often leaves APIService stuck and blocks namespace teardown).
delete_kueue_visibility_apiservice() {
  tool_stream kubectl delete apiservice v1beta1.visibility.kueue.x-k8s.io --ignore-not-found
}

# Apply the same release manifests as install, in delete order (visibility first, then main bundle).
delete_kueue_release_manifests() {
  ui_step "Removing Kueue install from release manifests (${KUEUE_VERSION})"
  tool_stream kubectl delete --ignore-not-found -f "$KUEUE_VISIBILITY_URL" || true
  tool_stream kubectl delete --ignore-not-found -f "$KUEUE_MANIFESTS_URL" || true
}

# CRDs often remain after namespace delete; remove any *.kueue.x-k8s.io CRDs left.
delete_kueue_crds() {
  local crd
  ui_step "Deleting leftover Kueue CRDs"
  while read -r crd; do
    [[ -z "$crd" ]] && continue
    tool_stream kubectl delete "$crd" --wait=false 2>/dev/null || true
  done < <(kubectl get crd -o name 2>/dev/null | grep '\.kueue\.x-k8s\.io$' || true)
}

# If namespace is stuck in Terminating, clear finalizers via /finalize (needs jq).
unstick_namespace_finalizers() {
  local ns="$1"
  if ! kubectl get ns "$ns" &>/dev/null; then
    return 0
  fi
  ui_note "Clearing finalizers on namespace ${ns} (if stuck in Terminating) …"
  if command -v jq &>/dev/null; then
    kubectl get ns "$ns" -o json | jq '.spec.finalizers = []' | kubectl replace --raw "/api/v1/namespaces/${ns}/finalize" -f - 2>/dev/null || true
  else
    ui_note "Install jq to auto-clear namespace finalizers, or run: kubectl get ns $ns -o json | jq '.spec.finalizers = []' | kubectl replace --raw \"/api/v1/namespaces/$ns/finalize\" -f -"
  fi
}

# Full Kueue teardown: frees webhooks, CRs, controller, CRDs — not only kueue-system.
uninstall_kueue_completely() {
  ui_note "This removes the Kueue controller, webhooks, ${KUEUE_VERSION} release resources, and all kueue.x-k8s.io CRDs. Other teams must not use Kueue on this cluster."

  delete_all_kueue_custom_resources
  sleep 3
  delete_kueue_visibility_apiservice
  delete_kueue_release_manifests

  ui_step "Deleting namespace kueue-system"
  tool_stream kubectl delete namespace kueue-system --ignore-not-found --wait=false 2>/dev/null || true
  sleep 5
  unstick_namespace_finalizers kueue-system

  sleep 3
  delete_kueue_crds

  if kubectl get crd -o name 2>/dev/null | grep -q '\.kueue\.x-k8s\.io$'; then
    ui_note "Some Kueue CRDs remain; waiting and retrying delete …"
    sleep 5
    delete_kueue_crds
  fi

  if ns_exists kueue-system 2>/dev/null; then
    unstick_namespace_finalizers kueue-system
  fi

  if ns_exists kueue-system; then
    ui_note "Namespace kueue-system still exists; you may need to remove finalizers on remaining objects or run kubectl get ns kueue-system -o yaml"
  else
    ui_ok "Kueue uninstalled"
  fi
}

# Admission webhooks outlive the controller and block Ingress / namespace deletion.
delete_ingress_nginx_webhooks() {
  local r
  ui_step "Removing ingress-nginx Validating/MutatingWebhookConfigurations"
  while read -r r; do
    [[ -z "$r" ]] && continue
    tool_stream kubectl delete "$r" --wait=false --ignore-not-found 2>/dev/null || true
  done < <(kubectl get validatingwebhookconfiguration -o name 2>/dev/null | grep -iE 'ingress-nginx|nginx-ingress' || true)
  while read -r r; do
    [[ -z "$r" ]] && continue
    tool_stream kubectl delete "$r" --wait=false --ignore-not-found 2>/dev/null || true
  done < <(kubectl get mutatingwebhookconfiguration -o name 2>/dev/null | grep -iE 'ingress-nginx|nginx-ingress' || true)
}

delete_cluster_scoped_grep() {
  local kind="$1"
  local pattern="$2"
  local r
  while read -r r; do
    [[ -z "$r" ]] && continue
    tool_stream kubectl delete "$r" --wait=false --ignore-not-found 2>/dev/null || true
  done < <(kubectl get "$kind" -o name 2>/dev/null | grep -E "$pattern" || true)
}

# Match install-kubernetes.sh: cloud deploy manifest + webhook teardown (namespace-only delete often hangs).
uninstall_ingress_nginx_completely() {
  delete_ingress_nginx_webhooks
  sleep 2

  ui_step "Deleting ingress-nginx resources from release manifest"
  tool_stream kubectl delete --ignore-not-found -f "$INGRESS_NGINX_DEPLOY_URL" || true
  sleep 3

  tool_stream kubectl delete ingressclass nginx --wait=false --ignore-not-found 2>/dev/null || true

  tool_stream kubectl delete crd ingressclassparams.networking.k8s.io --wait=false --ignore-not-found 2>/dev/null || true

  delete_cluster_scoped_grep clusterrole 'ingress-nginx'
  delete_cluster_scoped_grep clusterrolebinding 'ingress-nginx'
  delete_cluster_scoped_grep clusterrole 'nginx-ingress'
  delete_cluster_scoped_grep clusterrolebinding 'nginx-ingress'

  ui_step "Deleting namespace ingress-nginx (non-blocking, then finalize if needed)"
  tool_stream kubectl delete namespace ingress-nginx --ignore-not-found --wait=false 2>/dev/null || true
  sleep 5
  unstick_namespace_finalizers ingress-nginx

  if ns_exists ingress-nginx; then
    delete_ingress_nginx_webhooks
    unstick_namespace_finalizers ingress-nginx
    ui_note "Namespace ingress-nginx may still be terminating; inspect: kubectl get ns ingress-nginx -o yaml"
  else
    ui_ok "ingress-nginx controller namespace removed"
  fi
}

ingress_nginx_present() {
  ns_exists ingress-nginx && return 0
  kubectl get validatingwebhookconfiguration -o name 2>/dev/null | grep -qiE 'ingress-nginx|nginx-ingress' && return 0
  kubectl get mutatingwebhookconfiguration -o name 2>/dev/null | grep -qiE 'ingress-nginx|nginx-ingress' && return 0
  kubectl get ingressclass nginx &>/dev/null && return 0
  return 1
}

kueue_present() {
  ns_exists kueue-system && return 0
  kubectl get crd -o name 2>/dev/null | grep -q '\.kueue\.x-k8s\.io$'
}

metallb_present() {
  ns_exists metallb-system
}

# Sets globals: PREFLIGHT_UNINSTALL_KUEUE_FULL, PREFLIGHT_UNINSTALL_INGRESS_NGINX, PREFLIGHT_UNINSTALL_METALLB (0 or 1).
preflight_optional_shared_components() {
  local have_k have_i have_m ans
  have_k=0
  kueue_present && have_k=1
  have_i=0
  ingress_nginx_present && have_i=1
  have_m=0
  metallb_present && have_m=1

  printf '\n'
  _ui_box_top "$_Y" "$_Z"
  _ui_box_mid "$_Y" "$_B" "Pre-flight: optional cluster components" "$_Z"
  _ui_box_bot "$_Y" "$_Z"
  ui_note "Decide now whether to remove shared infrastructure after ReconHawx is torn down. You will not be prompted again."

  printf '\n'
  ui_step "Detected installations"
  if [[ "$have_k" -eq 1 ]]; then
    ui_note "Kueue: yes (namespace kueue-system and/or *.kueue.x-k8s.io CRDs)"
  else
    ui_note "Kueue: not detected"
  fi
  if [[ "$have_i" -eq 1 ]]; then
    ui_note "ingress-nginx: yes (namespace / webhooks / IngressClass nginx)"
  else
    ui_note "ingress-nginx: not detected"
  fi
  if [[ "$have_m" -eq 1 ]]; then
    ui_note "MetalLB: yes (namespace metallb-system)"
  else
    ui_note "MetalLB: not detected"
  fi

  PREFLIGHT_UNINSTALL_KUEUE_FULL=0
  PREFLIGHT_UNINSTALL_INGRESS_NGINX=0
  PREFLIGHT_UNINSTALL_METALLB=0

  printf '\n'
  ui_step "Uninstall choices (only for components detected above)"

  if [[ "$have_k" -eq 1 ]]; then
    ui_note "Full Kueue removal: controller, visibility APIService, release ${KUEUE_VERSION}, all *.kueue.x-k8s.io CRDs. Unsafe if other teams use Kueue."
    read_uninstaller -r -p "$(printf '%suninstaller · %s' "$_B" "Uninstall Kueue completely after ReconHawx? [y/N] ")" ans
    case "$ans" in
    y | Y | yes | YES | Yes) PREFLIGHT_UNINSTALL_KUEUE_FULL=1 ;;
    *) ui_note "Keeping Kueue controller (ReconHawx ClusterQueues/ResourceFlavors will still be removed)." ;;
    esac
  else
    ui_note "Skipping Kueue uninstall prompt (not installed)."
  fi

  printf '\n'
  if [[ "$have_i" -eq 1 ]]; then
    ui_note "Full ingress-nginx removal: webhooks, manifest ${INGRESS_NGINX_DEPLOY_URL}, namespace. Other ingress classes may differ."
    read_uninstaller -r -p "$(printf '%suninstaller · %s' "$_B" "Uninstall ingress-nginx completely after ReconHawx? [y/N] ")" ans
    case "$ans" in
    y | Y | yes | YES | Yes) PREFLIGHT_UNINSTALL_INGRESS_NGINX=1 ;;
    *) ui_note "Keeping ingress-nginx." ;;
    esac
  else
    ui_note "Skipping ingress-nginx uninstall prompt (not detected)."
  fi

  printf '\n'
  if [[ "$have_m" -eq 1 ]]; then
    ui_note "Removes MetalLB; other LoadBalancer Services using it will stop working."
    read_uninstaller -r -p "$(printf '%suninstaller · %s' "$_B" "Delete namespace metallb-system after ReconHawx? [y/N] ")" ans
    case "$ans" in
    y | Y | yes | YES | Yes) PREFLIGHT_UNINSTALL_METALLB=1 ;;
    *) ui_note "Keeping MetalLB." ;;
    esac
  else
    ui_note "Skipping MetalLB prompt (namespace metallb-system not present)."
  fi

  printf '\n'
  ui_step "Summary — optional teardown"
  ui_note "Kueue full uninstall: $([[ "${PREFLIGHT_UNINSTALL_KUEUE_FULL}" -eq 1 ]] && echo yes || echo no)"
  ui_note "ingress-nginx full uninstall: $([[ "${PREFLIGHT_UNINSTALL_INGRESS_NGINX}" -eq 1 ]] && echo yes || echo no)"
  ui_note "MetalLB namespace delete: $([[ "${PREFLIGHT_UNINSTALL_METALLB}" -eq 1 ]] && echo yes || echo no)"
}

run_preflight_kueue_uninstall() {
  if [[ "${PREFLIGHT_UNINSTALL_KUEUE_FULL:-0}" -ne 1 ]]; then
    return 0
  fi
  if kueue_present; then
    uninstall_kueue_completely
  else
    ui_note "Kueue no longer present; skipping full Kueue uninstall."
  fi
}

run_preflight_ingress_uninstall() {
  if [[ "${PREFLIGHT_UNINSTALL_INGRESS_NGINX:-0}" -ne 1 ]]; then
    return 0
  fi
  if ingress_nginx_present; then
    uninstall_ingress_nginx_completely
  else
    ui_note "ingress-nginx no longer present; skipping ingress uninstall."
  fi
}

run_preflight_metallb_uninstall() {
  if [[ "${PREFLIGHT_UNINSTALL_METALLB:-0}" -ne 1 ]]; then
    return 0
  fi
  if ! metallb_present; then
    ui_note "Namespace metallb-system already gone; skipping MetalLB delete."
    return 0
  fi
  ui_step "Deleting namespace metallb-system (from pre-flight choice)"
  tool_stream kubectl delete namespace metallb-system --wait=true --timeout=15m
  ui_ok "Namespace metallb-system deleted"
}

prompt_remove_node_labels() {
  local ans n
  read_uninstaller -r -p "$(printf '%suninstaller · %s' "$_B" "Remove reconhawx.runner and reconhawx.worker labels from all nodes? [y/N] ")" ans
  case "$ans" in
  y | Y | yes | YES | Yes)
    ui_step "Removing ReconHawx node labels"
    for n in $(kubectl get nodes -o jsonpath='{.items[*].metadata.name}'); do
      kubectl label node "$n" reconhawx.runner- reconhawx.worker- 2>/dev/null || true
    done
    ui_ok "Node labels cleared (if they were set)"
    ;;
  *)
    ui_note "Leaving node labels unchanged."
    ;;
  esac
}

main() {
  require_cmd kubectl
  kubectl_cluster_ok

  if [[ -n "${KUBECONFIG:-}" ]]; then
    ui_note "Using KUBECONFIG=${KUBECONFIG}"
  fi

  ui_banner

  preflight_optional_shared_components

  ui_note "Cluster-scoped resources use the names from kubernetes/base/kueue. If you renamed them, delete leftovers manually."
  confirm_reconhawx_removal

  delete_reconhawx_workloads_and_jobs || true
  delete_reconhawx_namespace || true
  delete_cluster_kueue_reconhawx

  printf '\n'
  _ui_box_top "$_Y" "$_Z"
  _ui_box_mid "$_Y" "$_B" "Optional: shared cluster components (pre-flight choices)" "$_Z"
  _ui_box_bot "$_Y" "$_Z"

  run_preflight_kueue_uninstall
  run_preflight_ingress_uninstall
  run_preflight_metallb_uninstall

  prompt_remove_node_labels

  printf '\n'
  _ui_box_top "$_G" "$_Z"
  _ui_box_mid "$_G" "$_B" "Uninstall steps complete" "$_Z"
  _ui_box_bot "$_G" "$_Z"
  ui_note "Remove /etc/hosts entries for reconhawx.local manually if you no longer need them."
}

main "$@"
