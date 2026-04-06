#!/usr/bin/env bash
#
# Install ReconHawx on a Kubernetes cluster (see docs/install-on-kubernetes.md).
# Requires kubectl and a working kubeconfig (e.g. KUBECONFIG or ~/.kube/config).
#
# Manifests: uses kubernetes/base next to this script when present, otherwise
# downloads the latest GitHub release source tarball (see --from-release / RECONHAWX_FROM_RELEASE).
# Release tarball (downloaded or unpacked next to this script without .git): kubernetes/base in place.
# Git clone: copies kubernetes/base to INSTALL_STAGING_DIR (default /tmp/reconhawx) so secrets are not written in the repo.
#
# Set RECONHAWX_NO_COLOR=1 to disable ANSI styling.
#
# -u deferred: piped installs (curl … | bash) may not set BASH_SOURCE[0], which would trip nounset.
set -eo pipefail

RUN_TOOL_LONG_HEAD_LINES="${RUN_TOOL_LONG_HEAD_LINES:-10}"
RUN_TOOL_LONG_FAIL_TAIL_LINES="${RUN_TOOL_LONG_FAIL_TAIL_LINES:-25}"
KUEUE_VERSION="${KUEUE_VERSION:-v0.11.1}"
INGRESS_NGINX_DEPLOY_URL="${INGRESS_NGINX_DEPLOY_URL:-https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.14.2/deploy/static/provider/cloud/deploy.yaml}"
METALLB_MANIFEST_URL="${METALLB_MANIFEST_URL:-https://raw.githubusercontent.com/metallb/metallb/v0.15.3/config/manifests/metallb-native.yaml}"
INGRESS_HOST="${INGRESS_HOST:-reconhawx.local}"
# RECONHAWX_FROM_RELEASE: unset = auto (local kubernetes/base if present, else tarball); 0 = local only; 1 = tarball only.
RECONHAWX_GITHUB_REPO="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"
RECONHAWX_RELEASE_TMPDIR=""

# 1 = use RECONHAWX_SOURCE_TREE_ROOT/kubernetes/base in place (no staging); 0 = stage copy under INSTALL_STAGING_DIR (git clone).
RECONHAWX_INSTALL_FROM_RELEASE=0
# Repository root: extracted release dir, REPO_ROOT for in-place unpack, or REPO_ROOT when staging.
RECONHAWX_SOURCE_TREE_ROOT=""

# Git clones only: copy kubernetes/base here (deleted after a successful install).
INSTALL_STAGING_DIR="${INSTALL_STAGING_DIR:-/tmp/reconhawx}"

# Stdin / pipe: BASH_SOURCE[0] may be unset or empty — fall back to $PWD (release tarball mode will apply).
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
  _ui_box_mid "$_C" "$_B" "ReconHawx - Kubernetes cluster installation" "$_Z"
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

# Run the given command (e.g. kubectl …) with optional log gutter on TTY. Pass the full argv (do not wrap kubectl twice).
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
      printf '%s  %sCommand failed (exit %s). Lines that often indicate the cause:%s\n' "$_D" "$_R" "$_ec" "$_Z"
      local _err_hits
      _err_hits="$(grep -nEi 'error|fatal|fail(ed|ure)?|denied|refused|invalid|not[[:space:]]+found|timeout|internal[[:space:]]+error' "$log" 2>/dev/null | head -40 || true)"
      if [[ -n "$_err_hits" ]]; then
        printf '%s\n' "$_err_hits" | _format_tool_log_lines
      else
        ui_note "(No lines matched common error patterns.)"
      fi
      printf '%s  %sLast %s lines:%s\n' "$_D" "$_Y" "$RUN_TOOL_LONG_FAIL_TAIL_LINES" "$_Z"
      tail -n "$RUN_TOOL_LONG_FAIL_TAIL_LINES" "$log" | _format_tool_log_lines
    fi
  fi
  rm -f "$log"
  if [[ "$_ec" -ne 0 ]]; then
    die "Step failed (exit ${_ec}): $*"
  fi
  ui_ok "Finished"
}

b64_encode() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

require_cmd() {
  command -v "$1" &>/dev/null || die "missing required command: $1"
}

# curl … | bash feeds the script on stdin, so prompts must not read from stdin (EOF).
read_installer() {
  if [[ -t 0 ]]; then
    read "$@" || die "Unexpected end of input"
  elif [[ -r /dev/tty ]]; then
    read "$@" </dev/tty || die "Cannot read installer prompts (try: bash <(curl -fsSL URL) or curl … -o install.sh && bash install.sh)"
  else
    die "No TTY for prompts (e.g. CI). Save the script and run: bash install-kubernetes.sh"
  fi
}

