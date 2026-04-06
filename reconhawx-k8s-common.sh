#!/usr/bin/env bash
#
# reconhawx-k8s-common.sh — small Bash library for *upgrade* flows only.
#
# Purpose
# -------
# install-kubernetes.sh and install-minikube.sh stay fully self-contained so
# `curl … | bash` still works without pulling a second file from the repo.
# Upgrade scripts need the same GitHub release / local manifest resolution and
# version introspection; this file holds that logic once so update-kubernetes.sh
# and update-minikube.sh do not drift from each other.
#
# Location
# --------
# This file lives at the **repository root** next to update-*.sh. It is not under
# scripts/: that directory is gitignored in this project (local tooling), so
# anything required for a normal clone or release tarball must live elsewhere.
#
# What it does
# ------------
# - Resolve kubernetes/base: optional download of the latest GitHub release
#   tarball (same rules as install: RECONHAWX_FROM_RELEASE, --from-release,
#   RECONHAWX_GITHUB_REPO), setting BASE_SRC and related globals.
# - Query GitHub releases/latest for the published tag (for “latest release” UX).
# - Read the manifest bundle semver from kubernetes/base/config/reconhawx-version.yaml
#   (APP_VERSION — tied to release-please / cluster ConfigMap reconhawx-version).
# - Locate kubernetes/base-update next to kubernetes/base (safe apply without
#   re-applying jwt/postgres secrets from git).
# - Sync frontend Ingress host in kubernetes/base from the cluster before upgrade apply
#   so custom install hostnames are not overwritten by the repo default.
# - From a git clone, copy kubernetes/base and kubernetes/base-update to
#   INSTALL_STAGING_DIR (default /tmp/reconhawx) so patches do not dirty the repo;
#   release trees apply from the extracted path in place.
# - Run kubernetes/base-update/pre-apply.d/[0-9]*.sh (reconhawx_run_base_update_pre_apply_hooks)
#   before kubectl apply -k base-update so breaking manifest transitions stay idempotent.
#
# Usage
# -----
# From the repo root (same directory as this file):
#   source "$REPO_ROOT/reconhawx-k8s-common.sh"
#
# The caller must define: die(), require_cmd(). If download path runs, it also
# calls ui_step, ui_ok, ui_note — define those for consistent installer-style
# output, or stub them if you need a silent/tooling caller.
# Git staging paths also need read_installer() (and _B/_Z if you style prompts).
#
# Not runnable on its own (no main); do not execute directly.
#
# shellcheck shell=bash

reconhawx_json_tarball_url_from_api() {
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

reconhawx_latest_release_json() {
  local repo="${1:-ReconHawx/reconhawx}"
  local api="https://api.github.com/repos/${repo}/releases/latest"
  curl -sSf \
    -H 'Accept: application/vnd.github+json' \
    -H 'User-Agent: reconhawx-update-kubernetes' \
    "$api" || die "curl failed: ${api}"
}

# Prints semantic version without leading v (e.g. 0.7.0 from tag v0.7.0).
reconhawx_latest_release_version_from_github() {
  local json="$1" tag
  if command -v jq &>/dev/null; then
    tag="$(printf '%s' "$json" | jq -r .tag_name)"
  elif command -v python3 &>/dev/null; then
    tag="$(printf '%s' "$json" | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'])")"
  else
    die "needs jq or python3 to read GitHub release tag_name"
  fi
  if [[ -z "$tag" || "$tag" == "null" ]]; then
    die "GitHub API did not return tag_name"
  fi
  printf '%s' "${tag#v}"
}

reconhawx_local_tree_version() {
  local root="$1"
  local vf="$root/version.txt"
  if [[ -f "$vf" ]]; then
    tr -d ' \t\r\n' <"$vf"
    return 0
  fi
  printf ''
}

# Sets BASE_SRC, RECONHAWX_SOURCE_TREE_ROOT, RECONHAWX_INSTALL_FROM_RELEASE=1, RECONHAWX_RELEASE_TMPDIR
reconhawx_download_release_kubernetes_base_set_BASE_SRC() {
  require_cmd curl
  require_cmd tar
  local repo api json url tarpath root base
  repo="${RECONHAWX_GITHUB_REPO:-ReconHawx/reconhawx}"
  api="https://api.github.com/repos/${repo}/releases/latest"

  ui_step "Fetching kubernetes manifests from latest GitHub release (${repo})"
  json="$(reconhawx_latest_release_json "$repo")"
  url="$(reconhawx_json_tarball_url_from_api "$json")"

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
  ui_ok "Release extracted at ${root} (manifests from ${BASE_SRC})."
}

