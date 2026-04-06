#!/usr/bin/env bash
# Drop legacy Deployment/postgresql before applying StatefulSet manifests.
# Idempotent: no-op if StatefulSet already exists or Deployment absent.
set -euo pipefail

: "${RECONHAWX_NS:?}"

if [[ -n "${RECONHAWX_PRE_APPLY_LIB:-}" ]] && [[ -f "$RECONHAWX_PRE_APPLY_LIB" ]]; then
  # shellcheck source=/dev/null
  source "$RECONHAWX_PRE_APPLY_LIB"
else
  reconhawx_kubectl() { kubectl -n "$RECONHAWX_NS" "$@"; }
fi

if reconhawx_kubectl get statefulset postgresql &>/dev/null; then
  printf 'pre-apply: statefulset/postgresql already exists; skipping legacy Deployment cleanup.\n' >&2
  exit 0
fi

printf 'pre-apply: removing legacy deployment/postgresql if present (namespace %s).\n' "$RECONHAWX_NS" >&2
reconhawx_kubectl delete deployment postgresql --ignore-not-found

# Wait for app=postgresql pods to terminate so RWO PVC can attach to postgresql-0.
local_wait=120
step=2
elapsed=0
next_note=0
while reconhawx_kubectl get pods -l app=postgresql -o name 2>/dev/null | grep -q .; do
  if [[ "$elapsed" -ge "$local_wait" ]]; then
    printf 'pre-apply: timeout after %ds waiting for postgresql-labeled pods to exit in namespace %s\n' "$local_wait" "$RECONHAWX_NS" >&2
    reconhawx_kubectl get pods -l app=postgresql -o wide >&2 || true
    exit 1
  fi
  if [[ "$elapsed" -ge "$next_note" ]]; then
    printf 'pre-apply: waiting for postgresql-labeled pods to finish terminating (%ds / %ds) …\n' "$elapsed" "$local_wait" >&2
    reconhawx_kubectl get pods -l app=postgresql -o wide 2>/dev/null | head -5 >&2 || true
    next_note=$((next_note + 15))
  fi
  sleep "$step"
  elapsed=$((elapsed + step))
done
printf 'pre-apply: no postgresql-labeled pods left; continuing upgrade apply.\n' >&2

exit 0
