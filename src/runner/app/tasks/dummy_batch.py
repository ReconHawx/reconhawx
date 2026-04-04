import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import os
import asyncpg
import json

logger = logging.getLogger(__name__)

class DummyBatchTask:
    def __init__(self, job_id: str, items: List[str], user_id: str):
        self.job_id = job_id
        self.items = items
        self.user_id = user_id
        self.results = {
            "success_count": 0,
            "error_count": 0,
            "errors": [],
            "processed_items": [],
            "echo_messages": []
        }
        
        # PostgreSQL connection parameters
        self.db_host = os.getenv("POSTGRES_HOST", "localhost")
        self.db_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.db_name = os.getenv("DATABASE_NAME", "reconhawx")
        self.db_user = os.getenv("POSTGRES_USER", "admin")
        self.db_password = os.getenv("POSTGRES_PASSWORD", "password")
    
    async def get_db_connection(self):
        """Get PostgreSQL database connection"""
        try:
            connection = await asyncpg.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            return connection
        except Exception as e:
            logger.error(f"Error connecting to PostgreSQL: {str(e)}")
            raise
    
    async def execute(self):
        """Main execution method for dummy batch job"""
        try:
            # Update job status to running
            await self.update_job_status("running", 0, "Starting dummy batch processing...")
            
            total_items = len(self.items)
            if total_items == 0:
                await self.update_job_status("completed", 100, "No items to process", self.results)
                return
            
            logger.info(f"Starting dummy batch job {self.job_id} for {total_items} items")
            
            # Process each item
            for i, item in enumerate(self.items):
                try:
                    # Simulate some processing time
                    await asyncio.sleep(1)
                    
                    # Create a simple echo message
                    echo_message = f"Processed item {i+1}: {item} at {datetime.now(timezone.utc).isoformat()}"
                    self.results["echo_messages"].append(echo_message)
                    self.results["processed_items"].append({
                        "item": item,
                        "index": i,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "success"
                    })
                    self.results["success_count"] += 1
                    
                    logger.info(f"Processed item {i+1}/{total_items}: {item}")
                    
                    # Update progress
                    progress = int(((i + 1) / total_items) * 100)
                    await self.update_job_status("running", progress, f"Processed {i+1}/{total_items} items...")
                    
                except Exception as e:
                    logger.error(f"Error processing item {item}: {str(e)}")
                    self.results["error_count"] += 1
                    self.results["errors"].append({
                        "item": item,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
            
            # Final status update
            message = f"Completed: {self.results['success_count']} successful, {self.results['error_count']} errors"
            await self.update_job_status("completed", 100, message, self.results)
            
            logger.info(f"Dummy batch job {self.job_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Error in dummy batch job {self.job_id}: {str(e)}")
            await self.update_job_status("failed", 0, f"Job failed: {str(e)}")
    
    async def update_job_status(self, status: str, progress: int, message: str, results: Optional[Dict[str, Any]] = None):
        """Update job status in PostgreSQL database"""
        try:
            conn = await self.get_db_connection()
            
            try:
                # Update the job status
                # Use timezone-naive datetime for PostgreSQL compatibility
                update_query = """
                    UPDATE job_status 
                    SET status = $1, progress = $2, message = $3, updated_at = $4
                    WHERE job_id = $5
                """
                
                # Convert timezone-aware datetime to timezone-naive
                now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                
                await conn.execute(
                    update_query,
                    status, progress, message, now_naive, self.job_id
                )
                
                # If results are provided, update them as well
                if results is not None:
                    results_query = """
                        UPDATE job_status 
                        SET results = $1
                        WHERE job_id = $2
                    """
                    # Convert results dict to JSON string for PostgreSQL jsonb column
                    results_json = json.dumps(results)
                    await conn.execute(results_query, results_json, self.job_id)
                
                logger.info(f"Updated job {self.job_id} status: {status} ({progress}%) - {message}")
                
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"Error updating job status: {str(e)}") 