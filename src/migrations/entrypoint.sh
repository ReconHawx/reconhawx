#!/usr/bin/env sh
set -eu
exec python -m migrations.k8s_entrypoint
