"""Structured logging for worker (command_wrapper and task scripts).

Worker subprocess stdout is captured to NATS as task output; all application logs
must go to stderr so they never mix into the published payload. This module
always uses stream=stderr.
"""

from __future__ import annotations

import logging
import os

from recon_log_format import apply_service_logging, parse_log_level


def configure_worker_logging() -> None:
    """Configure root logging once; honor LOG_LEVEL / LOG_FORMAT; logs to stderr only."""
    apply_service_logging(
        service="worker",
        include_uvicorn=False,
        log_format=os.getenv("LOG_FORMAT"),
        root_level=parse_log_level(os.getenv("LOG_LEVEL"), logging.INFO),
        text_format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        text_datefmt="%Y-%m-%d %H:%M:%S",
        stream="ext://sys.stderr",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    # nats-py is chatty on DEBUG
    logging.getLogger("nats").setLevel(logging.INFO)
