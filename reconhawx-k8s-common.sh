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
#
# Usage
# -----
# From the repo root (same directory as this file):
#   source "$REPO_ROOT/reconhawx-k8s-common.sh"
#
# The caller must define: die(), require_cmd(). If download path runs, it also
# calls ui_step, ui_ok, ui_note — define those for consistent installer-style
# output, or stub them if you need a silent/tooling caller.
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
    RECONHAWX_INSTALL_FROM_RELEASE=0
    RECONHAWX_SOURCE_TREE_ROOT="$REPO_ROOT"
  fi
}

reconhawx_base_update_dir() {
  local base_dir="$1"
  local upd
  upd="$(cd "$base_dir/.." && pwd)/base-update"
  [[ -d "$upd" ]] || die "missing ${upd} (kubernetes/base-update must sit next to kubernetes/base)"
  printf '%s' "$upd"
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
