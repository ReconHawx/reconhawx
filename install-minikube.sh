#!/usr/bin/env bash
#
# Install ReconHawx on Minikube (see docs/install-on-minikube.md).
# Run from any directory; resolves repo kubernetes/base from this script's location.
# Uses only `minikube … kubectl` (standalone kubectl not required).
# The install root is where kubernetes/base is copied so repo files are not modified.
#
# Set RECONHAWX_NO_COLOR=1 to disable ANSI styling.
# Long tool logs: show RUN_TOOL_LONG_HEAD_LINES (default 10) on success; on failure, error-like lines plus a tail.
#
set -euo pipefail

RUN_TOOL_LONG_HEAD_LINES="${RUN_TOOL_LONG_HEAD_LINES:-10}"
RUN_TOOL_LONG_FAIL_TAIL_LINES="${RUN_TOOL_LONG_FAIL_TAIL_LINES:-25}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_SRC="$REPO_ROOT/kubernetes/base"
KUEUE_VERSION="${KUEUE_VERSION:-v0.11.1}"
INGRESS_HOST="${INGRESS_HOST:-reconhawx.local}"

if [[ -t 1 ]] && [[ -z "${RECONHAWX_NO_COLOR:-}" ]]; then
  _B=$'\e[1m'
  _D=$'\e[2m'
  _C=$'\e[36m'
  _G=$'\e[32m'
  _R=$'\e[31m'
  _Y=$'\e[33m'
  _Z=$'\e[0m'
else
  _B= _D= _C= _G= _R= _Y= _Z=
fi

die() {
  printf '%s✗ %s%s\n' "$_R" "$*" "$_Z" >&2
  exit 1
}

# Inner width between corners (must match "%-60s" plus the four surrounding spaces: 60+4=64).
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

# One content line: │ + two spaces + 60-char field + two spaces + │ (ASCII in the field avoids column drift).
_ui_box_mid() {
  printf '%s│%s  %-*s  %s│%s\n' "$1" "$2" 60 "$3" "$1" "$4"
}

