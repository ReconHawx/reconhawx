# One-shot cluster upgrade Job image (kubectl apply -k base-update + rollouts).
FROM alpine:3.19

# busybox (base) provides awk/grep/sed; no standalone awk package on Alpine.
RUN apk add --no-cache \
    bash \
    curl \
    tar \
    jq \
    python3 \
    py3-pip \
    coreutils \
    kubectl \
    helm \
    openssl \
    && rm -rf /root/.kube

WORKDIR /opt/reconhawx

COPY upgrade.sh reconhawx-k8s-common.sh reconhawx-kueue-quota-sync.py reconhawx-observability-helm.sh ./
RUN chmod +x upgrade.sh

ENTRYPOINT ["/opt/reconhawx/upgrade.sh"]