install_staging_prepare() {
  if [[ ! -e "$INSTALL_STAGING_DIR" ]]; then
    return 0
  fi
  ui_note "Install staging path ${INSTALL_STAGING_DIR} already exists."
  local ans
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Remove ${INSTALL_STAGING_DIR} and continue? [y/N] ")" ans
  case "$ans" in
  y | Y | yes | YES | Yes)
    rm -rf "$INSTALL_STAGING_DIR"
    ui_ok "Removed ${INSTALL_STAGING_DIR}"
    ;;
  *)
    die "Aborted: remove or rename ${INSTALL_STAGING_DIR} and re-run."
    ;;
  esac
}

install_staging_cleanup_on_success() {
  if [[ -e "$INSTALL_STAGING_DIR" ]]; then
    ui_note "Removing install staging directory ${INSTALL_STAGING_DIR} …"
    rm -rf "$INSTALL_STAGING_DIR"
    ui_ok "Staging directory removed"
  fi
}

usage_install_kubernetes() {
  cat <<'EOF'
Usage: install-kubernetes.sh [options]

  --from-release    Use the latest GitHub release source tarball for kubernetes/base
                    instead of a local copy (also the default when this script is not
                    run from a full repository tree).

  -h, --help        Show this help.

Environment:
  RECONHAWX_FROM_RELEASE   unset = auto; 0 = require local kubernetes/base; 1 = require release tarball.
  RECONHAWX_GITHUB_REPO    owner/repo (default: ReconHawx/reconhawx).
  INSTALL_STAGING_DIR      Git-clone installs only: staging copy (default: /tmp/reconhawx); deleted after success.
  INGRESS_HOST             Frontend URL hostname (default: reconhawx.local); also written to frontend-ingress when not default.

Examples (no git clone):

  curl -fsSL https://raw.githubusercontent.com/ReconHawx/reconhawx/main/install-kubernetes.sh | bash

  # Equivalent; avoids stdin issues in minimal environments:
  bash <(curl -fsSL https://raw.githubusercontent.com/ReconHawx/reconhawx/main/install-kubernetes.sh)
EOF
}

# Parse {"tarball_url": "https://..."}; needs jq or python3.
_json_tarball_url_from_api() {
  local json="$1" url
  if command -v jq &>/dev/null; then
    url="$(printf '%s' "$json" | jq -r .tarball_url)"
  elif command -v python3 &>/dev/null; then
    url="$(printf '%s' "$json" | python3 -c "import json,sys; print(json.load(sys.stdin)['tarball_url'])")"
  else
    die "release download needs jq or python3 to read GitHub API JSON (tarball_url)"
  fi
  if [[ -z "$url" || "$url" == "null" ]]; then
    die "GitHub API did not return tarball_url — is there a published release?"
  fi
  printf '%s' "$url"
}

download_release_kubernetes_base_set_BASE_SRC() {
  require_cmd curl
  require_cmd tar
  local repo api json url tmp tarpath root base
  repo="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"
  api="https://api.github.com/repos/${repo}/releases/latest"

  ui_step "Fetching kubernetes/base from latest GitHub release (${repo})"
  json="$(
    curl -sSf \
      -H 'Accept: application/vnd.github+json' \
      -H 'User-Agent: reconhawx-install-kubernetes' \
      "$api"
  )" || die "curl failed: ${api}"

  url="$(_json_tarball_url_from_api "$json")"

  RECONHAWX_RELEASE_TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/reconhawx-release.XXXXXX")"
  tarpath="${RECONHAWX_RELEASE_TMPDIR}/src.tar.gz"

  curl -sSfL "$url" -o "$tarpath" || die "failed to download release tarball"

  tar -xzf "$tarpath" -C "${RECONHAWX_RELEASE_TMPDIR}" || die "failed to extract release tarball"
  rm -f "$tarpath"

  local -a dirs
  dirs=()
  shopt -s nullglob
  for d in "${RECONHAWX_RELEASE_TMPDIR}"/*/; do
    dirs+=("$d")
  done
  shopt -u nullglob
  ((${#dirs[@]} == 1)) || die "expected one top-level directory in release tarball, found ${#dirs[@]}"

  root="${dirs[0]%/}"
  base="$root/kubernetes/base"
  [[ -d "$base" ]] || die "kubernetes/base missing in release tree: $root"
  BASE_SRC="$base"
  RECONHAWX_INSTALL_FROM_RELEASE=1
  RECONHAWX_SOURCE_TREE_ROOT="$root"
  ui_ok "Release extracted at ${root} (apply uses ${BASE_SRC})."
}

# Uses global BASE_SRC (repo-relative), RECONHAWX_FROM_RELEASE; optional global FORCE_FROM_RELEASE_ARG.
resolve_kubernetes_base_src() {
  local want_release=0 auto_note=0
  if [[ "${FORCE_FROM_RELEASE_ARG:-0}" -eq 1 ]]; then
    want_release=1
  elif [[ "${RECONHAWX_FROM_RELEASE:-}" == "1" ]]; then
    want_release=1
  elif [[ "${RECONHAWX_FROM_RELEASE:-}" == "0" ]]; then
    want_release=0
  elif [[ ! -d "$BASE_SRC" ]]; then
    want_release=1
    auto_note=1
  else
    want_release=0
  fi

  if [[ "$want_release" -eq 1 ]]; then
    if [[ "$auto_note" -eq 1 ]]; then
      ui_note "No local kubernetes/base at ${BASE_SRC}; using latest GitHub release tarball."
    fi
    download_release_kubernetes_base_set_BASE_SRC
  else
    [[ -d "$BASE_SRC" ]] || die "kubernetes/base not found at $BASE_SRC (use --from-release or RECONHAWX_FROM_RELEASE=1)"
    RECONHAWX_SOURCE_TREE_ROOT="$REPO_ROOT"
    if [[ -e "$REPO_ROOT/.git" ]]; then
      RECONHAWX_INSTALL_FROM_RELEASE=0
    else
      RECONHAWX_INSTALL_FROM_RELEASE=1
    fi
  fi
}

kubectl_cluster_ok() {
  kubectl cluster-info &>/dev/null || die "kubectl cannot reach the cluster (check KUBECONFIG and context)"
  kubectl get nodes &>/dev/null || die "kubectl get nodes failed"
}

wait_ingress_nginx_admission_endpoints() {
  local ns=ingress-nginx
  local svc=ingress-nginx-controller-admission
  local deadline=$((SECONDS + 300))
  ui_note "Waiting for ${svc} endpoints (ingress validating webhook) …"
  while ((SECONDS < deadline)); do
    local ips
    ips="$(kubectl get endpoints "$svc" -n "$ns" -o jsonpath='{.subsets[0].addresses[*].ip}' 2>/dev/null || true)"
    if [[ -n "${ips// /}" ]]; then
      ui_note "Admission endpoints are up; short pause for the webhook to listen …"
      sleep 12
      return 0
    fi
    sleep 2
  done
  die "Timed out waiting for ${svc} endpoints. Check: kubectl get ep,po -n ${ns}"
}

ensure_install_prefix() {
  local root="$1"
  if [[ -d "$root" ]] && [[ -w "$root" ]]; then
    return 0
  fi
  local parent
  parent="$(dirname "$root")"
  if [[ -d "$parent" ]] && [[ -w "$parent" ]]; then
    mkdir -p "$root/kubernetes/base" 2>/dev/null && return 0
  fi
  ui_note "Creating install directory with sudo: $root"
  sudo mkdir -p "$root/kubernetes"
  sudo chown -R "$(id -u):$(id -g)" "$root"
}

_dots_escape_host() {
  printf '%s' "$1" | sed 's/\./\\./g'
}

sync_kubernetes_base() {
  local src="$1"
  local dst="$2"
  if command -v rsync &>/dev/null; then
    mkdir -p "$dst"
    rsync -a --delete "$src/" "$dst/"
  else
    rm -rf "$dst"
    mkdir -p "$dst"
    cp -a "$src"/. "$dst"/
  fi
}

write_secrets_from_examples() {
  local base="$1"
  local jwt_plain="$2"
  local refresh_plain="$3"
  local pg_user="$4"
  local pg_pass="$5"

  local jwt_b64 refresh_b64 user_b64 pass_b64
  if [[ -z "$jwt_plain" ]]; then
    jwt_b64="$(b64_encode "$(openssl rand -hex 32)")"
  else
    jwt_b64="$(b64_encode "$jwt_plain")"
  fi
  if [[ -z "$refresh_plain" ]]; then
    refresh_b64="$(b64_encode "$(openssl rand -hex 32)")"
  else
    refresh_b64="$(b64_encode "$refresh_plain")"
  fi
  user_b64="$(b64_encode "$pg_user")"
  pass_b64="$(b64_encode "$pg_pass")"

  local jwt_tmpl="$base/secrets/jwt-secret.yaml.example"
  local pg_tmpl="$base/secrets/postgres-secret.yaml.example"
  [[ -f "$jwt_tmpl" ]] || die "missing $jwt_tmpl"
  [[ -f "$pg_tmpl" ]] || die "missing $pg_tmpl"

  sed \
    -e "s#JWT_SECRET_PLACEHOLDER#${jwt_b64}#g" \
    -e "s#REFRESH_SECRET_KEY_PLACEHOLDER#${refresh_b64}#g" \
    "$jwt_tmpl" >"$base/secrets/jwt-secret.yaml"

  sed \
    -e "s#POSTGRES_USERNAME_PLACEHOLDER#${user_b64}#g" \
    -e "s#POSTGRES_PASSWORD_PLACEHOLDER#${pass_b64}#g" \
    "$pg_tmpl" >"$base/secrets/postgres-secret.yaml"

  ui_ok "Wrote secrets under $base/secrets/ (values not shown)."
}

# Ship host is reconhawx.local; replace only when the installer picks another name.
patch_frontend_ingress_host_if_custom() {
  local base="$1" host="$2" ing otmp
  ing="$base/frontend/frontend-ingress.yaml"
  [[ -f "$ing" ]] || die "missing frontend ingress manifest: $ing"
  if [[ "$host" != "reconhawx.local" ]]; then
    otmp="$(mktemp)"
    awk -v h="$host" '$0 == "  - host: reconhawx.local" { print "  - host: " h; next } { print }' "$ing" >"$otmp"
    mv "$otmp" "$ing"
    ui_note "frontend-ingress: using host ${host}"
  fi
}

hosts_lines_matching_reconhawx_local() {
  local pat
  pat="$(_dots_escape_host "$INGRESS_HOST")"
  grep -nE '(^|[[:space:]])'"${pat}"'([[:space:]]|$)' /etc/hosts 2>/dev/null || true
}

_hosts_ingress_mapping_state() {
  local want_ip="$1"
  local line pat seen_ok=0 seen_bad=0 re
  pat="$(_dots_escape_host "$INGRESS_HOST")"
  re="(^|[[:space:]])${pat}([[:space:]]|$)"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line// /}" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    line="${line%%#*}"
    line="$(printf '%s' "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "${line// /}" ]] && continue
    [[ "$line" =~ $re ]] || continue
    read -r -a fields <<<"$line"
    local lip="${fields[0]}"
    local has_host=0 tok
    for tok in "${fields[@]}"; do
      [[ "$tok" == "$INGRESS_HOST" ]] && has_host=1 && break
    done
    [[ "$has_host" -eq 0 ]] && continue
    if [[ "$lip" == "$want_ip" ]]; then
      seen_ok=1
    else
      seen_bad=1
    fi
  done </etc/hosts

  if [[ "$seen_bad" -eq 1 ]]; then
    printf 'wrong\n'
  elif [[ "$seen_ok" -eq 1 ]]; then
    printf 'ok\n'
  else
    printf 'missing\n'
  fi
}

update_hosts_file() {
  local ip="$1"
  local state
  state="$(_hosts_ingress_mapping_state "$ip")"

  if [[ "$state" == "ok" ]]; then
    ui_ok "/etc/hosts already maps ${INGRESS_HOST} to ${ip}; leaving unchanged."
    return 0
  fi

  if [[ "$state" == "missing" ]]; then
    ui_step "Updating /etc/hosts"
    ui_note "Adding $ip $INGRESS_HOST (sudo)."
    printf '%s %s\n' "$ip" "$INGRESS_HOST" | sudo tee -a /etc/hosts >/dev/null
    ui_ok "/etc/hosts updated"
    return 0
  fi

  ui_note "Existing /etc/hosts entries for ${INGRESS_HOST} use a different address than ${ip}:"
  while IFS= read -r line; do
    printf '%s%s│%s %s\n' "$_D" "$_Y" "$_Z" "$line"
  done < <(hosts_lines_matching_reconhawx_local)
  local ans
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Remove those lines and set ${INGRESS_HOST} to ${ip}? [y/N] ")" ans
  case "$ans" in
  y | Y | yes | YES | Yes)
    local host_pat
    sudo cp /etc/hosts "/etc/hosts.bak.reconhawx.$(date +%Y%m%d%H%M%S)"
    host_pat="$(_dots_escape_host "$INGRESS_HOST")"
    sudo sed -i "\#${host_pat}#d" /etc/hosts
    printf '%s %s\n' "$ip" "$INGRESS_HOST" | sudo tee -a /etc/hosts >/dev/null
    ui_ok "/etc/hosts updated"
    ;;
  *)
    die "Aborted: remove or edit ${INGRESS_HOST} in /etc/hosts, then re-run this step."
    ;;
  esac
}

list_cluster_nodes() {
  mapfile -t CLUSTER_NODES < <(kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
  ((${#CLUSTER_NODES[@]} > 0)) || die "No nodes returned by kubectl get nodes"
}

print_node_menu() {
  local i
  ui_step "Cluster nodes (runner hosts API stack; workers run workflow tasks; a node may be both)"
  printf '\n'
  for i in "${!CLUSTER_NODES[@]}"; do
    printf '%s  %2d) %s%s\n' "$_D" "$((i + 1))" "${CLUSTER_NODES[$i]}" "$_Z"
  done
  printf '\n'
}

# Resolve comma-separated names or 1-based indices into node names. Prints unique names, one per line.
resolve_node_tokens() {
  local input="$1"
  local part idx name found
  local -A seen=()
  IFS=',' read -ra parts <<<"$input"
  for part in "${parts[@]}"; do
    part="${part// /}"
    [[ -z "$part" ]] && continue
    if [[ "$part" =~ ^[0-9]+$ ]]; then
      idx="$part"
      ((idx >= 1 && idx <= ${#CLUSTER_NODES[@]})) || die "Invalid node index: $part (use 1–${#CLUSTER_NODES[@]})"
      name="${CLUSTER_NODES[$((idx - 1))]}"
    else
      found=0
      for n in "${CLUSTER_NODES[@]}"; do
        if [[ "$n" == "$part" ]]; then
          name="$n"
          found=1
          break
        fi
      done
      ((found)) || die "Unknown node name: $part"
    fi
    if [[ -z "${seen[$name]+x}" ]]; then
      seen[$name]=1
      printf '%s\n' "$name"
    fi
  done
}

prompt_node_roles() {
  local r_line w_line
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Runner node(s) — comma-separated names or numbers from the list: ")" r_line
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Worker node(s) — comma-separated names or numbers from the list: ")" w_line
  [[ -n "${r_line// /}" ]] || die "Select at least one runner node."
  [[ -n "${w_line// /}" ]] || die "Select at least one worker node."

  mapfile -t RUNNER_NODES < <(resolve_node_tokens "$r_line")
  mapfile -t WORKER_NODES < <(resolve_node_tokens "$w_line")
  ((${#RUNNER_NODES[@]} > 0)) || die "No runner nodes resolved."
  ((${#WORKER_NODES[@]} > 0)) || die "No worker nodes resolved."
}

apply_node_labels() {
  local n
  for n in "${RUNNER_NODES[@]}"; do
    ui_note "Label runner: $n"
    tool_stream kubectl label node "$n" reconhawx.runner=true --overwrite
  done
  for n in "${WORKER_NODES[@]}"; do
    ui_note "Label worker: $n"
    tool_stream kubectl label node "$n" reconhawx.worker=true --overwrite
  done
  ui_ok "Node labels applied"
}

# Populates RUNNER_NODES / WORKER_NODES with nodes that already have reconhawx.runner=true / reconhawx.worker=true.
collect_reconhawx_node_roles_from_cluster() {
  RUNNER_NODES=()
  WORKER_NODES=()
  local n rv wv
  for n in "${CLUSTER_NODES[@]}"; do
    rv="$(kubectl get node "$n" -o jsonpath='{.metadata.labels.reconhawx\.runner}' 2>/dev/null || true)"
    wv="$(kubectl get node "$n" -o jsonpath='{.metadata.labels.reconhawx\.worker}' 2>/dev/null || true)"
    if [[ "$rv" == "true" ]]; then
      RUNNER_NODES+=("$n")
    fi
    if [[ "$wv" == "true" ]]; then
      WORKER_NODES+=("$n")
    fi
  done
}

cluster_already_has_runner_and_worker_labels() {
  [[ ${#RUNNER_NODES[@]} -gt 0 && ${#WORKER_NODES[@]} -gt 0 ]]
}

discover_or_prompt_ingress_ip() {
  local ip lb
  lb="$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)"
  if [[ -z "$lb" ]]; then
    lb="$(kubectl get svc -n ingress-nginx ingress-nginx-controller -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || true)"
  fi
  if [[ -n "$lb" ]]; then
    ui_note "Ingress Service reports: ${lb}"
    if [[ ! "$lb" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      ui_note "(Hostname is not an /etc/hosts IP; enter a node IP or MetalLB address below.)"
      lb=""
    fi
  fi
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "IP for ${INGRESS_HOST} in /etc/hosts [${lb:-required}]: ")" ip
  ip="${ip:-$lb}"
  [[ -n "$ip" ]] || die "An IP address is required for /etc/hosts (set a node IP where ingress is reachable, or install MetalLB)."
  printf '%s' "$ip"
}

# PostgreSQL init prints Username:/Password:; log collectors often prefix lines (^ no longer matches).
_fetch_pg_logs() {
  local cur prev
  cur="$("$@" logs statefulset/postgresql -n reconhawx 2>&1 || true)"
  if printf '%s\n' "$cur" | grep -qF 'ADMIN USER CREATED'; then
    printf '%s' "$cur"
    return 0
  fi
  prev="$("$@" logs statefulset/postgresql -n reconhawx --previous 2>/dev/null || true)"
  if printf '%s\n' "$prev" | grep -qF 'ADMIN USER CREATED'; then
    printf '%s' "$prev"
    return 0
  fi
  printf '%s\n%s' "$cur" "$prev"
}

# Log API can lag behind Ready; init prints to stderr early in the same container.
_fetch_pg_logs_with_retry() {
  local logs attempt max_attempts=45 sleep_s=2 warned=0
  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    logs="$(_fetch_pg_logs "$@")"
    if printf '%s' "$logs" | grep -qF 'ADMIN USER CREATED'; then
      printf '%s' "$logs"
      return 0
    fi
    if printf '%s' "$logs" | grep -qF 'skipping admin user creation'; then
      printf '%s' "$logs"
      return 0
    fi
    if printf '%s' "$logs" | grep -qF 'Username:' && printf '%s' "$logs" | grep -qF 'Password:'; then
      printf '%s' "$logs"
      return 0
    fi
    if [[ "$attempt" -eq 1 ]]; then
      continue
    fi
    if [[ "$warned" -eq 0 ]]; then
      ui_note "PostgreSQL logs do not show the admin bootstrap yet; retrying for up to ~$((max_attempts * sleep_s))s …"
      warned=1
    fi
    sleep "$sleep_s"
  done
  _fetch_pg_logs "$@"
}

# sed (not grep) so empty matches do not exit 1 under set -o pipefail inside $(...).
_pg_admin_user_from_logs() {
  printf '%s' "$1" | sed -n 's/.*Username:[[:space:]]*//p' | tail -n1 | sed 's/[[:space:]]*$//;s/\r$//'
}

