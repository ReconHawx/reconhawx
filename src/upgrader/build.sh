#!/usr/bin/env bash
# Copy repo-root files into build context then docker buildx (same contract as src/migrations/build.sh).
set -euo pipefail

registry="${1:?Usage: $0 <registry> <arch> [tag]}"
arch="${2:?Usage: $0 <registry> <arch> [tag]}"
tag="${3:-latest}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"

cp -f "$repo_root/reconhawx-k8s-common.sh" "$here/reconhawx-k8s-common.sh"
cp -f "$repo_root/reconhawx-kueue-quota-sync.py" "$here/reconhawx-kueue-quota-sync.py"
cp -f "$repo_root/reconhawx-observability-helm.sh" "$here/reconhawx-observability-helm.sh"

service_name=$(basename "$here")

if [ "$registry" == "minikube" ]; then
  image_tag="ghcr.io/reconhawx/reconhawx/${service_name}:latest"
  image_dest="--load"
  docker_tags=( -t "${image_tag}" )
  eval "$(minikube -p dev docker-env)"
else
  image_tag="${registry}/${service_name}:${tag}"
  image_dest="--push"
  docker_tags=( -t "${image_tag}" )
  if [ -n "${IMAGE_EXTRA_TAGS:-}" ]; then
    for extra in ${IMAGE_EXTRA_TAGS}; do
      docker_tags+=( -t "${registry}/${service_name}:${extra}" )
    done
  fi
fi

cd "$here"
docker buildx build --platform "${arch}" \
  --builder "${BUILDX_BUILDER:-multiarch-builder}" \
  -f ./Dockerfile "${docker_tags[@]}" . ${image_dest}
