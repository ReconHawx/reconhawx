#!/usr/bin/env bash

# Get kubeconfig from environment or use default
KUBECONFIG=${KUBECONFIG:-"$HOME/.kube/config"}

# Clean up existing resources first
echo "Cleaning up existing ingress-nginx resources..."
kubectl --kubeconfig "$KUBECONFIG" delete namespace ingress-nginx --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG" delete clusterrole ingress-nginx --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG" delete clusterrolebinding ingress-nginx --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG" delete validatingwebhookconfiguration ingress-nginx-admission --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG" delete mutatingwebhookconfiguration ingress-nginx-admission --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG" delete crd ingressclassparams.networking.k8s.io --ignore-not-found
kubectl --kubeconfig "$KUBECONFIG" delete ingressclass nginx --ignore-not-found

# Wait for resources to be cleaned up
sleep 10

# Create namespace for nginx-ingress
kubectl --kubeconfig "$KUBECONFIG" create namespace ingress-nginx

# Add the ingress-nginx repository
helm --kubeconfig "$KUBECONFIG" repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm --kubeconfig "$KUBECONFIG" repo update

# Install the ingress-nginx controller with increased timeout and additional configuration
echo "Installing ingress-nginx controller..."
helm --kubeconfig "$KUBECONFIG" upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --set controller.service.type=LoadBalancer \
  --set controller.ingressClassResource.default=true \
  --set controller.ingressClassResource.name=nginx \
  --set controller.ingressClassResource.enabled=true \
  --set controller.ingressClassResource.controllerValue="k8s.io/ingress-nginx" \
  --set controller.admissionWebhooks.enabled=false \
  --set controller.metrics.enabled=false \
  --set controller.resources.requests.cpu=100m \
  --set controller.resources.requests.memory=90Mi \
  --set controller.resources.limits.cpu=200m \
  --set controller.resources.limits.memory=180Mi \
  --timeout 5m

# Wait for the controller pod to be ready
echo "Waiting for ingress-nginx controller to be ready..."
kubectl --kubeconfig "$KUBECONFIG" wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=300s

# Verify the installation
echo "Verifying installation..."
kubectl --kubeconfig "$KUBECONFIG" get pods -n ingress-nginx
kubectl --kubeconfig "$KUBECONFIG" get svc -n ingress-nginx
kubectl --kubeconfig "$KUBECONFIG" get ingressclass nginx 