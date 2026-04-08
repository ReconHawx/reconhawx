#!/usr/bin/env python3
"""Set Kueue ClusterQueue nominalQuota from nodes labeled reconhawx.runner / reconhawx.worker.

Uses server-side apply with --force-conflicts so .spec.resourceGroups can replace values from
an earlier client-side kubectl apply -k (field manager kubectl-client-side-apply).

- worker-cluster-queue: sum of worker allocatable (after reserve).
- runner-cluster-queue: runner allocatable (after reserve) minus one AI analysis job slot.
- ai-analysis-cluster-queue: fixed to one Job's resource requests (default 500m CPU, 512Mi memory),
  matching create_ai_analysis_batch_job in src/api/app/services/job_submission.py.

Usage:
  reconhawx-kueue-quota-sync.py [kubectl-prefix-args...]

If no args, uses \"kubectl\". Examples:
  reconhawx-kueue-quota-sync.py
  reconhawx-kueue-quota-sync.py minikube -p reconhawx kubectl --

Env:
  RECONHAWX_KUEUE_RESERVE_PCT          Reserve fraction 0–100 (default 7) applied per role sum.
  RECONHAWX_KUEUE_AI_ANALYSIS_CPU      Override AI queue CPU nominalQuota (default 500m).
  RECONHAWX_KUEUE_AI_ANALYSIS_MEMORY   Override AI queue memory nominalQuota (default 512Mi).
"""

from __future__ import annotations

_EPILOG = """Environment variables:
  RECONHAWX_KUEUE_RESERVE_PCT          Reserve %% 0–100 (default 7) applied per role sum.
  RECONHAWX_KUEUE_AI_ANALYSIS_CPU      AI queue CPU nominalQuota (default 500m).
  RECONHAWX_KUEUE_AI_ANALYSIS_MEMORY   AI queue memory nominalQuota (default 512Mi)."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


def parse_cpu_millicores(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    if s.endswith("m"):
        return int(s[:-1])
    v = float(s)
    return int(round(v * 1000))


def parse_mem_bytes(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    suf = {
        "Ki": 1024,
        "Mi": 1024**2,
        "Gi": 1024**3,
        "Ti": 1024**4,
        "K": 1000,
        "M": 1000**2,
        "G": 1000**3,
        "T": 1000**4,
    }
    for k, mul in suf.items():
        if s.endswith(k):
            return int(float(s[: -len(k)]) * mul)
    return int(s)


def sum_allocatable(data: dict) -> tuple[int, int]:
    items = data.get("items") or []
    t_cpu, t_mem = 0, 0
    for node in items:
        if node.get("spec", {}).get("unschedulable"):
            continue
        alloc = node.get("status", {}).get("allocatable") or {}
        c, m = alloc.get("cpu"), alloc.get("memory")
        if not c or not m:
            continue
        t_cpu += parse_cpu_millicores(c)
        t_mem += parse_mem_bytes(m)
    return t_cpu, t_mem


def format_cpu_nominal(mcpu: int) -> str:
    if mcpu <= 0:
        return "1m"
    if mcpu % 1000 == 0:
        return str(mcpu // 1000)
    return f"{mcpu}m"


def format_mem_nominal(b: int) -> str:
    if b <= 0:
        return "1Mi"
    gib = b / (1024**3)
    if gib >= 1:
        rounded = round(gib)
        if abs(gib - rounded) < 1e-9:
            return f"{int(rounded)}Gi"
    mib = b / (1024**2)
    return f"{max(1, int(round(mib)))}Mi"


def apply_reserve(mcpu: int, mem: int, pct: float) -> tuple[int, int]:
    r = max(0.0, min(100.0, pct))
    f = (100.0 - r) / 100.0
    return int(mcpu * f), int(mem * f)


def kubectl_json(kubectl_cmd: list[str], *kubectl_args: str) -> dict:
    r = subprocess.run(
        [*kubectl_cmd, *kubectl_args],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        die(
            f"kubectl failed ({r.returncode}): {' '.join(kubectl_cmd)} …\n"
            f"{r.stderr or r.stdout}"
        )
    return json.loads(r.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Size ReconHawx Kueue ClusterQueues from labeled node allocatable.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # REMAINDER (not "*"): prefix may include flags like "minikube -p NAME kubectl --",
    # which argparse would otherwise treat as its own options.
    parser.add_argument(
        "kubectl",
        nargs=argparse.REMAINDER,
        metavar="ARG",
        help="kubectl invocation prefix (default: kubectl)",
    )
    args = parser.parse_args()
    kubectl_cmd = args.kubectl if args.kubectl else ["kubectl"]

    runner_data = kubectl_json(kubectl_cmd, "get", "nodes", "-l", "reconhawx.runner=true", "-o", "json")
    worker_data = kubectl_json(kubectl_cmd, "get", "nodes", "-l", "reconhawx.worker=true", "-o", "json")

    rs_cpu, rs_mem = sum_allocatable(runner_data)
    ws_cpu, ws_mem = sum_allocatable(worker_data)

    if not (runner_data.get("items") or []):
        die("reconhawx-kueue-quota-sync: no nodes labeled reconhawx.runner=true")
    if rs_cpu <= 0 or rs_mem <= 0:
        die("reconhawx-kueue-quota-sync: zero CPU/memory allocatable on runner-labeled nodes")
    if not (worker_data.get("items") or []):
        die("reconhawx-kueue-quota-sync: no nodes labeled reconhawx.worker=true")
    if ws_cpu <= 0 or ws_mem <= 0:
        die("reconhawx-kueue-quota-sync: zero CPU/memory allocatable on worker-labeled nodes")

    try:
        reserve = float(os.environ.get("RECONHAWX_KUEUE_RESERVE_PCT", "7"))
    except ValueError:
        die("RECONHAWX_KUEUE_RESERVE_PCT must be a number")

    ai_cpu_s = os.environ.get("RECONHAWX_KUEUE_AI_ANALYSIS_CPU", "500m").strip()
    ai_mem_s = os.environ.get("RECONHAWX_KUEUE_AI_ANALYSIS_MEMORY", "512Mi").strip()
    ai_mcpu = parse_cpu_millicores(ai_cpu_s)
    ai_mem_b = parse_mem_bytes(ai_mem_s)
    if ai_mcpu <= 0 or ai_mem_b <= 0:
        die("Invalid RECONHAWX_KUEUE_AI_ANALYSIS_CPU / RECONHAWX_KUEUE_AI_ANALYSIS_MEMORY")

    r_cpu, r_mem = apply_reserve(rs_cpu, rs_mem, reserve)
    w_cpu, w_mem = apply_reserve(ws_cpu, ws_mem, reserve)

    runner_cq_mcpu = r_cpu - ai_mcpu
    runner_cq_mem = r_mem - ai_mem_b
    if runner_cq_mcpu <= 0 or runner_cq_mem <= 0:
        die(
            "reconhawx-kueue-quota-sync: runner capacity after reserve is too small for one AI analysis job "
            f"(runner after reserve: cpu={r_cpu}m mem={r_mem}B; need ai slot: cpu={ai_mcpu}m mem={ai_mem_b}B). "
            "Add runner nodes or lower RECONHAWX_KUEUE_RESERVE_PCT."
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def cq(name: str, flavor: str, cpu: str, mem: str) -> str:
        return f"""apiVersion: kueue.x-k8s.io/v1beta1
