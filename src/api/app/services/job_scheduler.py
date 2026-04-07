import asyncio
import copy
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
    def _parse_datetime_field(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return value
        return value

    def _request_from_stored_row(self, job_data: Dict[str, Any]) -> ScheduledJobRequest:
        """Rebuild API request from a DB/enriched scheduled job row."""
        pnames = job_data.get("program_names") or []
        first_name = job_data.get("program_name") or (pnames[0] if pnames else "unknown")
        kwargs: Dict[str, Any] = dict(
            job_type=JobType(job_data["job_type"]),
            job_data=job_data["job_data"],
            schedule=JobSchedule(**job_data["schedule_data"]),
            name=job_data["name"],
            description=job_data.get("description"),
            program_name=first_name,
            tags=job_data.get("tags", []),
        )
        if len(pnames) > 1:
            kwargs["program_names"] = pnames
        return ScheduledJobRequest(**kwargs)

    def _stored_row_to_response(self, job_data: Dict[str, Any]) -> ScheduledJobResponse:
        schedule_id = job_data["schedule_id"]
        next_run = None
        if self.scheduler.get_job(schedule_id):
            next_run = self.scheduler.get_job(schedule_id).next_run_time
        pids = job_data.get("program_ids") or []
        pnames = job_data.get("program_names") or []
        first_id = pids[0] if pids else None
        first_name = pnames[0] if pnames else job_data.get("program_name")
        return ScheduledJobResponse(
            schedule_id=schedule_id,
            job_type=JobType(job_data["job_type"]),
            name=job_data["name"],
            description=job_data["description"],
            program_ids=[str(p) for p in pids],
            program_names=list(pnames),
            program_id=first_id,
            program_name=first_name,
            job_data=job_data.get("job_data", {}),
            schedule=JobSchedule(**job_data["schedule_data"]),
            status=JobStatus(job_data["status"]),
            next_run=next_run,
            last_run=self._parse_datetime_field(job_data.get("last_run")),
            total_executions=job_data.get("total_executions", 0),
            successful_executions=job_data.get("successful_executions", 0),
            failed_executions=job_data.get("failed_executions", 0),
            created_at=self._parse_datetime_field(job_data["created_at"]),
            updated_at=self._parse_datetime_field(job_data["updated_at"]),
            tags=job_data.get("tags", []),
        )

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
                    request = self._request_from_stored_row(job_data)
                    # Schedule the job
                    await self._schedule_job(job_data["schedule_id"], request)
                    
                    # Store in memory
                    self.scheduled_jobs[job_data["schedule_id"]] = job_data
            
            logger.info(f"Loaded {len(scheduled_jobs_data)} scheduled jobs from database")
            
        except Exception as e:
            logger.error(f"Error loading scheduled jobs: {str(e)}")
    
    async def create_scheduled_job(
        self, request: ScheduledJobRequest, user_id: str, program_ids: List[str]
    ) -> ScheduledJobResponse:
        """Create a new scheduled job (program_ids: UUID strings, non-empty)."""
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
                "program_ids": program_ids,
                "status": JobStatus.SCHEDULED.value,
                "tags": request.tags,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc)
            }
            
            # Save to database
            await ScheduledJobRepository.create_scheduled_job(scheduled_job_data)
            
            # Schedule the job
            await self._schedule_job(schedule_id, request)
            
            stored = await ScheduledJobRepository.get_scheduled_job(schedule_id)
            if not stored:
                raise RuntimeError("Scheduled job row missing after create")
            self.scheduled_jobs[schedule_id] = stored

            logger.info(f"Created scheduled job {schedule_id}: {request.name}")

            return self._stored_row_to_response(stored)
            
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
    
    async def _execute_multi_program_workflow(
        self, schedule_id: str, request: ScheduledJobRequest, job_row: Dict[str, Any]
    ) -> None:
        """Run one Kubernetes workflow runner per program on this scheduled job."""
        from services.kubernetes import KubernetesService
        from repository import WorkflowDefinitionRepository

        k8s_service = KubernetesService()
        workflow_repo = WorkflowDefinitionRepository()

        effective_job_data = job_row.get("job_data") or {}
        stored_variables = job_row.get("workflow_variables") or {}
        target_program_names = [n for n in (job_row.get("program_names") or []) if n]
        if not target_program_names:
            raise ValueError("Scheduled workflow has no resolved programs")

        wf_id = effective_job_data.get("workflow_id")
        workflow_specs: List[Dict[str, Any]] = []

        if wf_id:
            workflow_definition = await workflow_repo.get_workflow_definition(wf_id)
            if not workflow_definition:
                raise ValueError(f"Workflow definition not found: {wf_id}")
            base = {
                "workflow_id": wf_id,
                "program_name": "",
                "execution_id": "",
                "name": workflow_definition.get("name", request.name),
                "description": workflow_definition.get(
                    "description", request.description or "Scheduled workflow execution"
                ),
                "variables": workflow_definition.get("variables", {}),
                "inputs": workflow_definition.get("inputs", {}),
                "steps": workflow_definition.get("steps", []),
            }
            if stored_variables and base.get("variables"):
                try:
                    from utils.workflow_processor import process_workflow_with_variables

                    base = process_workflow_with_variables(base, stored_variables)
                except ImportError:
                    logger.warning("Workflow processing utilities not available, using raw workflow")
                except Exception as e:
                    logger.error(f"Error processing workflow with variables: {str(e)}")
            for _pn in target_program_names:
                workflow_specs.append(copy.deepcopy(base))
        else:
            logger.warning("No workflow_id in job_data; using inline job_data for workflow")
            for _pn in target_program_names:
                wd = {
                    "workflow_id": None,
                    "program_name": "",
                    "execution_id": "",
                    "name": request.name,
                    "description": request.description or "Scheduled workflow execution",
                    "variables": effective_job_data.get("variables", {}),
                    "inputs": effective_job_data.get("inputs", {}),
                    "steps": effective_job_data.get("steps", []),
                }
                if stored_variables and wd.get("variables"):
                    try:
                        from utils.workflow_processor import process_workflow_with_variables

                        wd = process_workflow_with_variables(wd, stored_variables)
                    except Exception as e:
                        logger.error(f"Error processing workflow with variables: {str(e)}")
                workflow_specs.append(wd)

        monitor_coros: List[Any] = []
        for program_name, spec in zip(target_program_names, workflow_specs):
            job_id = str(uuid.uuid4())
            spec["program_name"] = program_name
            spec["execution_id"] = job_id
            job_payload = {
                "job_id": job_id,
                "job_type": request.job_type.value,
                "schedule_id": schedule_id,
                "job_data": effective_job_data,
                "user_id": job_row["user_id"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await JobRepository.create_job(job_id, request.job_type.value, job_payload)
            await k8s_service.create_runner_job(spec)
            logger.info(
                f"Created workflow runner job for scheduled workflow: {job_id} program={program_name}"
            )
            await self._record_job_execution(schedule_id, job_id, JobStatus.RUNNING)
            execution_id = await self._get_latest_execution_id(schedule_id, job_id)
            if execution_id:
                monitor_coros.append(
                    self._monitor_job_completion(
                        schedule_id, job_id, execution_id, update_schedule_status=False
                    )
                )

        if monitor_coros:
            results = await asyncio.gather(*monitor_coros, return_exceptions=True)
            failed = any(isinstance(r, Exception) for r in results) or any(r is not True for r in results if not isinstance(r, Exception))
            if failed:
                await self._update_scheduled_job_status(schedule_id, JobStatus.FAILED)
            else:
                await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
        else:
            await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)

    def _create_job_execution_function(self, schedule_id: str, request: ScheduledJobRequest) -> Callable:
        """Create a function that will be executed when the scheduled job runs"""
        async def execute_scheduled_job():
            try:
                logger.info(f"Executing scheduled job {schedule_id}: {request.name}")
                logger.debug(f"Request: {request}")
                await self._update_scheduled_job_status(schedule_id, JobStatus.RUNNING)

                job_row = await ScheduledJobRepository.get_scheduled_job(schedule_id)
                if not job_row:
                    raise ValueError(f"Scheduled job {schedule_id} not found in database")

                if request.job_type == JobType.WORKFLOW:
                    await self._execute_multi_program_workflow(schedule_id, request, job_row)
                    logger.info(f"Finished multi-program workflow submission for schedule {schedule_id}")
                    return

                effective_job_data = job_row.get("job_data") or {}

                job_id = str(uuid.uuid4())
                job_payload = {
                    "job_id": job_id,
                    "job_type": request.job_type.value,
                    "schedule_id": schedule_id,
                    "job_data": effective_job_data,
                    "user_id": job_row["user_id"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                await JobRepository.create_job(job_id, request.job_type.value, job_payload)

                if request.job_type == JobType.GATHER_API_FINDINGS:
                    worker_payload = {
                        "job_id": job_id,
                        "job_type": request.job_type.value,
                        "schedule_id": schedule_id,
                        "user_id": job_row["user_id"],
                        "program_name": request.program_name,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "job_data": effective_job_data,
                    }
                else:
                    worker_payload = {
                        "job_id": job_id,
                        "job_type": request.job_type.value,
                        "schedule_id": schedule_id,
                        "user_id": job_row["user_id"],
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        **effective_job_data,
                    }

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

                await self._record_job_execution(schedule_id, job_id, JobStatus.RUNNING)

                execution_id = await self._get_latest_execution_id(schedule_id, job_id)
                if execution_id:
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

            return self._stored_row_to_response(job_data)

        except Exception as e:
            logger.error(f"Error getting scheduled job {schedule_id}: {str(e)}")
            return None
    
    async def get_all_scheduled_jobs(self, user_id: Optional[str] = None, program_ids: Optional[List[str]] = None) -> List[ScheduledJobResponse]:
        """Get all scheduled jobs, optionally filtered by user and program permissions"""
        try:
            # Get from database
            scheduled_jobs_data = await ScheduledJobRepository.get_all_scheduled_jobs(user_id, program_ids)
            
            jobs = [self._stored_row_to_response(job_data) for job_data in scheduled_jobs_data]
            
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
            if "program_ids" in update_data:
                db_update_data["program_ids"] = update_data["program_ids"]

            # Update in database
            success = await ScheduledJobRepository.update_scheduled_job(schedule_id, db_update_data)

            if not success:
                return None

            reschedule = any(k in update_data for k in ("schedule", "job_data", "program_ids"))
            if reschedule and job_data.get("enabled", True):
                if self.scheduler.get_job(schedule_id):
                    self.scheduler.remove_job(schedule_id)
                fresh = await ScheduledJobRepository.get_scheduled_job(schedule_id)
                if fresh:
                    request = self._request_from_stored_row(fresh)
                    await self._schedule_job(schedule_id, request)
                    self.scheduled_jobs[schedule_id] = fresh

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
            
            request = self._request_from_stored_row(job_data)
            
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
    
    async def _monitor_job_completion(
        self,
        schedule_id: str,
        job_id: str,
        execution_id: str,
        *,
        update_schedule_status: bool = True,
    ) -> bool:
        """Monitor a Kubernetes job for completion. Returns True if the job completed successfully."""
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
                        if update_schedule_status:
                            await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
                        return False
                    
                    # Check if job is completed
                    if hasattr(job_status, 'status'):
                        if job_status.status.succeeded:
                            logger.info(f"Job {job_id} completed successfully")
                            await self._update_execution_completion(execution_id, JobStatus.COMPLETED)
                            if update_schedule_status:
                                await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
                            return True
                        elif job_status.status.failed:
                            logger.error(f"Job {job_id} failed")
                            await self._update_execution_completion(execution_id, JobStatus.FAILED, error_message="Kubernetes job failed")
                            if update_schedule_status:
                                await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
                            return False
                    
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
            if update_schedule_status:
                await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
            return False
            
        except Exception as e:
            logger.error(f"Error in job completion monitoring for {job_id}: {str(e)}")
            await self._update_execution_completion(execution_id, JobStatus.FAILED, error_message=f"Monitoring error: {str(e)}")
            if update_schedule_status:
                await self._update_scheduled_job_status(schedule_id, JobStatus.SCHEDULED)
            return False
    
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