_pg_admin_pass_from_logs() {
  printf '%s' "$1" | sed -n 's/.*Password:[[:space:]]*//p' | tail -n1 | sed 's/[[:space:]]*$//;s/\r$//'
}

main() {
  require_cmd kubectl
  require_cmd openssl

  ui_banner

  resolve_kubernetes_base_src

  kubectl_cluster_ok
  if [[ -n "${KUBECONFIG:-}" ]]; then
    ui_note "Using KUBECONFIG=${KUBECONFIG}"
  fi

  ui_step "Configuration (installer prompts)"

  local INSTALL_ROOT BASE_DST
  if [[ "${RECONHAWX_INSTALL_FROM_RELEASE}" -eq 1 ]]; then
    INSTALL_ROOT="$RECONHAWX_SOURCE_TREE_ROOT"
    BASE_DST="$INSTALL_ROOT/kubernetes/base"
    [[ -d "$BASE_DST" ]] || die "missing kubernetes/base under ${INSTALL_ROOT}"
    ui_note "Using kubernetes/base in place: ${INSTALL_ROOT}."
  else
    install_staging_prepare
    INSTALL_ROOT="$INSTALL_STAGING_DIR"
    BASE_DST="$INSTALL_ROOT/kubernetes/base"
    ui_note "Copying kubernetes/base from your git clone to ${INSTALL_STAGING_DIR} (removed after a successful install)."
    ui_step "Syncing manifests to $BASE_DST"
    ensure_install_prefix "$INSTALL_ROOT"
    mkdir -p "$INSTALL_ROOT/kubernetes"
    sync_kubernetes_base "$BASE_SRC" "$BASE_DST"
  fi

  local _ingress_reply
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Frontend ingress hostname [${INGRESS_HOST}]: ")" _ingress_reply
  _ingress_reply="$(printf '%s' "${_ingress_reply:-$INGRESS_HOST}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$_ingress_reply" ]] || _ingress_reply=reconhawx.local
  INGRESS_HOST="$_ingress_reply"
  patch_frontend_ingress_host_if_custom "$BASE_DST" "$INGRESS_HOST"

  local jwt_plain refresh_plain pg_user pg_pass
  ui_note "JWT / refresh: leave empty for random hex keys (base64-encoded in manifests, per docs)."
  read_installer -r -s -p "$(printf '%sinstaller · %s' "$_B" "JWT signing secret (empty = random): ")" jwt_plain
  echo
  read_installer -r -s -p "$(printf '%sinstaller · %s' "$_B" "Refresh secret key (empty = random): ")" refresh_plain
  echo

  local default_pg_user=reconhawx
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "PostgreSQL username [${default_pg_user}]: ")" pg_user
  pg_user="${pg_user:-$default_pg_user}"

  read_installer -r -s -p "$(printf '%sinstaller · %s' "$_B" "PostgreSQL password (empty = random): ")" pg_pass
  echo
  if [[ -z "$pg_pass" ]]; then
    pg_pass="$(openssl rand -hex 32)"
  fi

  if [[ ! -w "$BASE_DST" ]]; then
    sudo chown -R "$(id -u):$(id -g)" "$INSTALL_ROOT"
  fi

  write_secrets_from_examples "$BASE_DST" "$jwt_plain" "$refresh_plain" "$pg_user" "$pg_pass"

  list_cluster_nodes
  print_node_menu
  collect_reconhawx_node_roles_from_cluster
  if cluster_already_has_runner_and_worker_labels; then
    local rs ws labeling_ok
    printf -v rs '%s, ' "${RUNNER_NODES[@]}"
    rs="${rs%, }"
    printf -v ws '%s, ' "${WORKER_NODES[@]}"
    ws="${ws%, }"
    ui_note "Existing labels — runners: ${rs}; workers: ${ws}"
    read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Keep current runner/worker labels? [Y/n] ")" labeling_ok
    case "${labeling_ok:-y}" in
    n | N | no | NO | No)
      prompt_node_roles
      apply_node_labels
      ;;
    *)
      ui_ok "Keeping existing node labels"
      ;;
    esac
  else
    prompt_node_roles
    apply_node_labels
  fi

  ui_step "Kubernetes: ensuring namespace reconhawx"
  kubectl create namespace reconhawx --dry-run=client -o yaml | kubectl apply -f -
  ui_ok "Namespace ready"

  run_tool_long "Kubernetes: installing Kueue ${KUEUE_VERSION} (server-side apply)" \
    bash -c 'set -euo pipefail
      kubectl apply --server-side -f "https://github.com/kubernetes-sigs/kueue/releases/download/$1/manifests.yaml"
      kubectl apply --server-side -f "https://github.com/kubernetes-sigs/kueue/releases/download/$1/visibility-apf.yaml"
    ' bash "$KUEUE_VERSION"

  ui_step "Kubernetes: waiting for Kueue controller"
  tool_stream kubectl wait deploy/kueue-controller-manager -nkueue-system --for=condition=available --timeout=5m
  ui_ok "Kueue controller available"

  run_tool_long "Kubernetes: installing ingress-nginx (cloud manifest)" \
    kubectl apply -f "$INGRESS_NGINX_DEPLOY_URL"

  ui_step "Kubernetes: waiting for ingress-nginx controller"
  tool_stream kubectl wait deploy/ingress-nginx-controller -n ingress-nginx --for=condition=available --timeout=5m
  ui_ok "Ingress controller deployment available"

  ui_step "Kubernetes: finishing ingress-nginx rollout"
  tool_stream kubectl rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=5m
  ui_ok "Ingress controller rolled out"

  wait_ingress_nginx_admission_endpoints
  ui_ok "Ingress admission webhook should be reachable"

  local hosts_ip="" ml_ans pool_ip want_hosts=1 hosts_ans
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Add ${INGRESS_HOST} to /etc/hosts (requires sudo)? [Y/n] ")" hosts_ans
  case "${hosts_ans:-y}" in
  n | N | no | NO | No) want_hosts=0 ;;
  esac

  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Install MetalLB (optional, for LoadBalancer IPs)? [y/N] ")" ml_ans
  case "$ml_ans" in
  y | Y | yes | YES | Yes)
    run_tool_long "Kubernetes: installing MetalLB" \
      kubectl apply -f "$METALLB_MANIFEST_URL"
    ui_note "Waiting for MetalLB pods …"
    tool_stream kubectl wait -n metallb-system --for=condition=ready pod --all --timeout=5m || sleep 15
    read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "MetalLB pool IP (e.g. 192.168.0.66; used in IPAddressPool): ")" pool_ip
    [[ -n "${pool_ip// /}" ]] || die "MetalLB pool IP required"
    local ml_ex="$BASE_DST/metal-lb/metal-lb.yaml.example"
    local ml_out="$BASE_DST/metal-lb/metal-lb.yaml"
    [[ -f "$ml_ex" ]] || die "missing $ml_ex"
    sed "s#LB_IP_PLACEHOLDER#${pool_ip}#g" "$ml_ex" >"$ml_out"
    tool_stream kubectl apply -f "$ml_out"
    if [[ "$want_hosts" -eq 1 ]]; then
      hosts_ip="$pool_ip"
      ui_ok "MetalLB configured; using ${pool_ip} for /etc/hosts."
    else
      ui_ok "MetalLB configured (pool IP ${pool_ip})."
      ui_note "Skipping /etc/hosts; map ${INGRESS_HOST} to your ingress (e.g. ${pool_ip}) via DNS or a manual hosts file."
    fi
    ;;
  *)
    if [[ "$want_hosts" -eq 1 ]]; then
      hosts_ip="$(discover_or_prompt_ingress_ip)"
    else
      ui_note "Skipping /etc/hosts; map ${INGRESS_HOST} to your ingress via DNS or a manual hosts file."
    fi
    ;;
  esac

  ui_step "Kubernetes: applying ReconHawx manifests (kustomize)"
  local _attempt _max=6
  for _attempt in $(seq 1 "$_max"); do
    if tool_stream kubectl apply -k "$BASE_DST"; then
      ui_ok "Manifests applied"
      break
    fi
    if [[ "$_attempt" -eq "$_max" ]]; then
      die "kubectl apply -k failed after ${_max} attempts"
    fi
    ui_note "Apply failed (attempt ${_attempt}/${_max}); waiting 15s and retrying …"
    sleep 15
  done

  ui_step "Kubernetes: waiting for PostgreSQL"
  tool_stream kubectl rollout status statefulset/postgresql -n reconhawx --timeout=5m
  ui_ok "PostgreSQL available"

  if [[ -n "$hosts_ip" ]]; then
    update_hosts_file "$hosts_ip"
  fi

  ui_step "Kubernetes: waiting for API and frontend"
  tool_stream kubectl wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
  ui_ok "API and frontend available"

  local pg_logs admin_user admin_pass
  ui_step "Reading PostgreSQL logs for default admin credentials"
  pg_logs="$(_fetch_pg_logs_with_retry kubectl)"
  admin_user="$(_pg_admin_user_from_logs "$pg_logs")"
  admin_pass="$(_pg_admin_pass_from_logs "$pg_logs")"

  printf '\n'
  _ui_box_top "$_G" "$_Z"
  _ui_box_mid "$_G" "$_B" "Installation complete" "$_Z"
  _ui_box_bot "$_G" "$_Z"

  ui_step "Sign in at http://${INGRESS_HOST}"
  if [[ -n "$admin_user" && -n "$admin_pass" ]]; then
    printf '%s  Username:%s %s\n' "$_B" "$_Z" "$admin_user"
    printf '%s  Password:%s %s\n' "$_B" "$_Z" "$admin_pass"
    ui_note "Change this password after login."
  elif printf '%s' "$pg_logs" | grep -qF 'skipping admin user creation'; then
    ui_note "No new admin user (database already had users). Use your existing admin credentials or reset via the API/DB."
  else
    ui_note "Could not read admin credentials from logs yet. Try: kubectl logs statefulset/postgresql -n reconhawx | grep -A3 ADMIN"
  fi

  if [[ "${RECONHAWX_INSTALL_FROM_RELEASE}" -eq 0 ]]; then
    install_staging_cleanup_on_success
  else
    ui_note "Manifest source tree left at ${RECONHAWX_SOURCE_TREE_ROOT} (reuse for ops, debugging, etc.)."
  fi
}

FORCE_FROM_RELEASE_ARG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-release)
      FORCE_FROM_RELEASE_ARG=1
      shift
      ;;
    -h | --help)
      usage_install_kubernetes
      exit 0
      ;;
    *)
      die "unknown option: $1 (try --help)"
      ;;
  esac
done

main
