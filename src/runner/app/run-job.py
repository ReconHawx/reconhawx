#!/usr/bin/env python3
import sys
import json
import os
import asyncio

from runner_logging import configure_runner_logging

configure_runner_logging()

import logging
import aiohttp
from batch_jobs.phishlabs_batch import PhishLabsBatchTask
from batch_jobs.gather_api_findings import GatherApiFindingsTask
from batch_jobs.sync_recordedfuture_data import SyncRecordedFutureDataTask
from batch_jobs.refresh_vendor_intel import RefreshVendorIntelTask
from batch_jobs.ai_analysis_batch import AIAnalysisBatchTask
from services.kubernetes import KubernetesService

logger = logging.getLogger(__name__)


def _capture_batch_job_pod_output(job_id: str) -> str:
    """Capture batch job runner pod output/logs via Kubernetes API."""
    try:
        k8s_service = KubernetesService()
        logs = k8s_service.get_batch_job_pod_logs_by_job_id(job_id)
        return logs if logs else ""
    except Exception as e:
        logger.warning(f"Failed to capture pod output for job {job_id}: {e}")
        return ""


async def _upload_runner_pod_output(job_id: str, pod_output: str) -> None:
    """Append runner pod output to job status via API."""
    api_base_url = os.getenv("API_BASE_URL", "http://api:8000")
    headers = {}
    internal_api_key = os.getenv("INTERNAL_SERVICE_API_KEY")
    if internal_api_key:
        headers["Authorization"] = f"Bearer {internal_api_key}"

    payload = {
        "runner_pod_output": (
            f"\n--- Final Job Output ---\n{pod_output}\n\n--- End Job ---\n"
        ),
    }
    url = f"{api_base_url}/jobs/{job_id}/status"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.put(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    logger.warning(
                        f"Failed to upload runner_pod_output for job {job_id}: "
                        f"{resp.status} {body}"
                    )
                else:
                    logger.info(f"Uploaded runner_pod_output for job {job_id}")
    except Exception as e:
        logger.warning(f"Failed to upload runner_pod_output for job {job_id}: {e}")


async def run_phishlabs_batch_job(job_data: dict):
    """Run a PhishLabs batch job (fetch or create incidents)"""
    try:
        job_id = job_data.get("job_id")
        finding_ids = job_data.get("finding_ids", [])
        user_id = job_data.get("user_id", "unknown")
        action = job_data.get("action", "fetch")  # Default to fetch if not specified
        catcode = job_data.get("catcode")  # Only used for create action
        comment = job_data.get("comment")  # Custom comment for incident creation
        report_to_gsb = job_data.get("report_to_gsb", False)  # Whether to report to Google Safe Browsing

        if not job_id:
            logger.error("Job ID is required")
            return False

        if not finding_ids:
            logger.error("No finding IDs provided")
            return False

        logger.info(f"Starting PhishLabs batch job {job_id} for {len(finding_ids)} findings (action: {action}, GSB: {report_to_gsb})")

        # Create and execute the task
        task = PhishLabsBatchTask(job_id, finding_ids, user_id, action, catcode, comment, report_to_gsb)
        await task.execute()

        logger.info(f"PhishLabs batch job {job_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error running PhishLabs batch job: {str(e)}")
        return False

async def run_gather_api_findings_job(job_data: dict):
    """Run a gather API findings job"""
    try:
        job_id = job_data.get("job_id")
        program_name = job_data.get("program_name")  # Single program from scheduled job
        program_id = job_data.get("program_id")
        user_id = job_data.get("user_id", "unknown")

        # Extract from job_data nested structure
        job_specific_data = job_data.get("job_data", {})
        api_vendor = job_specific_data.get("api_vendor", "threatstream")  # Default to threatstream
        date_range_hours = job_specific_data.get("date_range_hours")  # Optional parameter
        custom_query = job_specific_data.get("custom_query")  # Required for ThreatStream list gather

        # Debug logging
        logger.info(f"DEBUG: Full job_data received: {job_data}")
        logger.info(f"DEBUG: job_specific_data extracted: {job_specific_data}")
        logger.info(f"DEBUG: api_vendor extracted: {api_vendor}")
        logger.info(f"DEBUG: custom_query extracted: {custom_query}")

        if not job_id:
            logger.error("Job ID is required")
            return False

        if not program_name:
            logger.error("Program name is required")
            return False

        if api_vendor == "threatstream":
            if custom_query is None or not str(custom_query).strip():
                logger.error(
                    "gather_api_findings with api_vendor=threatstream requires non-empty job_data.custom_query"
                )
                return False

        logger.info(
            f"Starting gather API findings job {job_id} for program {program_name} "
            f"(program_id={program_id!r}) using {api_vendor}"
        )

        # Create and execute the task
        task = GatherApiFindingsTask(
            job_id,
            program_name,
            user_id,
            api_vendor,
            date_range_hours,
            custom_query,
            program_id=program_id,
        )
        await task.execute()

        logger.info(f"Gather API findings job {job_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error running gather API findings job: {str(e)}")
        return False

async def run_ai_analysis_batch_job(job_data: dict):
    """Run an AI analysis batch job."""
    try:
        job_id = job_data.get("job_id")
        finding_ids = job_data.get("finding_ids", [])
        user_id = job_data.get("user_id", "unknown")
        model = job_data.get("model")
        force = job_data.get("force", False)

        if not job_id:
            logger.error("Job ID is required")
            return False

        if not finding_ids:
            logger.error("No finding IDs provided")
            return False

        logger.info(f"Starting AI analysis batch job {job_id} for {len(finding_ids)} findings")

        task = AIAnalysisBatchTask(job_id, finding_ids, user_id, model=model, force=force)
        await task.execute()

        logger.info(f"AI analysis batch job {job_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error running AI analysis batch job: {str(e)}")
        return False

async def run_sync_recordedfuture_data_job(job_data: dict):
    """Run a RecordedFuture data sync job"""
    try:
        job_id = job_data.get("job_id")
        program_name = job_data.get("program_name")
        user_id = job_data.get("user_id", "unknown")
        sync_options = job_data.get("sync_options", {})

        if not job_id:
            logger.error("Job ID is required")
            return False

        if not program_name:
            logger.error("Program name is required")
            return False

        logger.info(f"Starting RecordedFuture data sync job {job_id} for program: {program_name}")

        # Create and execute the task
        task = SyncRecordedFutureDataTask(job_id, program_name, user_id, sync_options=sync_options)
        await task.execute()

        logger.info(f"RecordedFuture data sync job {job_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error running RecordedFuture data sync job: {str(e)}")
        return False

async def run_refresh_vendor_intel_job(job_data: dict):
    """Run a vendor intel refresh job (Recorded Future or ThreatStream, data-only)."""
    try:
        job_id = job_data.get("job_id")
        program_name = job_data.get("program_name")
        program_id = job_data.get("program_id")
        user_id = job_data.get("user_id", "unknown")
        job_specific = job_data.get("job_data", {}) or {}
        api_vendor = job_specific.get("api_vendor", "recordedfuture")
        refresh_options = job_specific.get("refresh_options", {})

        if not job_id:
            logger.error("Job ID is required")
            return False
        if not program_name:
            logger.error("Program name is required")
            return False
        if api_vendor not in ("recordedfuture", "threatstream"):
            logger.error("api_vendor must be recordedfuture or threatstream")
            return False

        logger.info(
            "Starting refresh vendor intel job %s for program %s vendor=%s",
            job_id,
            program_name,
            api_vendor,
        )

        task = RefreshVendorIntelTask(
            job_id,
            program_name,
            user_id,
            api_vendor=api_vendor,
            program_id=program_id,
            refresh_options=refresh_options,
        )
        await task.execute()

        logger.info(f"Refresh vendor intel job {job_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error running refresh vendor intel job: {str(e)}")
        return False

async def main():
    """Main entry point for job execution"""
    job_id = None
    exit_code = 1
    try:
        # Read job data from file
        job_data_path = "/app/job-data/job_data.json"
        
        if not os.path.exists(job_data_path):
            logger.error(f"Job data file not found: {job_data_path}")
            sys.exit(1)
        
        with open(job_data_path, 'r') as f:
            job_data = json.load(f)
        
        job_id = job_data.get("job_id")
        job_type = job_data.get("job_type")
        logger.info(f"Starting job of type: {job_type}")
        
        success = False
        
        if job_type == "phishlabs_batch":
            success = await run_phishlabs_batch_job(job_data)
        elif job_type == "phishlabs_incidents_batch":
            success = await run_phishlabs_batch_job(job_data)
        elif job_type == "ai_analysis_batch":
            success = await run_ai_analysis_batch_job(job_data)
        elif job_type == "gather_api_findings":
            success = await run_gather_api_findings_job(job_data)
        elif job_type == "sync_recordedfuture_data":
            success = await run_sync_recordedfuture_data_job(job_data)
        elif job_type == "refresh_vendor_intel":
            success = await run_refresh_vendor_intel_job(job_data)
        else:
            logger.error(f"Unknown job type: {job_type}")
            exit_code = 1
            return
        
        if success:
            logger.info("Job completed successfully")
            exit_code = 0
        else:
            logger.error("Job failed")
            exit_code = 1
            
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        exit_code = 1
    finally:
        if job_id:
            final_pod_output = _capture_batch_job_pod_output(job_id)
            if final_pod_output:
                await _upload_runner_pod_output(job_id, final_pod_output)

    sys.exit(exit_code)

if __name__ == "__main__":
    asyncio.run(main())
