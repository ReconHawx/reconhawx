import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from models.job import (
    JobType, JobSchedule, ScheduleType, ScheduledJobRequest, ScheduledJobResponse, JobStatus
)
from services.job_submission import JobSubmissionService
from repository import JobRepository
from repository import ScheduledJobRepository

logger = logging.getLogger(__name__)

class JobSchedulerService:
    def __init__(self):
        """Initialize the job scheduler service"""
        self.scheduler = AsyncIOScheduler(
            jobstores={'default': MemoryJobStore()},
            executors={'default': AsyncIOExecutor()},
            job_defaults={
                'coalesce': False,
                'max_instances': 1
            }
        )
        self.job_submission_service = JobSubmissionService()
        self.scheduled_jobs: Dict[str, Dict[str, Any]] = {}
        self._running = False
        
    async def start(self):
        """Start the scheduler"""
        if not self._running:
            self.scheduler.start()
            self._running = True
            logger.info("Job scheduler started")
            
            # Load existing scheduled jobs from database
            await self._load_scheduled_jobs()
    
    async def stop(self):
        """Stop the scheduler"""
        if self._running:
            self.scheduler.shutdown()
            self._running = False
            logger.info("Job scheduler stopped")
    
    async def _load_scheduled_jobs(self):
        """Load existing scheduled jobs from the database"""
        try:
            logger.info("Loading scheduled jobs from database...")
            
            # Load all scheduled jobs from database
            scheduled_jobs_data = await ScheduledJobRepository.get_all_scheduled_jobs()
            
            for job_data in scheduled_jobs_data:
                if job_data.get("enabled", True):
                    # Recreate the scheduled job request
                    from models.job import ScheduledJobRequest, JobSchedule
                    
                    request = ScheduledJobRequest(
                        job_type=JobType(job_data["job_type"]),
                        job_data=job_data["job_data"],
                        schedule=JobSchedule(**job_data["schedule_data"]),
                        name=job_data["name"],
                        description=job_data.get("description"),
                        program_name=job_data.get("program_name", "unknown"),
                        tags=job_data.get("tags", [])
                    )
                    
                    # Schedule the job
                    await self._schedule_job(job_data["schedule_id"], request)
                    
                    # Store in memory
                    self.scheduled_jobs[job_data["schedule_id"]] = job_data
            
            logger.info(f"Loaded {len(scheduled_jobs_data)} scheduled jobs from database")
            
        except Exception as e:
            logger.error(f"Error loading scheduled jobs: {str(e)}")
    
    async def create_scheduled_job(self, request: ScheduledJobRequest, user_id: str, program_id: str) -> ScheduledJobResponse:
        """Create a new scheduled job"""
        try:
            schedule_id = str(uuid.uuid4())
            
            # Create the scheduled job record
            scheduled_job_data = {
                "schedule_id": schedule_id,
                "job_type": request.job_type.value,
                "name": request.name,
                "description": request.description,
                "schedule": request.schedule.dict(),
                "job_data": request.job_data,
                "workflow_variables": request.job_data.get("workflow_variables", {}),
                "user_id": user_id,
                "program_id": program_id,
                "status": JobStatus.SCHEDULED.value,
                "tags": request.tags,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            # Save to database
            await ScheduledJobRepository.create_scheduled_job(scheduled_job_data)
            
            # Schedule the job
            await self._schedule_job(schedule_id, request)
            
            # Store in memory
            self.scheduled_jobs[schedule_id] = scheduled_job_data
            
            logger.info(f"Created scheduled job {schedule_id}: {request.name}")
            
            return ScheduledJobResponse(
                schedule_id=schedule_id,
                job_type=request.job_type,
                name=request.name,
                description=request.description,
                program_id=program_id,
                job_data=request.job_data,
                schedule=request.schedule,
                status=JobStatus.SCHEDULED,
                next_run=await self._get_next_run_time(schedule_id, request.schedule),
                last_run=None,
                total_executions=0,
                successful_executions=0,
                failed_executions=0,
                created_at=scheduled_job_data["created_at"],
                updated_at=scheduled_job_data["updated_at"],
                tags=request.tags
            )
            
        except Exception as e:
            logger.error(f"Error creating scheduled job: {str(e)}")
            raise
    
    def _get_timezone_object(self, timezone_str: str):
        """Get timezone object from timezone string with fallback to UTC"""
        logger.info(f"🔍 DEBUG: _get_timezone_object called with: {timezone_str}")
        
        if not timezone_str:
            logger.info("🔍 DEBUG: No timezone string provided, using UTC")
            return timezone.utc
            
        try:
            import pytz
            timezone_obj = pytz.timezone(timezone_str)
            logger.info(f"🔍 DEBUG: Successfully created timezone object: {timezone_obj}")
            return timezone_obj
        except ImportError:
            # Fallback to UTC if pytz is not available
            logger.warning(f"pytz not available, using UTC for timezone {timezone_str}")
            return timezone.utc
        except Exception as e:
            # Fallback to UTC if timezone is invalid
            logger.warning(f"Invalid timezone {timezone_str}, using UTC: {str(e)}")
            return timezone.utc

    async def _schedule_job(self, schedule_id: str, request: ScheduledJobRequest):
        """Schedule a job with the APScheduler"""
        try:
            job_func = self._create_job_execution_function(schedule_id, request)
            
            if request.schedule.schedule_type == ScheduleType.ONCE:
                # One-time job
                if request.schedule.start_time:
                    # Use the timezone from the schedule configuration for one-time jobs
                    timezone_str = request.schedule.timezone or "UTC"
                    timezone_obj = self._get_timezone_object(timezone_str)
                    
                    # Create trigger with timezone
                    trigger = DateTrigger(run_date=request.schedule.start_time, timezone=timezone_obj)
                    self.scheduler.add_job(
                        job_func,
                        trigger=trigger,
                        id=schedule_id,
                        name=request.name,
                        replace_existing=True
                    )
                else:
                    # Run immediately
                    self.scheduler.add_job(
                        job_func,
                        trigger='date',
                        id=schedule_id,
                        name=request.name,
                        replace_existing=True
                    )
                    
            elif request.schedule.schedule_type == ScheduleType.RECURRING:
                # Recurring job
                if not request.schedule.recurring_schedule:
                    raise ValueError("Recurring schedule configuration is required")
                
                interval_seconds = request.schedule.recurring_schedule.get_interval_seconds()
                
                # Use the timezone from the schedule configuration for recurring jobs
                timezone_str = request.schedule.timezone or "UTC"
                timezone_obj = self._get_timezone_object(timezone_str)
                
                trigger = IntervalTrigger(
                    seconds=interval_seconds,
                    start_date=request.schedule.start_time,
                    end_date=request.schedule.recurring_schedule.end_date,
                    timezone=timezone_obj
                )
                
                self.scheduler.add_job(
                    job_func,
                    trigger=trigger,
                    id=schedule_id,
                    name=request.name,
                    replace_existing=True,
                    max_instances=1
                )
                
            elif request.schedule.schedule_type == ScheduleType.CRON:
                # Cron job
                if not request.schedule.cron_schedule:
                    raise ValueError("Cron schedule configuration is required")
                
                cron_string = request.schedule.cron_schedule.to_cron_string()
                
                # Use the timezone from the schedule configuration
                timezone_str = request.schedule.timezone or "UTC"
                timezone_obj = self._get_timezone_object(timezone_str)
                
                # Fix: Convert standard cron day_of_week (0-6) to APScheduler format
                # Standard cron: 0=Sunday, 1=Monday, ..., 6=Saturday
                # APScheduler: 0=Monday, 1=Tuesday, ..., 6=Sunday
                if request.schedule.cron_schedule.day_of_week != '*':
                    # Convert day_of_week from standard cron to APScheduler format
                    standard_day = int(request.schedule.cron_schedule.day_of_week)
                    
                    # Map: 0(Sun)->6, 1(Mon)->0, 2(Tue)->1, 3(Wed)->2, 4(Thu)->3, 5(Fri)->4, 6(Sat)->5
                    if standard_day == 0:  # Sunday
                        apscheduler_day = 6
                    else:
                        apscheduler_day = standard_day - 1
                    
                    # Rebuild cron string with corrected day_of_week
                    cron_parts = cron_string.split()
                    cron_parts[4] = str(apscheduler_day)  # day_of_week is the 5th field (0-indexed)
                    cron_string = ' '.join(cron_parts)
                    
                    logger.info(f"🔍 DEBUG: Day of week conversion - Standard: {standard_day} -> APScheduler: {apscheduler_day}")
                    logger.info(f"🔍 DEBUG: Original cron: {request.schedule.cron_schedule.to_cron_string()}")
                    logger.info(f"🔍 DEBUG: Converted cron: {cron_string}")
                
                # Debug logging
                logger.info(f"🔍 DEBUG: Cron job timezone processing - schedule_id: {schedule_id}")
                logger.info(f"🔍 DEBUG: Received timezone: {timezone_str}")
                logger.info(f"🔍 DEBUG: Processed timezone object: {timezone_obj}")
                logger.info(f"🔍 DEBUG: Cron string: {cron_string}")
                logger.info(f"🔍 DEBUG: Full schedule data: {request.schedule.dict()}")
                logger.info(f"🔍 DEBUG: Day of week value: {request.schedule.cron_schedule.day_of_week}")
                logger.info(f"🔍 DEBUG: Day of week type: {type(request.schedule.cron_schedule.day_of_week)}")
                
                trigger = CronTrigger.from_crontab(cron_string, timezone=timezone_obj)
                
                self.scheduler.add_job(
                    job_func,
                    trigger=trigger,
                    id=schedule_id,
                    name=request.name,
                    replace_existing=True,
                    max_instances=1
                )
            
            logger.info(f"Scheduled job {schedule_id} with type {request.schedule.schedule_type}")
            
        except Exception as e:
            logger.error(f"Error scheduling job {schedule_id}: {str(e)}")
            raise
    
    def _create_job_execution_function(self, schedule_id: str, request: ScheduledJobRequest) -> Callable:
        """Create a function that will be executed when the scheduled job runs"""
        async def execute_scheduled_job():
            try:
                logger.info(f"Executing scheduled job {schedule_id}: {request.name}")
                logger.debug(f"Request: {request}")
                # Update status to running
                await self._update_scheduled_job_status(schedule_id, JobStatus.RUNNING)
                
                # Get the scheduled job data to get user_id and other details
                job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
                if not job_data:
                    raise ValueError(f"Scheduled job {schedule_id} not found in database")
                
                # Create and submit the actual job
                job_id = str(uuid.uuid4())
                job_payload = {
                    "job_id": job_id,
                    "job_type": request.job_type.value,
                    "schedule_id": schedule_id,
                    "job_data": request.job_data,
                    "user_id": job_data["user_id"],
                    "created_at": datetime.now(timezone.utc).isoformat()
                }

                # Create job status record
                await JobRepository.create_job(
                    job_id,
                    request.job_type.value,
                    job_payload
                )

                # Create payload for worker - structure depends on job type
                if request.job_type == JobType.GATHER_API_FINDINGS:
                    # gather_api_findings expects program_name at top level but other params nested in job_data
                    worker_payload = {
                        "job_id": job_id,
                        "job_type": request.job_type.value,
                        "schedule_id": schedule_id,
                        "user_id": job_data["user_id"],
                        "program_name": request.program_name,  # From scheduled job
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "job_data": request.job_data  # Keep nested structure for api_vendor, date_range_hours
                    }
                else:
                    # Other job types expect flattened structure
                    worker_payload = {
                        "job_id": job_id,
                        "job_type": request.job_type.value,
                        "schedule_id": schedule_id,
                        "user_id": job_data["user_id"],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        **request.job_data  # Flatten job_data fields to top level
                    }

                # Submit to Kubernetes based on job type
                if request.job_type == JobType.DUMMY_BATCH:
                    self.job_submission_service.create_dummy_batch_job(job_id, worker_payload)
                elif request.job_type == JobType.TYPOSQUAT_BATCH:
                    self.job_submission_service.create_typosquat_batch_job(job_id, worker_payload)
                elif request.job_type == JobType.PHISHLABS_BATCH:
                    self.job_submission_service.create_phishlabs_batch_job(job_id, worker_payload)
                elif request.job_type == JobType.AI_ANALYSIS_BATCH:
                    await self.job_submission_service.create_ai_analysis_batch_job(job_id, worker_payload)
                elif request.job_type == JobType.GATHER_API_FINDINGS:
                    self.job_submission_service.create_gather_api_findings_job(job_id, worker_payload)
                elif request.job_type == JobType.SYNC_RECORDEDFUTURE_DATA:
                    self.job_submission_service.create_sync_recordedfuture_data_job(job_id, worker_payload)
                elif request.job_type == JobType.WORKFLOW:
                    # For workflow jobs, use the workflow execution system
                    from services.kubernetes import KubernetesService
                    from repository import WorkflowDefinitionRepository
                    k8s_service = KubernetesService()
                    workflow_repo = WorkflowDefinitionRepository()
                    
                    # Get workflow definition ID from job data
                    workflow_definition_id = job_payload.get("job_data", {}).get("workflow_id")
                    
                    if workflow_definition_id:
                        # Load complete workflow definition from database
                        try:
                            workflow_definition = await workflow_repo.get_workflow_definition(workflow_definition_id)
                            if workflow_definition:
                                logger.info(f"Loaded workflow definition for scheduled workflow: {workflow_definition_id}")
                                
                                # Get stored workflow variables from scheduled job
                                stored_variables = self.scheduled_jobs[schedule_id].get("workflow_variables", {})
                                
                                # Extract workflow data from database definition
                                workflow_data = {
                                    "workflow_id": workflow_definition_id,
                                    "execution_id": job_id,  # Use job_id as execution_id
                                    "program_name": request.program_name,
                                    "name": workflow_definition.get("name", request.name),
                                    "description": workflow_definition.get("description", request.description or "Scheduled workflow execution"),
                                    "variables": workflow_definition.get("variables", {}),
                                    "inputs": workflow_definition.get("inputs", {}),
                                    "steps": workflow_definition.get("steps", [])
                                }
                                
                                # Process workflow with stored variables if any
                                if stored_variables and workflow_data["variables"]:
                                    logger.info(f"Processing workflow with {len(stored_variables)} stored variables")
                                    try:
                                        # Import workflow processing utilities
                                        from utils.workflow_processor import process_workflow_with_variables
                                        workflow_data = process_workflow_with_variables(workflow_data, stored_variables)
                                        logger.info("Workflow processed with variables successfully")
                                    except ImportError:
                                        logger.warning("Workflow processing utilities not available, using raw workflow")
                                    except Exception as e:
                                        logger.error(f"Error processing workflow with variables: {str(e)}")
                                        # Continue with unprocessed workflow
                                
                                logger.info(f"Workflow definition loaded: {len(workflow_data['steps'])} steps, {len(workflow_data['variables'])} variables, {len(workflow_data['inputs'])} inputs")
                            else:
                                logger.error(f"Workflow definition not found: {workflow_definition_id}")
                                raise ValueError(f"Workflow definition not found: {workflow_definition_id}")
                        except Exception as e:
                            logger.error(f"Error loading workflow definition {workflow_definition_id}: {str(e)}")
                            raise
                    else:
                        # Fallback to job_data if no workflow_definition_id
                        logger.warning("No workflow_definition_id provided, using job_data")
                        workflow_data = {
                            "workflow_id": None,
                            "execution_id": job_id,
                            "program_name": job_payload.get("job_data", {}).get("program_name", "scheduled-workflow"),
                            "name": request.name,
                            "description": request.description or "Scheduled workflow execution",
                            "variables": job_payload.get("job_data", {}).get("variables", {}),
                            "inputs": job_payload.get("job_data", {}).get("inputs", {}),
                            "steps": job_payload.get("job_data", {}).get("steps", [])
                        }
                    
                    # Create runner job using the workflow execution system
                    await k8s_service.create_runner_job(workflow_data)
                    logger.info(f"Created workflow runner job for scheduled workflow: {job_id}")
                
                # Record execution
                await self._record_job_execution(schedule_id, job_id, JobStatus.RUNNING)
                
                # Start monitoring job completion in background
                execution_id = await self._get_latest_execution_id(schedule_id, job_id)
                if execution_id:
                    # Start monitoring in background task
                    asyncio.create_task(self._monitor_job_completion(schedule_id, job_id, execution_id))
                
                logger.info(f"Successfully submitted scheduled job {schedule_id} as job {job_id}")
                
            except Exception as e:
                logger.error(f"Error executing scheduled job {schedule_id}: {str(e)}")
                await self._update_scheduled_job_status(schedule_id, JobStatus.FAILED)
                await self._record_job_execution(schedule_id, "", JobStatus.FAILED, error_message=str(e))
        
        return execute_scheduled_job
    
    async def get_scheduled_job(self, schedule_id: str) -> Optional[ScheduledJobResponse]:
        """Get a scheduled job by ID"""
        try:
            # Get from database
            job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            
            if not job_data:
                return None
            
            # Get next run time from scheduler
            next_run = None
            if self.scheduler.get_job(schedule_id):
                next_run = self.scheduler.get_job(schedule_id).next_run_time
            
            return ScheduledJobResponse(
                schedule_id=schedule_id,
                job_type=JobType(job_data["job_type"]),
                name=job_data["name"],
                description=job_data["description"],
                program_id=job_data.get("program_id", ""),
                program_name=job_data.get("program_name", ""),
                job_data=job_data.get("job_data", {}),
                schedule=JobSchedule(**job_data["schedule_data"]),
                status=JobStatus(job_data["status"]),
                next_run=next_run,
                last_run=job_data.get("last_run"),
                total_executions=job_data.get("total_executions", 0),
                successful_executions=job_data.get("successful_executions", 0),
                failed_executions=job_data.get("failed_executions", 0),
                created_at=job_data["created_at"],
                updated_at=job_data["updated_at"],
                tags=job_data.get("tags", [])
            )
            
        except Exception as e:
            logger.error(f"Error getting scheduled job {schedule_id}: {str(e)}")
            return None
    
    async def get_all_scheduled_jobs(self, user_id: Optional[str] = None, program_ids: Optional[List[str]] = None) -> List[ScheduledJobResponse]:
        """Get all scheduled jobs, optionally filtered by user and program permissions"""
        try:
            # Get from database
            scheduled_jobs_data = await ScheduledJobRepository.get_all_scheduled_jobs(user_id, program_ids)
            
            jobs = []
            for job_data in scheduled_jobs_data:
                # Get next run time from scheduler
                next_run = None
                if self.scheduler.get_job(job_data["schedule_id"]):
                    next_run = self.scheduler.get_job(job_data["schedule_id"]).next_run_time
                
                jobs.append(ScheduledJobResponse(
                    schedule_id=job_data["schedule_id"],
                    job_type=JobType(job_data["job_type"]),
                    name=job_data["name"],
                    description=job_data["description"],
                    program_id=job_data.get("program_id", ""),
                    program_name=job_data.get("program_name", ""),
                    job_data=job_data.get("job_data", {}),
                    schedule=JobSchedule(**job_data["schedule_data"]),
                    status=JobStatus(job_data["status"]),
                    next_run=next_run,
                    last_run=job_data.get("last_run"),
                    total_executions=job_data.get("total_executions", 0),
                    successful_executions=job_data.get("successful_executions", 0),
                    failed_executions=job_data.get("failed_executions", 0),
                    created_at=job_data["created_at"],
                    updated_at=job_data["updated_at"],
                    tags=job_data.get("tags", [])
                ))
            
            return jobs
            
        except Exception as e:
            logger.error(f"Error getting scheduled jobs: {str(e)}")
            return []
    
    async def update_scheduled_job(self, schedule_id: str, update_data: Dict[str, Any]) -> Optional[ScheduledJobResponse]:
        """Update a scheduled job"""
        try:
            # Get current job data
            job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            
            if not job_data:
                return None
            
            # Prepare update data for database
            db_update_data = {}
            if "name" in update_data:
                db_update_data["name"] = update_data["name"]
            if "description" in update_data:
                db_update_data["description"] = update_data["description"]
            if "schedule" in update_data:
                db_update_data["schedule_data"] = update_data["schedule"]
            if "enabled" in update_data:
                db_update_data["enabled"] = update_data["enabled"]
            if "tags" in update_data:
                db_update_data["tags"] = update_data["tags"]
            if "job_data" in update_data:
                db_update_data["job_data"] = update_data["job_data"]
            
            # Update in database
            success = await ScheduledJobRepository.update_scheduled_job(schedule_id, db_update_data)
            
            if not success:
                return None
            
            # Reschedule if schedule changed
            if "schedule" in update_data:
                # Remove existing job
                if self.scheduler.get_job(schedule_id):
                    self.scheduler.remove_job(schedule_id)
                
                # Create new schedule
                request = ScheduledJobRequest(
                    job_type=JobType(job_data["job_type"]),
                    job_data=job_data["job_data"],
                    schedule=JobSchedule(**update_data["schedule"]),
                    name=job_data["name"],
                    description=job_data["description"],
                    program_name=job_data.get("program_name", "unknown"),
                    tags=job_data.get("tags", [])
                )
                await self._schedule_job(schedule_id, request)
            
            return await self.get_scheduled_job(schedule_id)
            
        except Exception as e:
            logger.error(f"Error updating scheduled job {schedule_id}: {str(e)}")
            return None
    
    async def delete_scheduled_job(self, schedule_id: str) -> bool:
        """Delete a scheduled job"""
        try:
            # Remove from scheduler
            if self.scheduler.get_job(schedule_id):
                self.scheduler.remove_job(schedule_id)
            
            # Remove from database
            success = await ScheduledJobRepository.delete_scheduled_job(schedule_id)
            
            if success:
                logger.info(f"Deleted scheduled job {schedule_id}")
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(f"Error deleting scheduled job {schedule_id}: {str(e)}")
            return False
    
    async def enable_scheduled_job(self, schedule_id: str) -> bool:
        """Enable a scheduled job"""
        try:
            # Get current job data
            job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            if not job_data:
                return False

            # Update the enabled field inside schedule_data
            schedule_data = job_data["schedule_data"].copy()
            schedule_data["enabled"] = True

            # Update in database
            success = await ScheduledJobRepository.update_scheduled_job(schedule_id, {"schedule_data": schedule_data})

            if not success:
                return False

            # Resume the job in scheduler
            if self.scheduler.get_job(schedule_id):
                self.scheduler.resume_job(schedule_id)

            logger.info(f"Enabled scheduled job {schedule_id}")
            return True

        except Exception as e:
            logger.error(f"Error enabling scheduled job {schedule_id}: {str(e)}")
            return False
    
    async def disable_scheduled_job(self, schedule_id: str) -> bool:
        """Disable a scheduled job"""
        try:
            # Get current job data
            job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            if not job_data:
                return False

            # Update the enabled field inside schedule_data
            schedule_data = job_data["schedule_data"].copy()
            schedule_data["enabled"] = False

            # Update in database
            success = await ScheduledJobRepository.update_scheduled_job(schedule_id, {"schedule_data": schedule_data})

            if not success:
                return False

            # Pause the job in scheduler
            if self.scheduler.get_job(schedule_id):
                self.scheduler.pause_job(schedule_id)

            logger.info(f"Disabled scheduled job {schedule_id}")
            return True

        except Exception as e:
            logger.error(f"Error disabling scheduled job {schedule_id}: {str(e)}")
            return False
    
    async def run_scheduled_job_now(self, schedule_id: str) -> bool:
        """Run a scheduled job immediately"""
        try:
            # Get the scheduled job data
            job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            
            if not job_data:
                logger.error(f"Scheduled job {schedule_id} not found")
                return False
            
            # Create the scheduled job request from stored data
            from models.job import ScheduledJobRequest, JobSchedule
            
            # Use the program name that's already stored in the job data
            program_name = job_data.get("program_name", "unknown")
            
            request = ScheduledJobRequest(
                job_type=JobType(job_data["job_type"]),
                job_data=job_data["job_data"],
                schedule=JobSchedule(**job_data["schedule_data"]),
                name=job_data["name"],
                description=job_data.get("description"),
                program_name=program_name,
                tags=job_data.get("tags", [])
            )
            
            # Execute the job immediately using the same function as scheduled execution
            execution_function = self._create_job_execution_function(schedule_id, request)
            await execution_function()
            
            logger.info(f"Successfully triggered immediate execution for scheduled job {schedule_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error running scheduled job {schedule_id}: {str(e)}")
            return False
    
    async def _get_next_run_time(self, schedule_id: str, schedule: JobSchedule) -> Optional[datetime]:
        """Get the next run time for a scheduled job"""
        try:
            job = self.scheduler.get_job(schedule_id)
            if job:
                return job.next_run_time
            return None
        except Exception as e:
            logger.error(f"Error getting next run time for {schedule_id}: {str(e)}")
            return None
    
    async def _update_scheduled_job_status(self, schedule_id: str, status: JobStatus):
        """Update scheduled job status"""
        await ScheduledJobRepository.update_scheduled_job(schedule_id, {"status": status.value})
    
    async def _record_job_execution(self, schedule_id: str, job_id: str, status: JobStatus, error_message: Optional[str] = None):
        """Record a job execution"""
        try:
            # Update execution counts
            job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            if job_data:
                update_data = {
                    "total_executions": job_data.get("total_executions", 0) + 1,
                    "last_run": datetime.now(timezone.utc)
                }
                
                if status == JobStatus.COMPLETED:
                    update_data["successful_executions"] = job_data.get("successful_executions", 0) + 1
                elif status == JobStatus.FAILED:
                    update_data["failed_executions"] = job_data.get("failed_executions", 0) + 1
                
                await ScheduledJobRepository.update_scheduled_job(schedule_id, update_data)
            
            # Create execution history record
            execution_data = {
                "execution_id": str(uuid.uuid4()),
                "schedule_id": schedule_id,
                "job_id": job_id,
                "status": status.value,
                "started_at": datetime.now(timezone.utc),
                "error_message": error_message
            }
            
            await ScheduledJobRepository.create_execution_history(execution_data)
            
        except Exception as e:
            logger.error(f"Error recording job execution: {str(e)}")
    
    async def _monitor_job_completion(self, schedule_id: str, job_id: str, execution_id: str):
        """Monitor a Kubernetes job for completion and update execution history"""
        try:
            logger.info(f"Starting job completion monitoring for job {job_id} (schedule {schedule_id})")
            
            # Get the scheduled job to determine job type
            scheduled_job = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            job_type = scheduled_job.get("job_type") if scheduled_job else None
            
            # Monitor for up to 30 minutes
            max_attempts = 180  # 30 minutes with 10-second intervals
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    # Get Kubernetes job status - handle different job types
                    job_status = None
                    if job_type == "workflow":
                        # For workflow jobs, use the KubernetesService to get status
                        from services.kubernetes import KubernetesService
                        k8s_service = KubernetesService()
                        try:
                            # Workflow jobs are named with 'workflow-' prefix
                            logger.debug(f"Getting workflow job status for job_id: {job_id}")
                            job_status = k8s_service.get_job_status("workflow", job_id)
                            logger.debug("Workflow job status retrieved successfully")
                        except Exception as e:
                            logger.debug(f"Error getting workflow job status: {str(e)}")
                            job_status = None
                    else:
                        # For other job types, use the JobSubmissionService
                        logger.debug(f"Getting regular job status for job_id: {job_id}")
                        job_status = self.job_submission_service.get_job_status(job_id, job_type=job_type)
                    
                    if not job_status:
                        logger.warning(f"Job {job_id} not found in Kubernetes, marking as failed")
                        await self._update_execution_completion(execution_id, JobStatus.FAILED, error_message="Job not found in Kubernetes")
                        await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
                        return
                    
                    # Check if job is completed
                    if hasattr(job_status, 'status'):
                        if job_status.status.succeeded:
                            logger.info(f"Job {job_id} completed successfully")
                            await self._update_execution_completion(execution_id, JobStatus.COMPLETED)
                            await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
                            return
                        elif job_status.status.failed:
                            logger.error(f"Job {job_id} failed")
                            await self._update_execution_completion(execution_id, JobStatus.FAILED, error_message="Kubernetes job failed")
                            await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
                            return
                    
                    # Job still running, wait and check again
                    await asyncio.sleep(10)  # Wait 10 seconds
                    attempt += 1
                    
                except Exception as e:
                    logger.error(f"Error checking job status for {job_id}: {str(e)}")
                    await asyncio.sleep(10)
                    attempt += 1
            
            # Timeout reached
            logger.warning(f"Job {job_id} monitoring timed out after 30 minutes")
            await self._update_execution_completion(execution_id, JobStatus.FAILED, error_message="Job monitoring timed out")
            await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
            
        except Exception as e:
            logger.error(f"Error in job completion monitoring for {job_id}: {str(e)}")
            await self._update_execution_completion(execution_id, JobStatus.FAILED, error_message=f"Monitoring error: {str(e)}")
            await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
    
    async def _update_execution_completion(self, execution_id: str, status: JobStatus, error_message: Optional[str] = None, results: Optional[Any] = None):
        """Update execution history with completion details"""
        try:
            # Get the execution record to calculate duration
            execution_data = await ScheduledJobRepository.get_execution_history_by_id(execution_id)
            
            if not execution_data:
                logger.error(f"Execution record {execution_id} not found for completion update")
                return
            
            # Calculate duration - handle both string and datetime objects
            started_at = execution_data["started_at"]
            if isinstance(started_at, str):
                # Parse ISO format string to datetime
                started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            
            # Ensure started_at is timezone-aware
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            
            completed_at = datetime.now(timezone.utc)
            duration_seconds = int((completed_at - started_at).total_seconds())
            
            # Update execution history
            update_data = {
                "status": status.value,
                "completed_at": completed_at,
                "duration_seconds": duration_seconds,
                "error_message": error_message
            }
            
            if results is not None:
                update_data["results"] = results
            
            await ScheduledJobRepository.update_execution_history(execution_id, update_data)
            
            # Update success/failure counts on the scheduled job
            schedule_id = execution_data["schedule_id"]
            job_data = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            if job_data:
                update_job_data = {}
                
                if status == JobStatus.COMPLETED:
                    update_job_data["successful_executions"] = job_data.get("successful_executions", 0) + 1
                elif status == JobStatus.FAILED:
                    update_job_data["failed_executions"] = job_data.get("failed_executions", 0) + 1
                
                if update_job_data:
                    await ScheduledJobRepository.update_scheduled_job(schedule_id, update_job_data)
                    logger.info(f"Updated scheduled job {schedule_id} counts: {update_job_data}")
            
            logger.info(f"Updated execution {execution_id} completion: {status.value} (duration: {duration_seconds}s)")
            
        except Exception as e:
            logger.error(f"Error updating execution completion for {execution_id}: {str(e)}")
    
    async def _get_latest_execution_id(self, schedule_id: str, job_id: str) -> Optional[str]:
        """Get the latest execution ID for a job"""
        try:
            # Get the most recent execution for this schedule_id and job_id
            executions = await ScheduledJobRepository.get_execution_history(schedule_id, limit=1)
            
            for execution in executions:
                if execution.get("job_id") == job_id:
                    return execution.get("execution_id")
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting latest execution ID for job {job_id}: {str(e)}")
            return None 