#!/usr/bin/env bash

kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/manifests.yaml
kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/visibility-apf.yaml
kubectl wait deploy/kueue-controller-manager -nkueue-system --for=condition=available --timeout=5m