"""Shared stop/cancel flag for batch jobs (set by SIGTERM/SIGINT in run-job.py)."""

job_stopped_externally = False


def request_job_stop() -> None:
    global job_stopped_externally
    job_stopped_externally = True


def is_job_stopped() -> bool:
    return job_stopped_externally


class JobStoppedExternally(Exception):
    """Raised when a batch job should exit cooperatively after external stop."""
