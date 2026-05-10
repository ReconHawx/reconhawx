---
name: kubernetes-deploy
description: >-
  Builds and deploys Recon services: local Minikube uses scripts/deploy.py (kubectl context dev,
  kubernetes/overlays/dev); other environments use kubectl/kustomize. Use when the user mentions
  deploy, kubectl, kustomize, Minikube, or cluster operations for this project.
---

# Kubernetes deploy (Recon)

## Before you start

Read **`AGENTS.md`** for the canonical command cheat sheet. Narrative and examples: **`scripts/README.md`**, **`kubernetes/README.md`**. Long-form ordering and kubectl snippets: **`.cursor/rules/kubernetes-deployment-operations.mdc`**.

Requires **Docker**, **kubectl**, and Python deps **`rich`**, **`pyyaml`** for `scripts/deploy.py`.

## Common commands

From the repository root (Minikube dev only; **`kubectl` context `dev`**):

```bash
python scripts/deploy.py d all
python scripts/deploy.py d api          # d ignores service arg; same as d
python scripts/deploy.py bd api
```

Public / other clusters: **`kubectl apply -k kubernetes/base/`** or the appropriate overlay—see [`kubernetes/README.md`](../../kubernetes/README.md). Internal dev overlay path: **`kubernetes/overlays/dev`**.

## Dependency order

When applying infra manually, respect ordering: core datastores and messaging (e.g. postgresql, redis, nats), **Kueue** if used, config, then application deployments, then job templates. Details are in the k8s deployment rule.

## Observability (Helm)

Install and scripted upgrade helpers ([`install-kubernetes.sh`](../../install-kubernetes.sh), [`update-kubernetes.sh`](../../update-kubernetes.sh), Minikube variants) source [`reconhawx-observability-helm.sh`](../../reconhawx-observability-helm.sh) when it sits next to those scripts. Set **`RECONHAWX_OBSERVABILITY=0`** to skip Loki / Alloy / Grafana (air-gapped or no Helm). In-cluster **Admin → System upgrade** always runs the same Helm step after rollouts (**strict**; needs chart repo egress unless mirrored).

## After changes

If deploy flags, overlay paths, or ordering change, update **`AGENTS.md`** and/or the relevant README or `.mdc` in the same change (see PR template).
