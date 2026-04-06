#!/usr/bin/env bash
#
# Install ReconHawx on Minikube (see docs/install-on-minikube.md).
# Uses `minikube … kubectl` (standalone kubectl not required).
# Manifests: local kubernetes/base when present, otherwise latest GitHub release tarball
# (full tree in place under the extract). Unpacked release (no .git): kubernetes/base in place.
# Git clone: copy kubernetes/base to INSTALL_STAGING_DIR (default /tmp/reconhawx).
#
# Set RECONHAWX_NO_COLOR=1 to disable ANSI styling.
# Long tool logs: show RUN_TOOL_LONG_HEAD_LINES (default 10) on success; on failure, error-like lines plus a tail.
#
# -u deferred: piped installs (curl … | bash) may not set BASH_SOURCE[0], which would trip nounset.
set -eo pipefail

RUN_TOOL_LONG_HEAD_LINES="${RUN_TOOL_LONG_HEAD_LINES:-10}"
RUN_TOOL_LONG_FAIL_TAIL_LINES="${RUN_TOOL_LONG_FAIL_TAIL_LINES:-25}"

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
KUEUE_VERSION="${KUEUE_VERSION:-v0.11.1}"
INGRESS_HOST="${INGRESS_HOST:-reconhawx.local}"
# RECONHAWX_FROM_RELEASE: unset = auto (local kubernetes/base if present, else tarball); 0 = local only; 1 = tarball only.
RECONHAWX_GITHUB_REPO="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"
RECONHAWX_RELEASE_TMPDIR=""
# 1 = in-place kubernetes/base; 0 = stage under INSTALL_STAGING_DIR (git clone only).
RECONHAWX_INSTALL_FROM_RELEASE=0
RECONHAWX_SOURCE_TREE_ROOT=""
# Git clones only: staging copy (removed after a successful install).
INSTALL_STAGING_DIR="${INSTALL_STAGING_DIR:-/tmp/reconhawx}"

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
  printf '%s  %s%s\n' "$_D" "$*" "$_Z" >&2
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

# curl … | bash: stdin is the script; prompts read from /dev/tty.
read_installer() {
  if [[ -t 0 ]]; then
    read "$@" || die "Unexpected end of input"
  elif [[ -r /dev/tty ]]; then
    read "$@" </dev/tty || die "Cannot read prompts (try: bash <(curl -fsSL URL) or save this script and run bash install-minikube.sh)"
  else
    die "No TTY for prompts. Save the script and run: bash install-minikube.sh"
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

usage_install_minikube() {
  cat <<'EOF'
Usage: install-minikube.sh [options]

  --from-release    Use the latest GitHub release source tarball (also the default when
                    kubernetes/base is not next to this script).

  -h, --help        Show this help.

Environment:
  RECONHAWX_FROM_RELEASE   unset = auto; 0 = local kubernetes/base only; 1 = release tarball only.
  RECONHAWX_GITHUB_REPO    owner/repo (default: ReconHawx/reconhawx).
  INSTALL_STAGING_DIR      Git-clone installs: staging copy (default: /tmp/reconhawx); deleted after success.
  INGRESS_HOST             Frontend URL hostname (default: reconhawx.local); also written to frontend-ingress when not default.
EOF
}

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
  local repo api json url tarpath root base
  repo="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"
  api="https://api.github.com/repos/${repo}/releases/latest"

  ui_step "Fetching source from latest GitHub release (${repo})"
  json="$(
    curl -sSf \
      -H 'Accept: application/vnd.github+json' \
      -H 'User-Agent: reconhawx-install-minikube' \
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
  require_cmd minikube
  require_cmd openssl

  ui_banner

  resolve_kubernetes_base_src

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
    ui_ok "Manifest tree ready"
  fi

  local _ingress_reply
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Frontend ingress hostname [${INGRESS_HOST}]: ")" _ingress_reply
  _ingress_reply="$(printf '%s' "${_ingress_reply:-$INGRESS_HOST}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$_ingress_reply" ]] || _ingress_reply=reconhawx.local
  INGRESS_HOST="$_ingress_reply"
  patch_frontend_ingress_host_if_custom "$BASE_DST" "$INGRESS_HOST"

  local default_profile=reconhawx
  read_installer -r -p "$(printf '%sinstaller · %s' "$_B" "Minikube profile (cluster name) [${default_profile}]: ")" MINIKUBE_PROFILE
  MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-$default_profile}"

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
  tool_stream mk rollout status statefulset/postgresql -n reconhawx --timeout=5m
  ui_ok "PostgreSQL available"

  local ip
  ip="$(minikube -p "$MINIKUBE_PROFILE" ip)"
  update_hosts_file "$ip"

  ui_step "Kubernetes: waiting for API and frontend"
  tool_stream mk wait deploy/frontend deploy/api -n reconhawx --for=condition=available --timeout=5m
  ui_ok "API and frontend available"

  local pg_logs admin_user admin_pass
  ui_step "Reading PostgreSQL logs for default admin credentials"
  pg_logs="$(_fetch_pg_logs_with_retry minikube -p "$MINIKUBE_PROFILE" kubectl --)"
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
    ui_note "Could not read admin credentials from logs yet. Try: minikube -p ${MINIKUBE_PROFILE} kubectl -- logs statefulset/postgresql -n reconhawx | grep -A3 ADMIN"
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
      usage_install_minikube
      exit 0
      ;;
    *)
      die "unknown option: $1 (try --help)"
      ;;
  esac
done

main
