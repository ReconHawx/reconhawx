from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime
from sqlalchemy import and_, desc
from sqlalchemy.exc import SQLAlchemyError
from models.postgres import JobStatus
from db import get_db_session
import uuid

logger = logging.getLogger(__name__)

class JobRepository:
    @staticmethod
    async def create_job(job_id: str, job_type: str, job_data: Dict[str, Any]) -> bool:
        """Create a new job status record"""
        try:
            async with get_db_session() as db:
                
                job_doc = {
                    "id": uuid.uuid4(),
                    "job_id": job_id,
                    "job_type": job_type,
                    "status": "pending",
                    "progress": 0,
                    "message": "Job created",
                    "results": None,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
                
                job_status = JobStatus(**job_doc)
                db.add(job_status)
                db.commit()
                db.refresh(job_status)
                
                logger.info(f"Created job status record for job {job_id}")
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error creating job status for {job_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error creating job status for {job_id}: {str(e)}")
            return False

    @staticmethod
    async def update_job_status(job_id: str, status: str, progress: int, message: str, results: Optional[Dict[str, Any]] = None) -> bool:
        """Update job status"""
        try:
            async with get_db_session() as db:
                job_status = db.query(JobStatus).filter(JobStatus.job_id == job_id).first()
                
                if not job_status:
                    logger.warning(f"Job {job_id} not found for status update")
                    return False
                
                job_status.status = status
                job_status.progress = progress
                job_status.message = message
                job_status.updated_at = datetime.utcnow()
                
                if results is not None:
                    job_status.results = results
                
                db.commit()
                logger.info(f"Updated job {job_id} status to {status} ({progress}%)")
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error updating job status for {job_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error updating job status for {job_id}: {str(e)}")
            return False

    @staticmethod
    async def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status by ID"""
        try:
            async with get_db_session() as db:
                job_status = db.query(JobStatus).filter(JobStatus.job_id == job_id).first()
                
                if job_status:
                    return job_status.to_dict()
                return None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting job status for {job_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error getting job status for {job_id}: {str(e)}")
            return None

    @staticmethod
    async def delete_job(job_id: str) -> bool:
        """Delete a job status record"""
        try:
            async with get_db_session() as db:
                job_status = db.query(JobStatus).filter(JobStatus.job_id == job_id).first()
                
                if not job_status:
                    return False
                
                db.delete(job_status)
                db.commit()
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database error deleting job {job_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {str(e)}")
            return False

    @staticmethod
    async def get_all_jobs(page: int = 1, limit: int = 25, job_type: Optional[str] = None, status: Optional[str] = None) -> Tuple[List[Dict[str, Any]], int]:
        """Get all jobs with pagination and filtering"""
        try:
            async with get_db_session() as db:
                # Build filter query
                filter_conditions = []
                if job_type:
                    filter_conditions.append(JobStatus.job_type == job_type)
                if status:
                    filter_conditions.append(JobStatus.status == status)
                
                # Get total count
                if filter_conditions:
                    total = db.query(JobStatus).filter(and_(*filter_conditions)).count()
                else:
                    total = db.query(JobStatus).count()
                
                # Calculate skip
                skip = (page - 1) * limit
                
                # Get jobs with pagination
                query = db.query(JobStatus)
                if filter_conditions:
                    query = query.filter(and_(*filter_conditions))
                
                job_statuses = query.order_by(desc(JobStatus.created_at)).offset(skip).limit(limit).all()
                jobs = [job_status.to_dict() for job_status in job_statuses]
                
                return jobs, total
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting all jobs: {str(e)}")
            return [], 0
        except Exception as e:
            logger.error(f"Error getting all jobs: {str(e)}")
            return [], 0 