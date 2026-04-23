#!/usr/bin/env python3
"""Normalize Grafana dashboard JSON for Reconhawx (Loki by datasource name). See --help."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def _strip_export_metadata(root: dict[str, Any]) -> None:
    for k in ("__inputs", "__requires", "__elements"):
        root.pop(k, None)


def _normalize_loki_datasource_ref(
    ds: Any, *, loki_name: str, loki_type: str
) -> Any:
    """Return a {type, name} ref for Loki; leave other datasource refs unchanged."""
    if isinstance(ds, str):
        s = ds.strip()
        if s in ("${DS_LOKI}",) or s == "DS_LOKI" or s == loki_name:
            return {"type": loki_type, "name": loki_name}
        return ds
    if not isinstance(ds, dict):
        return ds
    if ds.get("type") != loki_type:
        return ds
    # Bind Loki by Helm provisioned name (avoids UID mismatch after import).
    return {"type": loki_type, "name": loki_name}


def _walk(obj: Any, *, loki_name: str, loki_type: str) -> None:
    if isinstance(obj, dict):
        if "datasource" in obj:
            obj["datasource"] = _normalize_loki_datasource_ref(
                obj["datasource"], loki_name=loki_name, loki_type=loki_type
            )
        for v in obj.values():
            _walk(v, loki_name=loki_name, loki_type=loki_type)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, loki_name=loki_name, loki_type=loki_type)


def _replace_placeholder_strings(obj: Any, placeholder: str, loki_name: str) -> None:
    """Replace stray ${DS_LOKI} strings in case they appear outside datasource objects."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if isinstance(v, str) and placeholder in v:
                obj[k] = v.replace(placeholder, loki_name)
            else:
                _replace_placeholder_strings(v, placeholder, loki_name)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and placeholder in item:
                obj[i] = item.replace(placeholder, loki_name)
            else:
                _replace_placeholder_strings(item, placeholder, loki_name)


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Normalize a Grafana dashboard export for kube-prometheus-stack: strip __inputs/__requires, "
            "rewrite Loki datasource refs to {type, name} (default name Loki), optional stable uid and tags."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 reconhawx-grafana-dashboard-normalize.py export.json -o kubernetes/observability/dashboards/x.json\n"
            "  python3 reconhawx-grafana-dashboard-normalize.py export.json --dry-run | jq .\n"
            "Docs: kubernetes/observability/README.md (Dashboards)."
        ),
    )
    p.add_argument("input", help="Exported dashboard .json path (or - for stdin)")
    p.add_argument("-o", "--output", help="Write normalized JSON here (default: stdout)")
    p.add_argument("--loki-name", default="Loki", help='Grafana datasource name (default: "Loki")')
    p.add_argument("--loki-type", default="loki", help="Datasource plugin id (default: loki)")
    p.add_argument("--dashboard-uid", help="Set top-level dashboard uid")
    p.add_argument("--add-tag", action="append", default=[], help="Ensure tag present (repeatable)")
    p.add_argument(
        "--no-default-tag",
        action="store_true",
        help="Do not add the reconhawx tag automatically",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and normalize only; print to stdout (ignores -o)",
    )
    args = p.parse_args()

    raw = sys.stdin.read() if args.input == "-" else open(args.input, encoding="utf-8").read()
    data: dict[str, Any] = json.loads(raw)

    if not isinstance(data, dict):
        print("error: root JSON must be an object", file=sys.stderr)
        return 1

    _strip_export_metadata(data)
    _walk(data, loki_name=args.loki_name, loki_type=args.loki_type)
    _replace_placeholder_strings(data, "${DS_LOKI}", args.loki_name)

    tags = list(data.get("tags") or [])
    tag_set = {str(t) for t in tags}
    if not args.no_default_tag and "reconhawx" not in tag_set:
        tags.append("reconhawx")
        tag_set.add("reconhawx")
    for t in args.add_tag:
        if t and t not in tag_set:
            tags.append(t)
            tag_set.add(t)
    if tags:
        data["tags"] = tags

    if args.dashboard_uid:
        data["uid"] = args.dashboard_uid

    out = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.dry_run or not args.output:
        sys.stdout.write(out)
    else:
        open(args.output, "w", encoding="utf-8").write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
