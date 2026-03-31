# Installation on minikube

## 1. Install and start minikube

```shell
minikube -p reconhawx start

😄  [reconhawx] minikube v1.38.1 on Nixos 26.05
    ▪ MINIKUBE_WANTUPDATENOTIFICATION=false
✨  Automatically selected the docker driver. Other choices: kvm2, ssh
❗  Starting v1.39.0, minikube will default to "containerd" container runtime. See #21973 for more info.
📌  Using Docker driver with root privileges
👍  Starting "reconhawx" primary control-plane node in "reconhawx" cluster
🚜  Pulling base image v0.0.50 ...
🔥  Creating docker container (CPUs=2, Memory=7900MB) ...
🐳  Preparing Kubernetes v1.35.1 on Docker 29.2.1 ...
🔗  Configuring bridge CNI (Container Networking Interface) ...
🔎  Verifying Kubernetes components...
    ▪ Using image gcr.io/k8s-minikube/storage-provisioner:v5
🌟  Enabled addons: storage-provisioner, default-storageclass
🏄  Done! kubectl is now configured to use "reconhawx" cluster and "default" namespace by default
```

## 2. Set label on the minikube node

```shell
kubectl label node reconhawx reconhawx.runner=true
kubectl label node reconhawx reconhawx.worker=true
```

## 3. Install kueue on the minikube cluster

```shell
kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/manifests.yaml
kubectl apply --server-side -f https://github.com/kubernetes-sigs/kueue/releases/download/v0.11.1/visibility-apf.yaml
kubectl wait deploy/kueue-controller-manager -nkueue-system --for=condition=available --timeout=5m
```

## 4. Install nginx ingress controller on the minikube cluster

```shell
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.14.2/deploy/static/provider/cloud/deploy.yaml
```

## 5. Create a namespace for the reconhawx application

```shell
kubectl create namespace reconhawx
```

## 6. Create Secrets Manifests

```shell
# Copy example files
cp kubernetes/base/secrets/jwt-secret.yaml.example kubernetes/base/secrets/jwt-secret.yaml
cp kubernetes/base/secrets/postgres-secret.yaml.example kubernetes/base/secrets/postgres-secret.yaml

# Generate random secrets
sed -i "s/JWT_SECRET_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/jwt-secret.yaml
sed -i "s/REFRESH_SECRET_KEY_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/jwt-secret.yaml
sed -i "s/POSTGRES_PASSWORD_PLACEHOLDER/`echo -n \"$(openssl rand -hex 32)\" | base64 -w0`/" kubernetes/base/secrets/postgres-secret.yaml
```

## 7. Install the reconhawx application on the minikube cluster

```shell
kubectl apply -k kubernetes/base/
```

## 8. Wait for the postgresql pod to be ready and get admin password from the postgresql pod

```shell
kubectl wait deploy/postgresql -n reconhawx --for=condition=available --timeout=5m
kubectl logs deploy/postgresql -n reconhawx | grep -A4 "ADMIN USER CREATED"
```

## 9. Start Minikube tunnel (in a separate terminal)

```shell
minikube -p reconhawx tunnel
```

## 10. Get Ingress IP and set hosts file

```shell
kubectl get ingress -n reconhawx

NAME               CLASS   HOSTS             ADDRESS          PORTS   AGE
frontend-ingress   nginx   reconhawx.local   10.106.114.192   80      30m

echo "10.106.114.192 reconhawx.local" | sudo tee -a /etc/hosts
```

## 11. Browse http://reconhawx.local