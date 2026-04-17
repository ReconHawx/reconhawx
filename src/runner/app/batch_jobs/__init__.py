"""Batch job handlers dispatched by ``run-job.py``.

Each module defines a standalone task class (e.g. ``PhishLabsBatchTask``,
``GatherApiFindingsTask``) that is instantiated directly by ``run-job.py``
based on the incoming ``job_type``. Unlike ``recon_tasks`` these are not
registered in ``TaskRegistry`` and do not participate in workflow execution.
"""
