#!/usr/bin/env bash

registry="${1:?Usage: $0 <registry> <arch> [tag]}"
arch="${2:?Usage: $0 <registry> <arch> [tag]}"
tag="${3:-latest}"
service_name=$(basename "$(pwd)")

if [ "$registry" == "minikube" ]; then
    image_tag="${service_name}:latest"
    image_dest="--load"
    docker_tags=( -t "${image_tag}" )
    eval $(minikube -p dev docker-env)
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

docker buildx build --platform "${arch}" \
  --builder "${BUILDX_BUILDER:-multiarch-builder}" \
  --build-arg APP_VERSION="${APP_VERSION:-dev}" \
  -f ./Dockerfile "${docker_tags[@]}" . ${image_dest}
