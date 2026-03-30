---
name: kubernetes-deploy
description: >-
  Builds and deploys Recon services to Kubernetes/k3s using scripts/deploy.py and kubernetes/
  overlays (including Kueue-related ordering). Use when the user mentions deploy, kubectl,
  kustomize, environments (dev/prod), or cluster operations for this project.
---

# Kubernetes deploy (Recon)

## Before you start

Read **`AGENTS.md`** for the canonical command cheat sheet. Narrative and examples: **`scripts/README.md`**, **`kubernetes/README.md`**. Long-form ordering and kubectl snippets: **`.cursor/rules/kubernetes-deployment-operations.mdc`**.

Requires **Docker**, **kubectl**, and Python deps **`rich`**, **`pyyaml`** for `scripts/deploy.py`.

## Common commands

From the repository root:

```bash
python scripts/deploy.py -e dev d all
python scripts/deploy.py -e dev d api
python scripts/deploy.py -e dev bd api
```

Public deployment uses `kubectl apply -k kubernetes/base/` directly (see `kubernetes/README.md`). Internal environments use overlays under `kubernetes/overlays/` (gitignored).

## Dependency order

When applying infra manually, respect ordering: core datastores and messaging (e.g. postgresql, redis, nats), **Kueue** if used, config, then application deployments, then job templates. Details are in the k8s deployment rule.

## After changes

If deploy flags, overlay paths, or ordering change, update **`AGENTS.md`** and/or the relevant README or `.mdc` in the same change (see PR template).