reconhawx_resolve_kubernetes_base_src() {
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
    reconhawx_download_release_kubernetes_base_set_BASE_SRC
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

reconhawx_sync_directory_tree() {
  local src="$1" dst="$2"
  if command -v rsync &>/dev/null; then
    mkdir -p "$dst"
    rsync -a --delete "$src/" "$dst/"
  else
    rm -rf "$dst"
    mkdir -p "$dst"
    cp -a "$src"/. "$dst"/
  fi
}

reconhawx_ensure_install_prefix() {
  local root="$1"
  if [[ -d "$root" ]] && [[ -w "$root" ]]; then
    return 0
  fi
  local parent
  parent="$(dirname "$root")"
  if [[ -d "$parent" ]] && [[ -w "$parent" ]]; then
    mkdir -p "$root/kubernetes/base" 2>/dev/null && return 0
  fi
  ui_note "Creating staging directory with sudo: $root"
  sudo mkdir -p "$root/kubernetes"
  sudo chown -R "$(id -u):$(id -g)" "$root"
}

# If staging_dir exists, prompt to remove (needs read_installer, ui_*, die, _B, _Z).
reconhawx_staging_dir_prepare() {
  local dir="$1"
  if [[ ! -e "$dir" ]]; then
    return 0
  fi
  ui_note "Upgrade staging path ${dir} already exists."
  local ans
  read_installer -r -p "$(printf '%supgrade · %s' "$_B" "Remove ${dir} and continue? [y/N] ")" ans
  case "$ans" in
  y | Y | yes | YES | Yes)
    rm -rf "$dir"
    ui_note "Removed ${dir}"
    ;;
  *)
    die "Aborted: remove or rename ${dir} and re-run."
    ;;
  esac
}

# Copy kubernetes/base and kubernetes/base-update under staging_root; print new kubernetes/base path
# on stdout only. Helpers here must not write ui_ok/ui_step to stdout (callers use BASE_SRC="$(…)").
reconhawx_stage_kubernetes_upgrade_manifests() {
  local repo_root="$1" staging_root="$2"
  local dst_base="$staging_root/kubernetes/base" dst_up="$staging_root/kubernetes/base-update"
  [[ -d "$repo_root/kubernetes/base-update" ]] || die "missing ${repo_root}/kubernetes/base-update"
  reconhawx_staging_dir_prepare "$staging_root"
  reconhawx_ensure_install_prefix "$staging_root"
  mkdir -p "$staging_root/kubernetes"
  # ui_note only: stdout must be only the path (callers use BASE_SRC="$(…)" ).
  ui_note "Syncing upgrade manifests to ${staging_root} (git clone; removed after success)"
  reconhawx_sync_directory_tree "$repo_root/kubernetes/base" "$dst_base"
  reconhawx_sync_directory_tree "$repo_root/kubernetes/base-update" "$dst_up"
  ui_note "Staged kubernetes/base and kubernetes/base-update"
  printf '%s' "$dst_base"
}

reconhawx_update_staging_cleanup_on_success() {
  local dir="${1:-}"
  [[ -n "$dir" ]] || return 0
  if [[ -e "$dir" ]]; then
    ui_note "Removing upgrade staging directory ${dir} …"
    rm -rf "$dir"
    ui_note "Staging directory removed"
  fi
}

reconhawx_base_update_dir() {
  local base_dir="$1"
  local upd
  upd="$(cd "$base_dir/.." && pwd)/base-update"
  [[ -d "$upd" ]] || die "missing ${upd} (kubernetes/base-update must sit next to kubernetes/base)"
  printf '%s' "$upd"
}

# Log pre-apply progress to stderr (same style as ui_note when _D/_Z are set).
reconhawx__pre_apply_log() {
  printf '%s  pre-apply: %s%s\n' "${_D:-}" "$*" "${_Z:-}" >&2
}