kind: ClusterQueue
metadata:
  name: "{name}"
  annotations:
    reconhawx.io/kueue-quotas-synced-at: "{stamp}"
spec:
  namespaceSelector: {{}}
  resourceGroups:
  - coveredResources: ["cpu", "memory"]
    flavors:
    - name: "{flavor}"
      resources:
      - name: "cpu"
        nominalQuota: {cpu}
      - name: "memory"
        nominalQuota: {mem}
"""

    ai_cpu_out = ai_cpu_s or format_cpu_nominal(ai_mcpu)
    ai_mem_out = ai_mem_s or format_mem_nominal(ai_mem_b)
    manifest = "\n---\n".join(
        [
            cq("worker-cluster-queue", "worker-flavor", format_cpu_nominal(w_cpu), format_mem_nominal(w_mem)),
            cq("runner-cluster-queue", "runner-flavor", format_cpu_nominal(runner_cq_mcpu), format_mem_nominal(runner_cq_mem)),
            cq("ai-analysis-cluster-queue", "runner-flavor", ai_cpu_out, ai_mem_out),
        ]
    )

    r = subprocess.run(
        [
            *kubectl_cmd,
            "apply",
            "--server-side",
            "--field-manager=reconhawx-kueue-quota-sync",
            "--force-conflicts",
            "-f",
            "-",
        ],
        input=manifest.encode(),
        capture_output=True,
    )
    if r.returncode != 0:
        print(r.stderr.decode() or r.stdout.decode(), file=sys.stderr)
        die("kubectl apply failed")


if __name__ == "__main__":
    main()
