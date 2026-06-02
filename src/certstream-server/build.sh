#!/usr/bin/env bash

registry="${1:?Usage: $0 <registry> <arch> [tag]}"
arch="${2:?Usage: $0 <registry> <arch> [tag]}"
tag="${3:-1.6.0}"
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
  --build-arg CERTSTREAM_GIT_COMMIT="${CERTSTREAM_GIT_COMMIT:-b19cba80d285ee0f63f2d8aac15e9d930433593a}" \
  -f ./Dockerfile "${docker_tags[@]}" . ${image_dest}
