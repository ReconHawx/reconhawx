#!/usr/bin/env python3
import sys
import logging
import json
import os
import asyncio
from tasks.phishlabs_batch import PhishLabsBatchTask
from tasks.dummy_batch import DummyBatchTask
from tasks.gather_api_findings import GatherApiFindingsTask
from tasks.sync_recordedfuture_data import SyncRecordedFutureDataTask
from tasks.ai_analysis_batch import AIAnalysisBatchTask

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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

async def run_dummy_batch_job(job_data: dict):
    """Run a dummy batch job for testing purposes"""
    try:
        job_id = job_data.get("job_id")
        items = job_data.get("items", [])
        user_id = job_data.get("user_id", "unknown")

        if not job_id:
            logger.error("Job ID is required")
            return False

        logger.info(f"Starting dummy batch job {job_id} for {len(items)} items")

        # Create and execute the task
        task = DummyBatchTask(job_id, items, user_id)
        await task.execute()

        logger.info(f"Dummy batch job {job_id} completed successfully")
        return True

    except Exception as e:
        logger.error(f"Error running dummy batch job: {str(e)}")
        return False

async def run_gather_api_findings_job(job_data: dict):
    """Run a gather API findings job"""
    try:
        job_id = job_data.get("job_id")
        program_name = job_data.get("program_name")  # Single program from scheduled job
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

        logger.info(f"Starting gather API findings job {job_id} for program {program_name} using {api_vendor}")

        # Create and execute the task
        task = GatherApiFindingsTask(job_id, program_name, user_id, api_vendor, date_range_hours, custom_query)
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

async def main():
    """Main entry point for job execution"""
    try:
        # Read job data from file
        job_data_path = "/app/job-data/job_data.json"
        
        if not os.path.exists(job_data_path):
            logger.error(f"Job data file not found: {job_data_path}")
            sys.exit(1)
        
        with open(job_data_path, 'r') as f:
            job_data = json.load(f)
        
        job_type = job_data.get("job_type")
        logger.info(f"Starting job of type: {job_type}")
        
        success = False
        
        if job_type == "phishlabs_batch":
            success = await run_phishlabs_batch_job(job_data)
        elif job_type == "phishlabs_incidents_batch":
            success = await run_phishlabs_batch_job(job_data)
        elif job_type == "ai_analysis_batch":
            success = await run_ai_analysis_batch_job(job_data)
        elif job_type == "dummy_batch":
            success = await run_dummy_batch_job(job_data)
        elif job_type == "gather_api_findings":
            success = await run_gather_api_findings_job(job_data)
        elif job_type == "sync_recordedfuture_data":
            success = await run_sync_recordedfuture_data_job(job_data)
        else:
            logger.error(f"Unknown job type: {job_type}")
            sys.exit(1)
        
        if success:
            logger.info("Job completed successfully")
            sys.exit(0)
        else:
            logger.error("Job failed")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 