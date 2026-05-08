#!/usr/bin/env python3
"""Run WPScan and treat ``scan_aborted`` / known-good JSON as success for worker exit status.

WPScan exits non-zero (e.g. 4) when the site is up but not WordPress, while still emitting
valid JSON with ``target_url``. ``command_wrapper.py`` forwards the child exit code to the
Kubernetes Job; this wrapper exits 0 when that JSON envelope is present so the step does not
fail spuriously.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys

from worker_logging import configure_worker_logging

configure_worker_logging()
logger = logging.getLogger(__name__)


def _wpscan_json_has_target(stdout: str) -> bool:
    if not stdout or not stdout.strip():
        return False
    try:
        data = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return bool(
        data.get("target_url") or data.get("url") or data.get("effective_url")
    )


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        logger.error("wpscan_wrapper: no arguments (expected wpscan CLI args)")
        sys.exit(2)

    cmd = ["wpscan", *argv]
    logger.info("wpscan_wrapper invoking: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if proc.stdout:
        sys.stdout.write(proc.stdout)
        sys.stdout.flush()
    if proc.stderr:
        sys.stderr.write(proc.stderr)
        sys.stderr.flush()

    rc = proc.returncode or 0
    if rc == 0:
        sys.exit(0)

    if _wpscan_json_has_target(proc.stdout or ""):
        logger.info(
            "wpscan exited %s but produced parseable JSON with a target URL; "
            "treating as success for worker exit status",
            rc,
        )
        sys.exit(0)

    sys.exit(rc)


if __name__ == "__main__":
    main()