ui_banner() {
  _ui_box_top "$_C" "$_Z"
  _ui_box_mid "$_C" "$_B" "ReconHawx - Minikube installation" "$_Z"
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

# Stream minikube/kubectl (and similar) output: prefixed gutter so it reads separately from installer text.
# With pipefail, PIPESTATUS[0] is the exit status of the command on the left of the pipe.
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

# Run a command with full output captured; print a short preview so the install flow is not blocked by pagers.
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

# deploy Available can be true before validate.nginx.ingress.kubernetes.io accepts traffic (connection refused).
wait_ingress_nginx_admission_endpoints() {
  local profile="$1"
  local ns=ingress-nginx
  local svc=ingress-nginx-controller-admission
  local deadline=$((SECONDS + 300))
  ui_note "Waiting for ${svc} endpoints (ingress validating webhook) …"
  while ((SECONDS < deadline)); do
    local ips
    ips="$(minikube -p "$profile" kubectl -- get endpoints "$svc" -n "$ns" -o jsonpath='{.subsets[0].addresses[*].ip}' 2>/dev/null || true)"
    if [[ -n "${ips// /}" ]]; then
      ui_note "Admission endpoints are up; short pause for the webhook to listen …"
      sleep 12
      return 0
    fi
    sleep 2
  done
  die "Timed out waiting for ${svc} endpoints. Check: minikube -p ${profile} kubectl -- get ep,po -n ${ns}"
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

# Escape dots so host labels match literally in grep ERE / sed BRE.
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

hosts_lines_matching_reconhawx_local() {
  local pat
  pat="$(_dots_escape_host "$INGRESS_HOST")"
  grep -nE '(^|[[:space:]])'"${pat}"'([[:space:]]|$)' /etc/hosts 2>/dev/null || true
}

# Classify /etc/hosts mapping for INGRESS_HOST vs Minikube IP (word-boundary match on hostname).
# Prints one of: missing | ok | wrong
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
  read -r -p "$(printf '%sinstaller · %s' "$_B" "Remove those lines and set ${INGRESS_HOST} to ${ip}? [y/N] ")" ans
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

main() {
  require_cmd minikube
  require_cmd openssl

  ui_banner

  [[ -d "$BASE_SRC" ]] || die "kubernetes/base not found at $BASE_SRC (expected repo layout)"

  ui_step "Configuration (installer prompts)"
  local default_root=~/reconhawx
  ui_note "Install root: copy destination for kubernetes/base (secrets and applies use this tree, not the repo)."
  read -r -p "$(printf '%sinstaller · %s' "$_B" "Install root directory [${default_root}]: ")" INSTALL_ROOT
  INSTALL_ROOT="${INSTALL_ROOT:-$default_root}"
  local BASE_DST="$INSTALL_ROOT/kubernetes/base"

  local default_profile=reconhawx
  read -r -p "$(printf '%sinstaller · %s' "$_B" "Minikube profile (cluster name) [${default_profile}]: ")" MINIKUBE_PROFILE
  MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-$default_profile}"

  local jwt_plain refresh_plain pg_user pg_pass
  ui_note "JWT / refresh: leave empty for random hex keys (base64-encoded in manifests, per docs)."
  read -r -s -p "$(printf '%sinstaller · %s' "$_B" "JWT signing secret (empty = random): ")" jwt_plain
  echo
  read -r -s -p "$(printf '%sinstaller · %s' "$_B" "Refresh secret key (empty = random): ")" refresh_plain
  echo

  local default_pg_user=reconhawx
  read -r -p "$(printf '%sinstaller · %s' "$_B" "PostgreSQL username [${default_pg_user}]: ")" pg_user
  pg_user="${pg_user:-$default_pg_user}"

  read -r -s -p "$(printf '%sinstaller · %s' "$_B" "PostgreSQL password (empty = random): ")" pg_pass
  echo
  if [[ -z "$pg_pass" ]]; then
    pg_pass="$(openssl rand -hex 32)"
  fi

  ui_step "Syncing manifests to $BASE_DST"
  ensure_install_prefix "$INSTALL_ROOT"
  mkdir -p "$INSTALL_ROOT/kubernetes"
  sync_kubernetes_base "$BASE_SRC" "$BASE_DST"
  ui_ok "Manifest tree ready"

  if [[ ! -w "$BASE_DST" ]]; then
    sudo chown -R "$(id -u):$(id -g)" "$INSTALL_ROOT"
  fi

  write_secrets_from_examples "$BASE_DST" "$jwt_plain" "$refresh_plain" "$pg_user" "$pg_pass"

  mk() {
    minikube -p "$MINIKUBE_PROFILE" kubectl -- "$@"
  }

  # Verbose cluster steps: capture full log; print a short preview (see run_tool_long).
  run_tool_long "Minikube: starting cluster (profile ${MINIKUBE_PROFILE}, docker, ports 80/443)" \
    minikube -p "$MINIKUBE_PROFILE" start --driver=docker --ports=80:80 --ports=443:443

  local node
  node="$(mk get nodes -o jsonpath='{.items[0].metadata.name}')"
  [[ -n "$node" ]] || die "could not resolve cluster node name"

  ui_step "Kubernetes: labeling node $node"
  tool_stream mk label node "$node" reconhawx.runner=true --overwrite
  tool_stream mk label node "$node" reconhawx.worker=true --overwrite
  ui_ok "Node labels applied"

  ui_step "Kubernetes: ensuring namespace reconhawx"
  tool_stream bash -c 'set -euo pipefail
    minikube -p "$1" kubectl -- create namespace reconhawx --dry-run=client -o yaml |
      minikube -p "$1" kubectl -- apply -f -
  ' bash "$MINIKUBE_PROFILE"
  ui_ok "Namespace ready"

  run_tool_long "Kubernetes: installing Kueue ${KUEUE_VERSION} (server-side apply)" \
    bash -c 'set -euo pipefail
      minikube -p "$1" kubectl -- apply --server-side -f "https://github.com/kubernetes-sigs/kueue/releases/download/$2/manifests.yaml"
      minikube -p "$1" kubectl -- apply --server-side -f "https://github.com/kubernetes-sigs/kueue/releases/download/$2/visibility-apf.yaml"
    ' bash "$MINIKUBE_PROFILE" "$KUEUE_VERSION"

  ui_step "Kubernetes: waiting for Kueue controller"
  tool_stream mk wait deploy/kueue-controller-manager -nkueue-system --for=condition=available --timeout=5m
  ui_ok "Kueue controller available"

  run_tool_long "Minikube: enabling ingress addon" \
    minikube -p "$MINIKUBE_PROFILE" addons enable ingress

  ui_step "Kubernetes: waiting for ingress-nginx controller"
  tool_stream mk wait deploy/ingress-nginx-controller -n ingress-nginx --for=condition=available --timeout=5m
  ui_ok "Ingress controller deployment available"

  ui_step "Kubernetes: finishing ingress-nginx rollout"
  tool_stream mk rollout status deployment/ingress-nginx-controller -n ingress-nginx --timeout=5m
  ui_ok "Ingress controller rolled out"

  wait_ingress_nginx_admission_endpoints "$MINIKUBE_PROFILE"
  ui_ok "Ingress admission webhook should be reachable"

  ui_step "Kubernetes: applying ReconHawx manifests (kustomize)"
  local _attempt _max
  _max=6
  for _attempt in $(seq 1 "$_max"); do
    if tool_stream mk apply -k "$BASE_DST"; then
      ui_ok "Manifests applied"
      break
    fi
    if [[ "$_attempt" -eq "$_max" ]]; then
      die "kubectl apply -k failed after ${_max} attempts (last error often ingress webhook; see messages above)"
    fi
    ui_note "Apply failed (attempt ${_attempt}/${_max}); waiting 15s and retrying (ingress admission may still be starting) …"
    sleep 15
  done

  ui_step "Kubernetes: waiting for PostgreSQL"
  tool_stream mk wait deploy/postgresql -n reconhawx --for=condition=available --timeout=5m
  ui_ok "PostgreSQL available"

  local ip
  ip="$(minikube -p "$MINIKUBE_PROFILE" ip)"
  update_hosts_file "$ip"

  ui_step "Kubernetes: waiting for API and frontend"
  tool_stream mk wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
  ui_ok "API and frontend available"

  local pg_logs admin_user admin_pass
  pg_logs="$(mk logs deploy/postgresql -n reconhawx 2>&1 || true)"
  admin_user="$(printf '%s' "$pg_logs" | sed -n 's/^[[:space:]]*Username:[[:space:]]*//p' | tail -n1 | tr -d '\r')"
  admin_pass="$(printf '%s' "$pg_logs" | sed -n 's/^[[:space:]]*Password:[[:space:]]*//p' | tail -n1 | tr -d '\r')"

  printf '\n'
  _ui_box_top "$_G" "$_Z"
  _ui_box_mid "$_G" "$_B" "Installation complete" "$_Z"
  _ui_box_bot "$_G" "$_Z"

  ui_step "Sign in at http://${INGRESS_HOST}"
  if printf '%s' "$pg_logs" | grep -q 'ADMIN USER CREATED'; then
    if [[ -n "$admin_user" && -n "$admin_pass" ]]; then
      printf '%s  Username:%s %s\n' "$_B" "$_Z" "$admin_user"
      printf '%s  Password:%s %s\n' "$_B" "$_Z" "$admin_pass"
      ui_note "Change this password after login."
    else
      ui_note "Admin user was created but username/password could not be parsed from logs; check: mk logs deploy/postgresql -n reconhawx"
    fi
  else
    ui_note "No new admin bootstrap block in logs (users may already exist). Use your existing admin credentials or inspect PostgreSQL logs."
  fi
}

main "$@"
