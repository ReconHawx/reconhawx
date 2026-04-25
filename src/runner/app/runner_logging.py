"""Shared logging setup for runner entrypoints (run-workflow.py, run-job.py)."""

from __future__ import annotations

import logging
import os

from recon_log_format import apply_service_logging, parse_log_level


def configure_runner_logging() -> None:
    """Configure root logging once; honor LOG_LEVEL / LOG_FORMAT; tune noisy libraries."""
    apply_service_logging(
        service="runner",
        include_uvicorn=False,
        log_format=os.getenv("LOG_FORMAT"),
        root_level=parse_log_level(os.getenv("LOG_LEVEL"), logging.INFO),
        text_format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        text_datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("task_executor").setLevel(logging.DEBUG)
    logging.getLogger("recon_tasks").setLevel(logging.DEBUG)
    logging.getLogger("batch_jobs").setLevel(logging.DEBUG)
    logging.getLogger("task_queue_client").setLevel(logging.DEBUG)
    logging.getLogger("kubernetes").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
