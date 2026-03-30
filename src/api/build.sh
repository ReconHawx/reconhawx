#!/usr/bin/env bash

registry="${1}"
if [ -z "$registry" ]; then
    echo "Usage: $0 <registry> <arch> [tag]"
    exit 1
fi

arch="${2}"
if [ -z "$arch" ]; then
    echo "Usage: $0 <registry> <arch> [tag]"
    exit 1
fi

tag="${3:-latest}"

temp_dir=$(mktemp -d)

service_name=$(basename $(pwd))

rsync -a --no-links ./app/ $temp_dir
cp Dockerfile $temp_dir
cp requirements.txt $temp_dir
cp setup_nuclei_templates.sh $temp_dir
cp update_nuclei_templates.py $temp_dir
cp generate_nuclei_tree.py $temp_dir
#cp -r ../common $temp_dir/common

if [ "$registry" == "minikube" ]; then
    image_tag="${service_name}:latest"
    image_dest="--load"
    docker_tags=( -t "${image_tag}" )
    eval $(minikube -p dev docker-env)
    echo "Using minikube registry"
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

pushd $temp_dir
docker buildx build --platform "${arch}" --builder "${BUILDX_BUILDER:-multiarch-builder}" -f ./Dockerfile "${docker_tags[@]}" . ${image_dest}
popd

rm -rf $temp_dir
