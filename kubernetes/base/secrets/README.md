# Kubernetes Secrets

The base manifests expect two secrets in the `recon` namespace. Template files are provided here — copy them, fill in real values, and apply before deploying.

## Setup

```bash
cd kubernetes/base/secrets/

# 1. JWT secret (API authentication)
cp jwt-secret.yaml.example jwt-secret.yaml
# Edit jwt-secret.yaml — generate keys with: echo -n "$(openssl rand -hex 32)" | base64 -w0

# 2. PostgreSQL credentials
cp postgres-secret.yaml.example postgres-secret.yaml
# Edit postgres-secret.yaml — encode values with: echo -n 'value' | base64 -w0

# 3. Apply
kubectl apply -f jwt-secret.yaml -n recon
kubectl apply -f postgres-secret.yaml -n recon
```

## Optional: internal-service-secret

Some services reference an `internal-service-secret` for inter-service API keys. This secret is marked `optional: true` in all deployments, so it is not required for basic operation. Create it if you need authenticated service-to-service calls:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: internal-service-secret
type: Opaque
data:
  token: <base64-encoded-api-key>
```