# Run kubernetes/base-update/pre-apply.d/[0-9]*.sh in sorted order before kubectl apply -k base-update.
# Args: kubernetes/base path, namespace, cluster APP_VERSION (may be empty), bundle APP_VERSION,
#       then kubectl argv prefix (e.g. kubectl OR minikube -p PROFILE kubectl --).
# Exports RECONHAWX_NS, RECONHAWX_CLUSTER_VERSION, RECONHAWX_BUNDLE_VERSION, RECONHAWX_PRE_APPLY_LIB (temp file).
# Requires: die(), and for UX ui_step / ui_ok like other helpers in this file.
reconhawx_run_base_update_pre_apply_hooks() {
  local base_src="$1" ns="$2" cver="$3" bver="$4"
  local -a kube_prefix=( "${@:5}" )
  [[ "${#kube_prefix[@]}" -ge 1 ]] || die "reconhawx_run_base_update_pre_apply_hooks: missing kubectl argv prefix (pass kubectl or 'minikube -p PROFILE kubectl --' after bundle version)"

  reconhawx__pre_apply_log "dispatcher starting (namespace ${ns})."

  local hookdir lib h
  hookdir="$(reconhawx_base_update_dir "$base_src")/pre-apply.d"
  if [[ ! -d "$hookdir" ]]; then
    reconhawx__pre_apply_log "no directory ${hookdir}; skipping."
    return 0
  fi

  local -a hooks=()
  local _nullglob_was_on=1
  shopt -q nullglob || _nullglob_was_on=0
  shopt -s nullglob
  hooks=( "$hookdir"/[0-9]*.sh )
  if [[ "$_nullglob_was_on" -eq 0 ]]; then
    shopt -u nullglob
  fi

  if [[ "${#hooks[@]}" -eq 0 ]]; then
    reconhawx__pre_apply_log "no matching [0-9]*.sh in ${hookdir}; skipping."
    return 0
  fi

  reconhawx__pre_apply_log "running ${#hooks[@]} script(s) from ${hookdir}."

  lib="$(mktemp "${TMPDIR:-/tmp}/reconhawx-pre-apply-lib.XXXXXX")"
  [[ -n "$lib" ]] || die "reconhawx_run_base_update_pre_apply_hooks: mktemp failed for kubectl wrapper"
  {
    printf 'reconhawx_kubectl() {\n  '
    local a
    for a in "${kube_prefix[@]}"; do
      printf '%q ' "$a"
    done
    printf -- '-n "${RECONHAWX_NS}" "$@"\n}\n'
  } >"$lib"
  bash -n "$lib" || die "reconhawx_run_base_update_pre_apply_hooks: generated kubectl wrapper is invalid (${lib})"

  local _c _b
  _c="$(printf '%s' "$cver" | tr -d ' \t\r\n')"
  _b="$(printf '%s' "$bver" | tr -d ' \t\r\n')"
  export RECONHAWX_NS="$ns"
  export RECONHAWX_CLUSTER_VERSION="${_c:-}"
  export RECONHAWX_BUNDLE_VERSION="${_b:-}"
  export RECONHAWX_PRE_APPLY_LIB="$lib"

  # Run hooks in this shell (not a subshell) so ui_step / stderr behave like the rest of the upgrade.
  for h in "${hooks[@]}"; do
    [[ -f "$h" ]] || continue
    ui_step "Kubernetes: pre-apply hook $(basename "$h")"
    if ! bash -euo pipefail "$h"; then
      printf '%spre-apply hook failed: %s%s\n' "${_R:-}" "$h" "${_Z:-}" >&2
      rm -f "$lib"
      unset RECONHAWX_PRE_APPLY_LIB
      die "Pre-apply hooks aborted."
    fi
    ui_ok "Finished $(basename "$h")"
  done

  rm -f "$lib"
  unset RECONHAWX_PRE_APPLY_LIB
  reconhawx__pre_apply_log "all hooks finished."
}

# Sync kubernetes/base/frontend/frontend-ingress.yaml host rule from the live Ingress so
# upgrades do not re-apply a repo-default host (e.g. reconhawx.local) over a custom install.
# Args: BASE_SRC (kubernetes/base path), namespace, then kubectl argv prefix (e.g. kubectl or
# minikube -p PROFILE kubectl --). No-op if manifest or ingress is missing or host is empty.
reconhawx_sync_frontend_ingress_manifest_from_cluster() {
  local base_dir="$1" ns="$2" ing_file cluster_host otmp
  shift 2
  ing_file="$base_dir/frontend/frontend-ingress.yaml"
  [[ -f "$ing_file" ]] || return 0
  cluster_host="$("$@" get ingress frontend-ingress -n "$ns" -o jsonpath='{.spec.rules[0].host}' 2>/dev/null || true)"
  cluster_host="$(printf '%s' "$cluster_host" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -n "$cluster_host" ]] || return 0
  otmp="$(mktemp)"
  awk -v h="$cluster_host" '/^  - host: / { print "  - host: " h; next } { print }' "$ing_file" >"$otmp"
  mv "$otmp" "$ing_file"
  ui_note "frontend-ingress.yaml host synced from cluster: ${cluster_host}"
}

reconhawx_manifest_bundle_version() {
  local root="$1"
  local vf="$root/kubernetes/base/config/reconhawx-version.yaml"
  if [[ ! -f "$vf" ]]; then
    printf ''
    return 0
  fi
  grep '^[[:space:]]*APP_VERSION:' "$vf" | head -1 | sed 's/^[^:]*:[[:space:]]*//;s/"//g;s/#.*//;s/[[:space:]]*$//' | tr -d '\r\n'
}
