#!/usr/bin/env python3
"""
Worker batch job runner
Handles batch jobs that need to run in the worker container
"""

import asyncio
import json
import logging
import os
import sys

# Add the app directory to the path
sys.path.insert(0, '/app')

from typosquat_batch import TyposquatBatchTask

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

async def run_typosquat_batch_job(job_data: dict):
    """Run typosquat batch job"""
    try:
        job_id = job_data.get("job_id")
        domains = job_data.get("domains", [])
        user_id = job_data.get("user_id", "unknown")
        program_name = job_data.get("program_name")
        logger.info(f"Starting typosquat batch job {job_id} for {len(domains)} domains")
        
        task = TyposquatBatchTask(job_id, domains, user_id, program_name)
        await task.execute()
        
        logger.info(f"Typosquat batch job {job_id} completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error running typosquat batch job: {str(e)}")
        return False

async def main():
    """Main entry point"""
    try:
        # Read job data from file
        job_data_path = "/workspace/job-data/job_data.json"
        
        if not os.path.exists(job_data_path):
            logger.error(f"Job data file not found: {job_data_path}")
            sys.exit(1)
        
        with open(job_data_path, 'r') as f:
            job_data = json.load(f)
        
        job_type = job_data.get("job_type")
        logger.info(f"Starting batch job of type: {job_type}")
        
        success = False
        
        if job_type == "typosquat_batch":
            success = await run_typosquat_batch_job(job_data)
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