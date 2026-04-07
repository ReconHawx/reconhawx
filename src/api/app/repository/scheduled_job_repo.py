from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from models.postgres import ScheduledJob, JobExecutionHistory, Program
from db import get_db_session
import uuid

logger = logging.getLogger(__name__)

def serialize_json_data(data: Any) -> Any:
    """Serialize data for JSONB storage, converting datetime objects to ISO strings"""
    if isinstance(data, dict):
        return {k: serialize_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [serialize_json_data(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif hasattr(data, 'isoformat'):  # Handle other datetime-like objects
        return data.isoformat()
    else:
        return data

class ScheduledJobRepository:
    @staticmethod
    def _enrich_program_fields_sync(db, job_dict: Dict[str, Any]) -> None:
        """Attach program_names and legacy program_name in program_ids order."""
        ids = job_dict.get("program_ids") or []
        if not ids:
            job_dict["program_names"] = []
            job_dict["program_name"] = None
            return
        try:
            uuids = [uuid.UUID(x) if isinstance(x, str) else x for x in ids]
        except ValueError:
            job_dict["program_names"] = []
            job_dict["program_name"] = None
            return
        programs = db.query(Program).filter(Program.id.in_(uuids)).all()
        id_to_name = {str(p.id): p.name for p in programs}
        job_dict["program_names"] = [id_to_name.get(str(i), "") for i in ids]
        job_dict["program_name"] = job_dict["program_names"][0] if job_dict["program_names"] else None

    @staticmethod
    async def create_scheduled_job(job_data: Dict[str, Any]) -> bool:
        """Create a new scheduled job record"""
        try:
            async with get_db_session() as db:
                # Convert user_id to UUID if it's a string
                user_uuid = None
                if job_data.get("user_id"):
                    try:
                        if isinstance(job_data["user_id"], str):
                            user_uuid = uuid.UUID(job_data["user_id"])
                        else:
                            user_uuid = job_data["user_id"]
                    except ValueError:
                        logger.error(f"Invalid user_id format: {job_data['user_id']}")
                        return False

                raw_pids = job_data.get("program_ids") or []
                program_uuid_list: List[uuid.UUID] = []
                for pid in raw_pids:
                    try:
                        if isinstance(pid, str):
                            program_uuid_list.append(uuid.UUID(pid))
                        else:
                            program_uuid_list.append(pid)
                    except ValueError:
                        logger.error(f"Invalid program_id in program_ids: {pid}")
                        return False
                if not program_uuid_list:
                    logger.error("program_ids must be non-empty")
                    return False

                # Serialize JSON data to handle datetime objects
                schedule_data = serialize_json_data(job_data["schedule"])
                job_data_serialized = serialize_json_data(job_data["job_data"])

                # Serialize workflow variables for JSONB storage
                workflow_variables = serialize_json_data(job_data.get("workflow_variables", {}))

                scheduled_job = ScheduledJob(
                    schedule_id=job_data["schedule_id"],
                    job_type=job_data["job_type"],
                    name=job_data["name"],
                    description=job_data.get("description"),
                    schedule_data=schedule_data,
                    job_data=job_data_serialized,
                    workflow_variables=workflow_variables,
                    user_id=user_uuid,
                    program_ids=program_uuid_list,
                    status=job_data["status"],
                    tags=job_data.get("tags", []),
                    next_run=job_data.get("next_run"),
                    last_run=job_data.get("last_run"),
                    total_executions=job_data.get("total_executions", 0),
                    successful_executions=job_data.get("successful_executions", 0),
                    failed_executions=job_data.get("failed_executions", 0),
                    enabled=job_data.get("enabled", True),
                    created_at=job_data.get("created_at", datetime.utcnow()),
                    updated_at=job_data.get("updated_at", datetime.utcnow())
                )

                db.add(scheduled_job)
                db.commit()
                db.refresh(scheduled_job)

                logger.info(f"Created scheduled job record for {job_data['schedule_id']}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"Database error creating scheduled job {job_data.get('schedule_id')}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error creating scheduled job {job_data.get('schedule_id')}: {str(e)}")
            return False

    @staticmethod
    async def get_scheduled_job(schedule_id: str) -> Optional[Dict[str, Any]]:
        """Get scheduled job by ID"""
        try:
            async with get_db_session() as db:
                scheduled_job = db.query(ScheduledJob).filter(ScheduledJob.schedule_id == schedule_id).first()

                if not scheduled_job:
                    return None

                job_dict = scheduled_job.to_dict()
                ScheduledJobRepository._enrich_program_fields_sync(db, job_dict)
                return job_dict

        except SQLAlchemyError as e:
            logger.error(f"Database error getting scheduled job {schedule_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error getting scheduled job {schedule_id}: {str(e)}")
            return None

    @staticmethod
    async def get_all_scheduled_jobs(user_id: Optional[str] = None, program_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get all scheduled jobs, optionally filtered by user and program permissions"""
        try:
            async with get_db_session() as db:
                query = db.query(ScheduledJob)

                if user_id:
                    # Convert user_id to UUID if it's a string
                    try:
                        if isinstance(user_id, str):
                            user_uuid = uuid.UUID(user_id)
                        else:
                            user_uuid = user_id
                        query = query.filter(ScheduledJob.user_id == user_uuid)
                    except ValueError:
                        logger.error(f"Invalid user_id format: {user_id}")
                        return []

                # Filter: scheduled job visible if it shares at least one program with the filter set
                if program_ids:
                    try:
                        program_uuids = []
                        for program_id in program_ids:
                            if isinstance(program_id, str):
                                program_uuids.append(uuid.UUID(program_id))
                            else:
                                program_uuids.append(program_id)
                        query = query.filter(ScheduledJob.program_ids.overlap(program_uuids))
                    except ValueError as e:
                        logger.error(f"Invalid program_id format: {e}")
                        return []

                scheduled_jobs = query.order_by(desc(ScheduledJob.created_at)).all()

                result = []
                for job in scheduled_jobs:
                    job_dict = job.to_dict()
                    ScheduledJobRepository._enrich_program_fields_sync(db, job_dict)
                    result.append(job_dict)

                return result

        except SQLAlchemyError as e:
            logger.error(f"Database error getting scheduled jobs: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting scheduled jobs: {str(e)}")
            return []

    @staticmethod
    async def update_scheduled_job(schedule_id: str, update_data: Dict[str, Any]) -> bool:
        """Update a scheduled job"""
        try:
            async with get_db_session() as db:
                scheduled_job = db.query(ScheduledJob).filter(ScheduledJob.schedule_id == schedule_id).first()

                if not scheduled_job:
                    logger.warning(f"Scheduled job {schedule_id} not found for update")
                    return False

                # Update fields
                if "name" in update_data:
                    scheduled_job.name = update_data["name"]
                if "description" in update_data:
                    scheduled_job.description = update_data["description"]
                if "schedule_data" in update_data:
                    # Serialize schedule data to handle datetime objects
                    scheduled_job.schedule_data = serialize_json_data(update_data["schedule_data"])
                if "enabled" in update_data:
                    scheduled_job.enabled = update_data["enabled"]
                if "tags" in update_data:
                    scheduled_job.tags = update_data["tags"]
                if "next_run" in update_data:
                    scheduled_job.next_run = update_data["next_run"]
                if "last_run" in update_data:
                    scheduled_job.last_run = update_data["last_run"]
                if "job_data" in update_data:
                    # Serialize job data to handle datetime objects
                    scheduled_job.job_data = serialize_json_data(update_data["job_data"])
                if "workflow_variables" in update_data:
                    # Serialize workflow variables for JSONB storage
                    scheduled_job.workflow_variables = serialize_json_data(update_data["workflow_variables"])
                if "total_executions" in update_data:
                    scheduled_job.total_executions = update_data["total_executions"]
                if "successful_executions" in update_data:
                    scheduled_job.successful_executions = update_data["successful_executions"]
                if "failed_executions" in update_data:
                    scheduled_job.failed_executions = update_data["failed_executions"]
                if "status" in update_data:
                    scheduled_job.status = update_data["status"]
                if "program_ids" in update_data:
                    raw_pids = update_data["program_ids"]
                    program_uuid_list: List[uuid.UUID] = []
                    for pid in raw_pids:
                        if isinstance(pid, str):
                            program_uuid_list.append(uuid.UUID(pid))
                        else:
                            program_uuid_list.append(pid)
                    if not program_uuid_list:
                        logger.error("program_ids update must be non-empty")
                        return False
                    scheduled_job.program_ids = program_uuid_list

                scheduled_job.updated_at = datetime.utcnow()

                db.commit()
                logger.info(f"Updated scheduled job {schedule_id}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"Database error updating scheduled job {schedule_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error updating scheduled job {schedule_id}: {str(e)}")
            return False

    @staticmethod
    async def delete_scheduled_job(schedule_id: str) -> bool:
        """Delete a scheduled job"""
        try:
            async with get_db_session() as db:
                scheduled_job = db.query(ScheduledJob).filter(ScheduledJob.schedule_id == schedule_id).first()

                if not scheduled_job:
                    logger.warning(f"Scheduled job {schedule_id} not found for deletion")
                    return False

                db.delete(scheduled_job)
                db.commit()

                logger.info(f"Deleted scheduled job {schedule_id}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"Database error deleting scheduled job {schedule_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error deleting scheduled job {schedule_id}: {str(e)}")
            return False

    @staticmethod
    async def create_execution_history(execution_data: Dict[str, Any]) -> bool:
        """Create a job execution history record"""
        try:
            async with get_db_session() as db:
                # Serialize results field for JSONB storage
                results_serialized = serialize_json_data(execution_data.get("results"))

                execution_history = JobExecutionHistory(
                    execution_id=execution_data["execution_id"],
                    schedule_id=execution_data["schedule_id"],
                    job_id=execution_data["job_id"],
                    status=execution_data["status"],
                    started_at=execution_data["started_at"],
                    completed_at=execution_data.get("completed_at"),
                    duration_seconds=execution_data.get("duration_seconds"),
                    error_message=execution_data.get("error_message"),
                    results=results_serialized,
                    created_at=execution_data.get("created_at", datetime.utcnow())
                )

                db.add(execution_history)
                db.commit()
                db.refresh(execution_history)

                logger.info(f"Created execution history record for {execution_data['execution_id']}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"Database error creating execution history {execution_data.get('execution_id')}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error creating execution history {execution_data.get('execution_id')}: {str(e)}")
            return False

    @staticmethod
    async def get_execution_history(schedule_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get execution history for a scheduled job"""
        try:
            async with get_db_session() as db:
                executions = db.query(JobExecutionHistory).filter(
                    JobExecutionHistory.schedule_id == schedule_id
                ).order_by(
                    JobExecutionHistory.started_at.desc()
                ).limit(limit).all()

                return [execution.to_dict() for execution in executions]

        except SQLAlchemyError as e:
            logger.error(f"Database error getting execution history for {schedule_id}: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting execution history for {schedule_id}: {str(e)}")
            return []

    @staticmethod
    async def get_execution_history_by_id(execution_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific execution record by execution_id"""
        try:
            async with get_db_session() as db:
                execution = db.query(JobExecutionHistory).filter(
                    JobExecutionHistory.execution_id == execution_id
                ).first()

                return execution.to_dict() if execution else None

        except SQLAlchemyError as e:
            logger.error(f"Database error getting execution history by ID {execution_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error getting execution history by ID {execution_id}: {str(e)}")
            return None

    @staticmethod
    async def update_execution_history(execution_id: str, update_data: Dict[str, Any]) -> bool:
        """Update a job execution history record"""
        try:
            async with get_db_session() as db:
                execution = db.query(JobExecutionHistory).filter(JobExecutionHistory.execution_id == execution_id).first()

                if not execution:
                    logger.warning(f"Execution history {execution_id} not found for update")
                    return False

                # Update fields
                if "status" in update_data:
                    execution.status = update_data["status"]
                if "completed_at" in update_data:
                    execution.completed_at = update_data["completed_at"]
                if "duration_seconds" in update_data:
                    execution.duration_seconds = update_data["duration_seconds"]
                if "error_message" in update_data:
                    execution.error_message = update_data["error_message"]
                if "results" in update_data:
                    execution.results = serialize_json_data(update_data["results"])

                db.commit()
                db.refresh(execution)

                logger.info(f"Updated execution history record {execution_id}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"Database error updating execution history {execution_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error updating execution history {execution_id}: {str(e)}")
            return False
